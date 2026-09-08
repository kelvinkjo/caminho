from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, BackgroundTasks
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import logging, uuid, bcrypt, jwt, re, secrets

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    _LLM_OK = True
except Exception:
    _LLM_OK = False

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"

app = FastAPI()

cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)

api = APIRouter(prefix="/api")

# ---------------- helpers ----------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False

def create_token(uid: str, ttl_minutes=15):
    payload = {
        "sub": uid,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def public_user(u: dict) -> dict:
    u = dict(u)
    u.pop("_id", None)
    u.pop("password_hash", None)
    u["permissions"] = sorted(effective_perms(u))
    u["role_label"] = ROLE_LABEL.get(u.get("role"), u.get("role"))
    u["is_top_authority"] = u.get("role") in TOP_AUTHORITY
    _fst, _fyr = FORMATION_META.get(u.get("current_stage_order", 1), ("PRE_VOCACIONADO", None))
    u.setdefault("formation_stage", _fst)
    u.setdefault("formation_year", _fyr)
    u.setdefault("formation_status", "EM_FORMACAO" if u.get("role") == "membro" else "ATIVO")
    return u

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "Não autenticado")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Sessão expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")
    u = await db.users.find_one({"id": payload["sub"]})
    if not u:
        raise HTTPException(401, "Usuário não encontrado")
    if u.get("blocked"):
        raise HTTPException(403, "Conta bloqueada")
    await db.users.update_one({"id": u["id"]}, {"$set": {"last_active": now_iso()}})
    return u

def require_roles(*roles):
    async def dep(user: dict = Depends(get_current_user)):
        if user["role"] != "mestre" and not is_top_authority(user) and user["role"] not in roles:
            raise HTTPException(403, "Acesso não autorizado")
        return user
    return dep

async def require_master(user: dict = Depends(get_current_user)) -> dict:
    # Autoridade institucional sobre etapas/config: Admin, Fundador (ou quem tiver MANAGE_FORMATION_STAGE)
    if user["role"] in ("admin", "fundador") or "MANAGE_FORMATION_STAGE" in (user.get("permissions") or []):
        return user
    raise HTTPException(403, "Apenas Admin ou Fundador podem gerenciar etapas e configurações de formação.")

# ---------------- models ----------------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProgressIn(BaseModel):
    completed: bool = False
    percent: int = 0

class FollowupIn(BaseModel):
    note: str = ""

class AdminUserPatch(BaseModel):
    role: Optional[str] = None
    formador_id: Optional[str] = None
    blocked: Optional[bool] = None

# ---------------- auth endpoints ----------------
def set_cookie(resp: Response, token: str):
    cookie_secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    cookie_samesite = os.environ.get("COOKIE_SAMESITE", "lax").lower()

    if cookie_samesite not in {"lax", "strict", "none"}:
        raise RuntimeError("COOKIE_SAMESITE inválido.")

    if cookie_samesite == "none" and not cookie_secure:
        raise RuntimeError("COOKIE_SAMESITE=none exige COOKIE_SECURE=true.")

    resp.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=900,
        path="/",
    )

@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "E-mail já cadastrado")
    uid = str(uuid.uuid4())
    doc = {
        "id": uid, "name": body.name, "email": email,
        "password_hash": hash_password(body.password),
        "role": "membro", "current_stage_order": 1, "formador_id": None,
        "onboarded": False, "blocked": False, "avatar": None, "permissions": [],
        "created_at": now_iso(), "last_active": now_iso(),
    }
    await db.users.insert_one(doc)
    token = create_token(uid)
    set_cookie(response, token)
    return {"user": public_user(doc)}

@api.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower()
    u = await db.users.find_one({"email": email})
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "E-mail ou senha inválidos")
    if u.get("blocked"):
        raise HTTPException(403, "Conta bloqueada")
    token = create_token(u["id"])
    set_cookie(response, token)
    return {"user": public_user(u)}

@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

@api.post("/auth/onboard-complete")
async def onboard_complete(user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"onboarded": True}})
    await award(user["id"], "primeiro_encontro")
    return {"ok": True}

@api.post("/auth/forgot-password")
async def forgot_password(body: dict):
    email = (body.get("email") or "").lower()
    logging.info(f"[reset] pedido de recuperação para {email}")
    return {"ok": True, "message": "Se o e-mail existir, enviaremos instruções."}

# ---------------- stage access ----------------
async def stage_progress(user_id: str, stage_order: int):
    lessons = await db.lessons.find({"stage_order": stage_order}).to_list(1000)
    total = len(lessons)
    if total == 0:
        return {"total": 0, "completed": 0, "percent": 0}
    ids = [l["id"] for l in lessons]
    done = await db.lesson_progress.count_documents({"user_id": user_id, "lesson_id": {"$in": ids}, "completed": True})
    return {"total": total, "completed": done, "percent": round(done / total * 100)}

@api.get("/stages")
async def get_stages(user: dict = Depends(get_current_user)):
    stages = await db.stages.find().sort("order", 1).to_list(100)
    out = []
    cur = user["current_stage_order"]
    approval = await db.approvals.find_one({"user_id": user["id"], "status": "pending"})
    for s in stages:
        s.pop("_id", None)
        prog = await stage_progress(user["id"], s["order"])
        if s["order"] < cur:
            status = "completed"
        elif s["order"] == cur:
            status = "awaiting_approval" if (approval and approval["stage_order"] == cur) else "current"
        else:
            status = "locked"
        s["status"] = status
        s["accessible"] = s["order"] <= cur
        s["progress"] = prog
        out.append(s)
    return out

@api.get("/stages/{order}/modules")
async def get_modules(order: int, user: dict = Depends(get_current_user)):
    if user["role"] not in STAFF_ROLES and order > user["current_stage_order"]:
        raise HTTPException(403, "Etapa bloqueada")
    modules = await db.modules.find({"stage_order": order}).sort("order", 1).to_list(200)
    prog_docs = await db.lesson_progress.find({"user_id": user["id"]}).to_list(2000)
    prog_map = {p["lesson_id"]: p for p in prog_docs}
    out = []
    for m in modules:
        m.pop("_id", None)
        lessons = await db.lessons.find({"module_id": m["id"]}).sort("order", 1).to_list(200)
        lout = []
        for l in lessons:
            l.pop("_id", None)
            p = prog_map.get(l["id"])
            l["completed"] = bool(p and p.get("completed"))
            l["percent"] = p.get("percent", 0) if p else 0
            lout.append(l)
        m["lessons"] = lout
        out.append(m)
    stage = await db.stages.find_one({"order": order})
    if stage:
        stage.pop("_id", None)
    return {"stage": stage, "modules": out, "progress": await stage_progress(user["id"], order)}

@api.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str, user: dict = Depends(get_current_user)):
    l = await db.lessons.find_one({"id": lesson_id})
    if not l:
        raise HTTPException(404, "Aula não encontrada")
    if user["role"] not in ("admin", "formador", "mestre") and l["stage_order"] > user["current_stage_order"]:
        raise HTTPException(403, "Etapa bloqueada")
    l.pop("_id", None)
    p = await db.lesson_progress.find_one({"user_id": user["id"], "lesson_id": lesson_id})
    l["completed"] = bool(p and p.get("completed"))
    l["percent"] = p.get("percent", 0) if p else 0
    return l

@api.post("/lessons/{lesson_id}/progress")
async def set_progress(lesson_id: str, body: ProgressIn, user: dict = Depends(get_current_user)):
    l = await db.lessons.find_one({"id": lesson_id})
    if not l:
        raise HTTPException(404, "Aula não encontrada")
    if user["role"] not in ("admin", "formador", "mestre") and l["stage_order"] > user["current_stage_order"]:
        raise HTTPException(403, "Etapa bloqueada")
    await db.lesson_progress.update_one(
        {"user_id": user["id"], "lesson_id": lesson_id},
        {"$set": {"completed": body.completed, "percent": max(body.percent, 100 if body.completed else 0),
                  "stage_order": l["stage_order"], "updated_at": now_iso()},
         "$setOnInsert": {"id": str(uuid.uuid4()), "started_at": now_iso()}},
        upsert=True)
    if body.completed:
        await award(user["id"], "primeira_formacao")
    return {"ok": True, "progress": await stage_progress(user["id"], l["stage_order"])}

# ---------------- formation status + recomendação (NUNCA altera etapa) ----------------
# REGRA INVIOLÁVEL: concluir a formação NÃO muda a etapa. Etapa só muda pelo Login Mestre.
async def stage_reqs(order: int):
    r = await db.stage_requirements.find_one({"order": order})
    return {"require_lessons": r.get("require_lessons", True) if r else True,
            "require_mandatory_lives": r.get("require_mandatory_lives", True) if r else True}

async def formation_status(user_id: str, order: int):
    prog = await stage_progress(user_id, order)
    reqs = await stage_reqs(order)
    lessons_ok = (prog["percent"] >= 100) if reqs["require_lessons"] else True
    lives_pending = (await mandatory_lives_pending(user_id, order)) if reqs["require_mandatory_lives"] else False
    concluded = lessons_ok and not lives_pending
    return {"percent": prog["percent"], "completed_lessons": prog["completed"],
            "total_lessons": prog["total"], "mandatory_lives_ok": not lives_pending,
            "concluded": concluded, "requirements": reqs}

@api.get("/formation/status")
async def my_formation_status(user: dict = Depends(get_current_user)):
    order = user["current_stage_order"]
    fs = await formation_status(user["id"], order)
    fs["next_step"] = ("Você concluiu os requisitos formativos desta etapa. A continuidade da sua caminhada será definida pela liderança responsável."
                       if fs["concluded"] else "Continue sua formação nesta etapa, no seu ritmo.")
    return fs

class RecommendIn(BaseModel):
    user_id: str
    recommended_stage_order: int
    justification: str

@api.post("/formador/recommend")
async def formador_recommend(body: RecommendIn, user: dict = Depends(require_roles("formador"))):
    if not body.justification.strip():
        raise HTTPException(400, "A justificativa é obrigatória.")
    if not (1 <= body.recommended_stage_order <= 6):
        raise HTTPException(400, "Etapa inválida.")
    target = await db.users.find_one({"id": body.user_id})
    if not target:
        raise HTTPException(404, "Usuário não encontrado")
    if user["role"] == "formador" and target.get("formador_id") != user["id"]:
        raise HTTPException(403, "Você só pode recomendar para pessoas que acompanha.")
    doc = {"id": str(uuid.uuid4()), "user_id": target["id"], "user_name": target["name"],
           "formador_id": user["id"], "formador_name": user["name"],
           "current_stage_order": target["current_stage_order"],
           "recommended_stage_order": body.recommended_stage_order,
           "justification": body.justification.strip(), "status": "pending",
           "created_at": now_iso(), "resolved_at": None, "resolved_by": None}
    await db.stage_recommendations.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "recommendation": doc}

@api.get("/formador/recommendations")
async def formador_recommendations(user: dict = Depends(require_roles("formador"))):
    items = await db.stage_recommendations.find({"formador_id": user["id"]}).sort("created_at", -1).to_list(500)
    for i in items:
        i.pop("_id", None)
    return items

# ---------------- formador people + radar ----------------
def radar_status(last_active: str):
    try:
        la = datetime.fromisoformat(last_active)
    except Exception:
        return "red"
    days = (datetime.now(timezone.utc) - la).days
    if days <= 3:
        return "green"
    if days <= 10:
        return "yellow"
    return "red"

@api.get("/formador/people")
async def my_people(user: dict = Depends(require_roles("admin", "formador"))):
    q = {} if user["role"] in ("admin", "fundador", "cofundador") else {"formador_id": user["id"]}
    q["role"] = "membro"
    people = await db.users.find(q).to_list(1000)
    stages = {s["order"]: s async for s in db.stages.find()}
    out = []
    for p in people:
        prog = await stage_progress(p["id"], p["current_stage_order"])
        fs = await formation_status(p["id"], p["current_stage_order"])
        st = stages.get(p["current_stage_order"], {})
        rec = await db.stage_recommendations.find_one({"user_id": p["id"], "status": "pending"})
        out.append({
            "id": p["id"], "name": p["name"], "email": p["email"],
            "current_stage_order": p["current_stage_order"],
            "stage_name": st.get("name", ""), "progress": prog,
            "formation_concluded": fs["concluded"],
            "recommendation_pending": bool(rec),
            "last_active": p.get("last_active"), "radar": radar_status(p.get("last_active", "")),
        })
    order = {"red": 0, "yellow": 1, "green": 2}
    out.sort(key=lambda x: order.get(x["radar"], 3))
    return out

# ---------------- missions ----------------
@api.get("/missions")
async def get_missions(user: dict = Depends(get_current_user)):
    missions = await db.missions.find({"active": True}).sort("order", 1).to_list(100)
    done = {d["mission_id"] async for d in db.mission_progress.find({"user_id": user["id"]})}
    out = []
    for m in missions:
        m.pop("_id", None)
        m["completed"] = m["id"] in done
        out.append(m)
    return out

@api.post("/missions/{mission_id}/complete")
async def complete_mission(mission_id: str, user: dict = Depends(get_current_user)):
    m = await db.missions.find_one({"id": mission_id})
    if not m:
        raise HTTPException(404, "Missão não encontrada")
    await db.mission_progress.update_one(
        {"user_id": user["id"], "mission_id": mission_id},
        {"$set": {"completed_at": now_iso()}, "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    await award(user["id"], "primeira_missao")
    return {"ok": True}

@api.get("/daily-word")
async def daily_word():
    w = await db.daily_readings.find_one({"kind": "word"})
    if w:
        w.pop("_id", None)
    return w or {}

# ---------------- dashboard ----------------
@api.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    stage = await db.stages.find_one({"order": user["current_stage_order"]})
    if stage:
        stage.pop("_id", None)
    prog = await stage_progress(user["id"], user["current_stage_order"])
    # continue lesson: latest updated incomplete in current stage
    last = await db.lesson_progress.find({"user_id": user["id"], "completed": False}).sort("updated_at", -1).to_list(1)
    continue_lesson = None
    if last:
        l = await db.lessons.find_one({"id": last[0]["lesson_id"]})
        if l:
            continue_lesson = {"id": l["id"], "title": l["title"], "module_title": l.get("module_title"), "percent": last[0].get("percent", 0)}
    if not continue_lesson:
        l = await db.lessons.find_one({"stage_order": user["current_stage_order"]}, sort=[("order", 1)])
        if l:
            continue_lesson = {"id": l["id"], "title": l["title"], "module_title": l.get("module_title"), "percent": 0}
    word = await daily_word()
    missions = await db.missions.find({"active": True}).sort("order", 1).to_list(3)
    mdone = {d["mission_id"] async for d in db.mission_progress.find({"user_id": user["id"]})}
    for m in missions:
        m.pop("_id", None)
        m["completed"] = m["id"] in mdone
    events = await db.events.find({}).sort("date", 1).to_list(3)
    for e in events:
        e.pop("_id", None)
    live = await db.lives.find_one({"status": "upcoming"}, sort=[("date", 1)])
    if live:
        live.pop("_id", None)
    fstatus = await formation_status(user["id"], user["current_stage_order"])
    notifs = await db.notifications.find({"user_id": user["id"], "read": False}).sort("at", -1).to_list(10)
    for n in notifs:
        n.pop("_id", None)
    return {
        "user": public_user(user), "stage": stage, "progress": prog,
        "continue_lesson": continue_lesson, "word": word,
        "missions": missions, "events": events, "next_live": live,
        "formation": fstatus, "notifications": notifs,
    }

# ---------------- admin ----------------
@api.get("/admin/stats")
async def admin_stats(user: dict = Depends(require_roles("admin"))):
    total = await db.users.count_documents({})
    by_stage = []
    stages = await db.stages.find().sort("order", 1).to_list(100)
    for s in stages:
        c = await db.users.count_documents({"current_stage_order": s["order"], "role": "membro"})
        by_stage.append({"stage": s["name"], "order": s["order"], "count": c})
    pending = await db.stage_recommendations.count_documents({"status": "pending"})
    formadores = await db.users.count_documents({"role": "formador"})
    return {"total_users": total, "by_stage": by_stage, "pending_approvals": pending, "formadores": formadores}

@api.get("/admin/users")
async def admin_users(user: dict = Depends(require_roles("admin"))):
    users = await db.users.find().sort("created_at", -1).to_list(2000)
    return [public_user(u) for u in users]

@api.patch("/admin/users/{uid}")
async def admin_patch_user(uid: str, body: AdminUserPatch, user: dict = Depends(require_roles("admin"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    await db.users.update_one({"id": uid}, {"$set": updates})
    if updates.get("formador_id"):
        await award(uid, "primeiro_acompanhamento")
    await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "action": "admin_update_user", "by": user["id"],
                                    "user_id": uid, "changes": updates, "at": now_iso()})
    return {"ok": True}

@api.get("/formadores")
async def list_formadores(user: dict = Depends(require_roles("admin"))):
    fs = await db.users.find({"role": "formador"}).to_list(500)
    return [{"id": f["id"], "name": f["name"]} for f in fs]

# ---------------- MASTER / Controle Mestre (permissão MANAGE_FORMATION_STAGE) ----------------
class StageDecisionIn(BaseModel):
    new_stage_order: int = 0
    reason: str
    action: str = "change"  # "change" | "maintain"

class ResolveRecIn(BaseModel):
    accept: bool
    reason: str = ""

class SettingsIn(BaseModel):
    allow_stage_skip: bool

async def notify(user_id: str, title: str, body: str):
    await db.notifications.insert_one({"id": str(uuid.uuid4()), "user_id": user_id, "title": title,
                                       "body": body, "read": False, "at": now_iso()})

@api.get("/master/users")
async def master_users(search: Optional[str] = None, master: dict = Depends(require_master)):
    q = {"role": {"$in": ["membro", "formador"]}}
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"name": rx}, {"email": rx}]
    users = await db.users.find(q).sort("name", 1).to_list(2000)
    stages = {s["order"]: s async for s in db.stages.find()}
    out = []
    for u in users:
        fs = await formation_status(u["id"], u["current_stage_order"])
        out.append({"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"],
                    "current_stage_order": u["current_stage_order"],
                    "stage_name": stages.get(u["current_stage_order"], {}).get("name", ""),
                    "progress_percent": fs["percent"], "formation_concluded": fs["concluded"],
                    "formador_id": u.get("formador_id")})
    return out

@api.get("/master/users/{uid}")
async def master_user_detail(uid: str, master: dict = Depends(require_master)):
    u = await db.users.find_one({"id": uid})
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    order = u["current_stage_order"]
    fs = await formation_status(uid, order)
    stage = await db.stages.find_one({"order": order})
    req_lives = await db.lives.find({"stage_order": order, "required": True}).to_list(100)
    lives_ok = 0
    for l in req_lives:
        if await db.live_attendance.find_one({"user_id": uid, "live_id": l["id"], "confirmed": True}):
            lives_ok += 1
    logs = await db.stage_change_logs.find({"user_id": uid}).sort("changed_at", -1).to_list(100)
    for lg in logs:
        lg.pop("_id", None)
    recs = await db.stage_recommendations.find({"user_id": uid}).sort("created_at", -1).to_list(50)
    for r in recs:
        r.pop("_id", None)
    return {"id": uid, "name": u["name"], "email": u["email"], "role": u["role"],
            "current_stage_order": order, "stage_name": stage.get("name") if stage else "",
            "formation": fs, "mandatory_lives": {"ok": lives_ok, "total": len(req_lives)},
            "history": logs, "recommendations": recs, "formador_id": u.get("formador_id")}

async def _apply_stage(uid: str, new_order: int, reason: str, action: str, master: dict, ip: Optional[str]):
    u = await db.users.find_one({"id": uid})
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    prev = u["current_stage_order"]
    if action == "maintain":
        new_order, change_type = prev, "MAINTAIN_STAGE"
    else:
        if not (1 <= new_order <= 6):
            raise HTTPException(400, "Etapa inválida.")
        change_type = "MAINTAIN_STAGE" if new_order == prev else ("ADVANCEMENT" if new_order > prev else "RETROCESSION")
        if new_order != prev:
            _fst, _fyr = FORMATION_META.get(new_order, ("PRE_VOCACIONADO", None))
            await db.users.update_one({"id": uid}, {"$set": {"current_stage_order": new_order, "formation_stage": _fst, "formation_year": _fyr}})
    log = {"id": str(uuid.uuid4()), "user_id": uid, "previous_stage": prev, "new_stage": new_order,
           "changed_by": master["id"], "changed_by_name": master["name"], "changed_at": now_iso(),
           "reason": reason.strip(), "change_type": change_type, "ip": ip}
    await db.stage_change_logs.insert_one(log)
    if new_order >= 5:
        await award(uid, "compromisso")
    if new_order >= 6:
        await award(uid, "consagracao")
    stages = {s["order"]: s["name"] async for s in db.stages.find()}
    if change_type == "MAINTAIN_STAGE":
        await notify(uid, "Sua formação foi registrada", f"Sua caminhada continuará na etapa {stages.get(new_order,'')}.")
    else:
        await notify(uid, "Sua jornada foi atualizada", f"Sua etapa de formação foi atualizada para {stages.get(new_order,'')}. Continue sua caminhada de formação, comunidade e missão.")
    if u.get("formador_id"):
        await notify(u["formador_id"], "Decisão de etapa registrada", f"A decisão sobre a etapa de {u['name']} foi registrada pela liderança.")
    await audit("FORMATION_STAGE_CHANGED", master, user_id=uid, previous=prev, new=new_order, change_type=change_type)
    log.pop("_id", None)
    return log

@api.post("/master/users/{uid}/stage")
async def master_set_stage(uid: str, body: StageDecisionIn, request: Request, master: dict = Depends(require_master)):
    if not body.reason.strip():
        raise HTTPException(400, "O motivo da decisão é obrigatório.")
    ip = request.client.host if request.client else None
    log = await _apply_stage(uid, body.new_stage_order, body.reason, body.action, master, ip)
    return {"ok": True, "log": log}

@api.get("/master/recommendations")
async def master_recommendations(master: dict = Depends(require_master)):
    items = await db.stage_recommendations.find({"status": "pending"}).sort("created_at", 1).to_list(500)
    for i in items:
        i.pop("_id", None)
    return items

@api.post("/master/recommendations/{rid}/resolve")
async def master_resolve_rec(rid: str, body: ResolveRecIn, request: Request, master: dict = Depends(require_master)):
    r = await db.stage_recommendations.find_one({"id": rid})
    if not r or r["status"] != "pending":
        raise HTTPException(404, "Recomendação não encontrada")
    status = "accepted" if body.accept else "rejected"
    await db.stage_recommendations.update_one({"id": rid}, {"$set": {"status": status, "resolved_at": now_iso(), "resolved_by": master["id"]}})
    await notify(r["formador_id"], "Recomendação respondida", f"Sua recomendação de etapa para {r['user_name']} foi {'aceita' if body.accept else 'recusada'} pelo Login Mestre.")
    if body.accept:
        ip = request.client.host if request.client else None
        await _apply_stage(r["user_id"], r["recommended_stage_order"], body.reason or r["justification"], "change", master, ip)
    return {"ok": True, "status": status}

@api.get("/master/settings")
async def get_settings(master: dict = Depends(require_master)):
    s = await db.settings.find_one({"key": "app"})
    if s:
        s.pop("_id", None)
    return s or {"key": "app", "allow_stage_skip": True}

@api.put("/master/settings")
async def put_settings(body: SettingsIn, master: dict = Depends(require_master)):
    await db.settings.update_one({"key": "app"}, {"$set": {"allow_stage_skip": body.allow_stage_skip}}, upsert=True)
    return {"ok": True}

# ---------------- notifications ----------------
@api.get("/notifications")
async def get_notifications(since: Optional[str] = None, limit: int = 100, user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"]}
    if since:
        q["at"] = {"$gt": since}
    items = await db.notifications.find(q).sort("at", -1).to_list(max(1, min(limit, 500)))
    for i in items:
        i.pop("_id", None)
    return items

@api.post("/notifications/read")
async def read_notifications(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}

# ---------------- AI assistant (Fase 8) ----------------
ASSISTANT_SYSTEM = (
    "Você é o Assistente de Formação do app CAMINHO, de uma comunidade católica jovem, "
    "carismática e missionária. Responda em português do Brasil, de forma acolhedora, clara "
    "e fiel ao Magistério da Igreja Católica.\n\n"
    "REGRAS OBRIGATÓRIAS:\n"
    "1. Nunca invente ensinamentos. Se não souber, diga honestamente que não sabe.\n"
    "2. Sempre que possível, indique as fontes: passagens bíblicas (livro, capítulo e versículo), "
    "números do Catecismo da Igreja Católica (CIC), documentos do Magistério (encíclicas, concílios) e santos.\n"
    "3. Diferencie claramente a DOUTRINA OFICIAL da Igreja de opiniões teológicas, tradições piedosas ou pareceres pessoais.\n"
    "4. Cite documentos do Magistério quando apropriado.\n"
    "5. Em questões pastorais complexas (pecado grave, discernimento vocacional, situações pessoais, "
    "sofrimento, saúde mental, decisões de vida), incentive o usuário a procurar um sacerdote, confessor, "
    "diretor espiritual ou formador da comunidade.\n\n"
    "Você NÃO substitui o sacerdote, o confessor, o diretor espiritual nem o formador. "
    "Você é uma ferramenta de apoio à formação, não uma autoridade pastoral."
)

class AssistantIn(BaseModel):
    question: str
    session_id: Optional[str] = None

@api.post("/assistant/ask")
async def assistant_ask(body: AssistantIn, user: dict = Depends(get_current_user)):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(400, "Digite uma pergunta.")
    if len(q) > 2000:
        raise HTTPException(400, "Pergunta muito longa.")
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not _LLM_OK or not key:
        raise HTTPException(503, "Assistente indisponível no momento.")
    session_id = body.session_id or str(uuid.uuid4())
    history = await db.assistant_messages.find(
        {"user_id": user["id"], "session_id": session_id}).sort("at", 1).to_list(20)
    convo = ""
    for h in history[-10:]:
        convo += f"{'Usuário' if h['role'] == 'user' else 'Assistente'}: {h['text']}\n"
    prompt = (convo + f"Usuário: {q}\nAssistente:") if convo else q
    try:
        chat = LlmChat(api_key=key, session_id=session_id, system_message=ASSISTANT_SYSTEM).with_model("anthropic", "claude-sonnet-4-6")
        answer = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logging.error(f"assistant error: {e}")
        raise HTTPException(502, "Não foi possível obter uma resposta agora. Tente novamente.")
    await db.assistant_messages.insert_one({"id": str(uuid.uuid4()), "user_id": user["id"], "session_id": session_id, "role": "user", "text": q, "at": now_iso()})
    await db.assistant_messages.insert_one({"id": str(uuid.uuid4()), "user_id": user["id"], "session_id": session_id, "role": "assistant", "text": answer, "at": now_iso()})
    return {"answer": answer, "session_id": session_id}

@api.get("/assistant/history")
async def assistant_history(session_id: str, user: dict = Depends(get_current_user)):
    msgs = await db.assistant_messages.find({"user_id": user["id"], "session_id": session_id}).sort("at", 1).to_list(100)
    return [{"role": m["role"], "text": m["text"]} for m in msgs]

# ---------------- Lives (Fase 3) ----------------
class PresenceIn(BaseModel):
    percent: int = 0

def live_accessible(live: dict, user: dict) -> bool:
    if user["role"] in STAFF_ROLES:
        return True
    stages = live.get("stages")
    if stages:
        return user["current_stage_order"] in stages
    so = live.get("stage_order")
    return so is None or so <= user["current_stage_order"]

async def mandatory_lives_pending(user_id: str, order: int) -> bool:
    req = await db.lives.find({"stage_order": order, "required": True}).to_list(100)
    for l in req:
        a = await db.live_attendance.find_one({"user_id": user_id, "live_id": l["id"], "confirmed": True})
        if not a:
            return True
    return False

@api.get("/lives")
async def get_lives(user: dict = Depends(get_current_user)):
    lives = await db.lives.find().sort("date", 1).to_list(300)
    att = {a["live_id"]: a async for a in db.live_attendance.find({"user_id": user["id"]})}
    buckets = {"live_now": [], "upcoming": [], "recorded": []}
    for l in lives:
        if not live_accessible(l, user):
            continue
        l.pop("_id", None)
        a = att.get(l["id"])
        l["presence_percent"] = a["percent"] if a else 0
        l["presence_confirmed"] = bool(a and a.get("confirmed"))
        key = {"live": "live_now", "scheduled": "upcoming", "upcoming": "upcoming", "ended": "recorded", "recorded": "recorded"}.get(l.get("status"), "upcoming")
        buckets[key].append(l)
    return buckets

@api.post("/lives/{lid}/presence")
async def live_presence(lid: str, body: PresenceIn, user: dict = Depends(get_current_user)):
    l = await db.lives.find_one({"id": lid})
    if not l:
        raise HTTPException(404, "Live não encontrada")
    if not live_accessible(l, user):
        raise HTTPException(403, "Você não tem acesso a esta live")
    minp = l.get("min_presence", 75)
    percent = max(0, min(100, body.percent))
    confirmed = percent >= minp
    await db.live_attendance.update_one(
        {"user_id": user["id"], "live_id": lid},
        {"$set": {"percent": percent, "confirmed": confirmed, "stage_order": l.get("stage_order"), "at": now_iso()},
         "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    return {"ok": True, "confirmed": confirmed, "min_presence": minp, "percent": percent}

# ---------------- Recommendations (IA) ----------------
@api.get("/recommendations")
async def recommendations(user: dict = Depends(get_current_user)):
    order = user["current_stage_order"]
    lessons = await db.lessons.find({"stage_order": order}).sort([("module_id", 1), ("order", 1)]).to_list(500)
    done = {p["lesson_id"] async for p in db.lesson_progress.find({"user_id": user["id"], "completed": True})}
    next_lesson = next(({"id": l["id"], "title": l["title"], "module_title": l.get("module_title")} for l in lessons if l["id"] not in done), None)
    mdone = {d["mission_id"] async for d in db.mission_progress.find({"user_id": user["id"]})}
    mission = None
    for m in await db.missions.find({"active": True}).sort("order", 1).to_list(50):
        if m["id"] not in mdone:
            mission = {"id": m["id"], "title": m["title"]}
            break
    reading = await db.daily_readings.find_one({"kind": "word"})
    if reading:
        reading.pop("_id", None)
    tip = ""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if _LLM_OK and key:
        try:
            stage = await db.stages.find_one({"order": order})
            chat = LlmChat(api_key=key, session_id=f"rec-{user['id']}",
                           system_message="Você é o Assistente de Formação do app católico CAMINHO. Dê UMA sugestão curta (1-2 frases), acolhedora e concreta para o membro avançar hoje na sua etapa. Não invente doutrina. Não use markdown, asteriscos, títulos nem formatação — apenas texto simples. Responda em português do Brasil.").with_model("anthropic", "claude-sonnet-4-6")
            tip = await chat.send_message(UserMessage(text=f"Etapa: {stage['name']} — tema {stage['theme']}. Próxima aula: {next_lesson['title'] if next_lesson else 'todas concluídas'}. Missão pendente: {mission['title'] if mission else 'todas concluídas'}. Dê a sugestão."))
            tip = (tip or "").replace("**", "").replace("##", "").strip()
        except Exception as e:
            logging.error(f"rec tip: {e}")
    return {"next_lesson": next_lesson, "mission": mission, "reading": reading, "tip": tip}

# ---------------- Apologetics / Defesa da Fé ----------------
@api.get("/apologetics")
async def apologetics_list(category: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"category": category} if category else {}
    items = await db.apologetics.find(q).sort("order", 1).to_list(200)
    cats = await db.apologetics.distinct("category")
    return {"categories": sorted(cats), "items": [{k: v for k, v in i.items() if k != "_id"} for i in items]}

@api.get("/apologetics/{aid}")
async def apologetics_detail(aid: str, user: dict = Depends(get_current_user)):
    i = await db.apologetics.find_one({"id": aid})
    if not i:
        raise HTTPException(404, "Conteúdo não encontrado")
    i.pop("_id", None)
    return i

# ---------------- Intelligent search ----------------
@api.get("/search")
async def search(q: str, user: dict = Depends(get_current_user)):
    q = (q or "").strip()
    if len(q) < 2:
        raise HTTPException(400, "Digite ao menos 2 caracteres.")
    rx = {"$regex": q, "$options": "i"}
    max_order = 6 if user["role"] in STAFF_ROLES else user["current_stage_order"]
    lessons = await db.lessons.find({"stage_order": {"$lte": max_order}, "$or": [{"title": rx}, {"content": rx}, {"dimension": rx}]}).to_list(15)
    apol = await db.apologetics.find({"$or": [{"question": rx}, {"answer": rx}, {"category": rx}]}).to_list(15)
    answer = ""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if _LLM_OK and key:
        try:
            chat = LlmChat(api_key=key, session_id=f"search-{user['id']}", system_message=ASSISTANT_SYSTEM).with_model("anthropic", "claude-sonnet-4-6")
            answer = await chat.send_message(UserMessage(text=f"Responda de forma breve (até 4 frases) e fiel ao Magistério, citando fontes: {q}"))
        except Exception as e:
            logging.error(f"search ai: {e}")
    return {
        "lessons": [{"id": l["id"], "title": l["title"], "module_title": l.get("module_title"), "stage_order": l["stage_order"], "dimension": l.get("dimension")} for l in lessons],
        "apologetics": [{"id": a["id"], "question": a["question"], "category": a["category"]} for a in apol],
        "answer": answer,
    }

# ---------------- Passaporte da Jornada ----------------
MILESTONES = [
    ("primeiro_encontro", "Primeiro Encontro", "sparkles", "O início de tudo: o encontro com Cristo."),
    ("primeira_formacao", "Primeira Formação", "book-open", "A primeira aula concluída na caminhada."),
    ("primeira_missao", "Primeira Missão", "flame", "O primeiro passo em missão."),
    ("primeiro_retiro", "Primeiro Retiro", "tent", "O primeiro retiro vivido com a comunidade."),
    ("primeiro_acompanhamento", "Primeiro Acompanhamento", "users", "Vinculado a um formador na caminhada."),
    ("primeira_evangelizacao", "Primeira Evangelização", "megaphone", "O primeiro anúncio a alguém."),
    ("compromisso", "Compromisso", "handshake", "A entrega madura à comunidade e à missão."),
    ("consagracao", "Consagração", "crown", "Permanecer, liderar e gerar novos discípulos."),
]
MILESTONE_KEYS = {m[0] for m in MILESTONES}

async def award(user_id: str, key: str):
    if key not in MILESTONE_KEYS:
        return
    await db.passport_awards.update_one(
        {"user_id": user_id, "milestone_key": key},
        {"$setOnInsert": {"id": str(uuid.uuid4()), "awarded_at": now_iso()}}, upsert=True)

@api.get("/passport")
async def get_passport(user: dict = Depends(get_current_user)):
    earned = {a["milestone_key"]: a async for a in db.passport_awards.find({"user_id": user["id"]})}
    items = []
    for key, title, icon, desc in MILESTONES:
        a = earned.get(key)
        items.append({"key": key, "title": title, "icon": icon, "description": desc,
                      "earned": bool(a), "awarded_at": a["awarded_at"] if a else None})
    return {"items": items, "earned_count": len(earned), "total": len(MILESTONES)}

@api.post("/master/users/{uid}/passport/{key}")
async def master_grant_milestone(uid: str, key: str, master: dict = Depends(require_master)):
    if key not in MILESTONE_KEYS:
        raise HTTPException(404, "Marco inválido")
    await award(uid, key)
    return {"ok": True}

# ---------------- Requisitos configuráveis por etapa (Mestre) ----------------
class StageReqIn(BaseModel):
    require_lessons: bool
    require_mandatory_lives: bool

@api.get("/master/stage-requirements")
async def get_stage_requirements(master: dict = Depends(require_master)):
    stages = await db.stages.find().sort("order", 1).to_list(100)
    out = []
    for s in stages:
        reqs = await stage_reqs(s["order"])
        out.append({"order": s["order"], "name": s["name"], **reqs})
    return out

@api.put("/master/stage-requirements/{order}")
async def set_stage_requirements(order: int, body: StageReqIn, master: dict = Depends(require_master)):
    await db.stage_requirements.update_one({"order": order},
        {"$set": {"order": order, "require_lessons": body.require_lessons, "require_mandatory_lives": body.require_mandatory_lives}}, upsert=True)
    return {"ok": True}

# ---------------- Relatório Pastoral (Mestre) ----------------
@api.get("/master/pastoral-report")
async def pastoral_report(master: dict = Depends(require_master)):
    membros = await db.users.find({"role": "membro"}).to_list(2000)
    stages = {s["order"]: s["name"] async for s in db.stages.find()}
    formadores = {f["id"]: f["name"] async for f in db.users.find({"role": "formador"})}
    by_stage = {}
    awaiting = []
    for m in membros:
        o = m["current_stage_order"]
        fs = await formation_status(m["id"], o)
        b = by_stage.setdefault(o, {"order": o, "stage": stages.get(o, ""), "total": 0, "concluded": 0})
        b["total"] += 1
        if fs["concluded"]:
            b["concluded"] += 1
            awaiting.append({"id": m["id"], "name": m["name"], "order": o, "stage_name": stages.get(o, ""),
                             "formador": formadores.get(m.get("formador_id"), "Sem formador"), "percent": fs["percent"]})
    awaiting.sort(key=lambda x: (x["order"], x["name"]))
    return {"by_stage": sorted(by_stage.values(), key=lambda x: x["order"]),
            "awaiting": awaiting, "awaiting_count": len(awaiting), "total_membros": len(membros)}

# ---------------- PERMISSÕES GRANULARES + GESTÃO DE CONTEÚDO/LIVES ----------------
ALL_PERMISSIONS = [
    "CREATE_COURSE", "EDIT_COURSE", "DELETE_COURSE", "PUBLISH_COURSE",
    "CREATE_MODULE", "EDIT_MODULE", "DELETE_MODULE",
    "CREATE_LESSON", "EDIT_LESSON", "DELETE_LESSON", "PUBLISH_LESSON",
    "UPLOAD_VIDEO", "UPLOAD_AUDIO", "UPLOAD_DOCUMENT",
    "CREATE_ANNOUNCEMENT", "EDIT_ANNOUNCEMENT", "DELETE_ANNOUNCEMENT", "PUBLISH_ANNOUNCEMENT",
    "CREATE_LIVE", "EDIT_LIVE", "START_LIVE", "END_LIVE", "MODERATE_LIVE",
    "VIEW_ANALYTICS", "MANAGE_CONTENT_ACCESS", "EDIT_ALL_CONTENT", "MANAGE_EXTERNAL_MEDIA",
    "MANAGE_LIVE", "MANAGE_CAMERA", "MANAGE_MICROPHONE", "MANAGE_SCENES", "MANAGE_SOURCES",
    "VIEW_LIVE_ANALYTICS", "TAKE_OVER_LIVE",
    # Fase 1 — gestão institucional / RBAC
    "MANAGE_USERS", "CREATE_USERS", "EDIT_USERS", "DELETE_USERS",
    "MANAGE_FOUNDERS", "MANAGE_COFOUNDERS", "MANAGE_FORMADOR_GERAL", "MANAGE_FORMADORES",
    "MANAGE_MEMBERS", "MANAGE_FORMATION", "MANAGE_FORMATION_STAGES", "MANAGE_FORMATION_STAGE",
    "CHANGE_FORMATION_STAGE", "TRANSFER_FORMADOR",
    "VIEW_AUDIT_LOG", "MANAGE_PERMISSIONS", "MANAGE_SETTINGS",
]

# --- Hierarquia institucional (role) — INDEPENDENTE da etapa de formação ---
ROLES = ["admin", "fundador", "cofundador", "formador_geral", "formador", "membro"]
ROLE_RANK = {"admin": 6, "fundador": 5, "cofundador": 4, "formador_geral": 3, "formador": 2, "membro": 1}
ROLE_LABEL = {"admin": "Admin Técnico", "fundador": "Fundador", "cofundador": "Cofundador",
              "formador_geral": "Formador Geral", "formador": "Formador", "membro": "Membro"}
TOP_AUTHORITY = ("admin", "fundador")
STAFF_ROLES = ("admin", "fundador", "cofundador", "formador_geral", "formador")
ADMIN_PROTECTED_MSG = "O administrador técnico possui proteção estrutural e não pode ser alterado por este perfil."

# etapa (order) -> (formation_stage, formation_year)
FORMATION_META = {1: ("PRE_VOCACIONADO", None), 2: ("VOCACIONADO", None), 3: ("DISCIPULO", 1),
                  4: ("DISCIPULO", 2), 5: ("COMPROMISSADO", None), 6: ("CONSAGRADO", None)}
FORMATION_STATUSES = ["ATIVO", "EM_FORMACAO", "PAUSADO", "AFASTADO", "CONCLUIDO"]

CONTENT_PERMS = ["CREATE_COURSE", "EDIT_COURSE", "CREATE_MODULE", "CREATE_LESSON", "EDIT_LESSON",
                 "PUBLISH_LESSON", "PUBLISH_COURSE", "UPLOAD_VIDEO", "UPLOAD_AUDIO", "UPLOAD_DOCUMENT",
                 "CREATE_ANNOUNCEMENT", "DELETE_ANNOUNCEMENT", "MANAGE_EXTERNAL_MEDIA"]
LIVE_PERMS = ["CREATE_LIVE", "EDIT_LIVE", "START_LIVE", "END_LIVE", "MODERATE_LIVE", "MANAGE_LIVE",
              "MANAGE_CAMERA", "MANAGE_MICROPHONE", "MANAGE_SCENES", "MANAGE_SOURCES", "VIEW_LIVE_ANALYTICS"]

ROLE_DEFAULT_PERMS = {
    "cofundador": ["MANAGE_USERS", "CREATE_USERS", "EDIT_USERS", "MANAGE_FORMADOR_GERAL", "MANAGE_FORMADORES",
                   "MANAGE_MEMBERS", "MANAGE_FORMATION", "MANAGE_FORMATION_STAGES", "VIEW_ANALYTICS",
                   "VIEW_AUDIT_LOG", "MANAGE_PERMISSIONS", "TRANSFER_FORMADOR", "EDIT_ALL_CONTENT"] + CONTENT_PERMS + LIVE_PERMS,
    "formador_geral": ["MANAGE_FORMADORES", "TRANSFER_FORMADOR", "MANAGE_FORMATION", "CHANGE_FORMATION_STAGE",
                       "VIEW_ANALYTICS", "EDIT_ALL_CONTENT"] + CONTENT_PERMS + LIVE_PERMS,
    "formador": CONTENT_PERMS + LIVE_PERMS + ["VIEW_ANALYTICS"],
    "membro": [],
}

def role_rank(r): return ROLE_RANK.get(r, 0)
def is_top_authority(u): return u.get("role") in TOP_AUTHORITY
def is_admin_protected(u): return u.get("role") == "admin" or u.get("admin_protected") is True

def effective_perms(user: dict):
    role = user.get("role")

    if role in TOP_AUTHORITY:
        return set(ALL_PERMISSIONS)

    # Formadores possuem permissões explicitamente delegadas.
    # Remover uma permissão deve realmente revogá-la.
    if role == "formador":
        return set(user.get("permissions") or [])

    base = set(ROLE_DEFAULT_PERMS.get(role, []))
    return base | set(user.get("permissions") or [])

def has_perm(user: dict, perm: str) -> bool:
    return perm in effective_perms(user)

def require_perm(perm: str):
    async def dep(user: dict = Depends(get_current_user)):
        if not has_perm(user, perm):
            raise HTTPException(403, f"Permissão necessária: {perm}")
        return user
    return dep

def can_edit(user: dict, doc: dict) -> bool:
    return is_top_authority(user) or doc.get("owner_id") == user["id"] or has_perm(user, "EDIT_ALL_CONTENT")

def can_manage_target(actor: dict, target: dict) -> bool:
    if is_admin_protected(target) and actor.get("role") != "admin":
        return False
    if actor.get("role") == "admin":
        return True
    if actor["id"] == target["id"]:
        return False
    return role_rank(target.get("role")) < role_rank(actor.get("role"))

async def audit(action: str, user: dict, **extra):
    await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "action": action, "by": user["id"],
                                    "by_name": user["name"], "at": now_iso(), **extra})

class CourseIn(BaseModel):
    title: str
    description: str = ""
    category: str = ""
    stages: List[int] = []
    publish: bool = False

class ModuleIn(BaseModel):
    stage_order: int
    title: str
    description: str = ""

class LessonIn(BaseModel):
    module_id: str
    title: str
    content: str = ""
    dimension: str = "Formação"
    duration_min: int = 10
    stage_order: int
    required: bool = False
    video_url: str = ""
    publish: bool = True

class LessonPatch(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class AnnouncementIn(BaseModel):
    title: str
    message: str
    priority: str = "normal"
    stages: List[int] = []
    publish: bool = True
    pinned: bool = False

class LiveIn(BaseModel):
    title: str
    description: str = ""
    date: str = ""
    presenter: str = ""
    stages: List[int] = []
    chat_enabled: bool = True
    required: bool = False
    min_presence: int = 75
    stream_url: str = ""

class LivePatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    stages: Optional[List[int]] = None

class PermsIn(BaseModel):
    permissions: List[str]

# --- catálogo + permissões do usuário ---
@api.get("/permissions/catalog")
async def perms_catalog(user: dict = Depends(get_current_user)):
    return {"permissions": ALL_PERMISSIONS}

@api.get("/master/formadores-permissions")
async def formadores_permissions(master: dict = Depends(require_master)):
    fs = await db.users.find({"role": "formador"}).to_list(500)
    return [{"id": f["id"], "name": f["name"], "email": f["email"], "blocked": f.get("blocked", False),
             "permissions": f.get("permissions") or []} for f in fs]

@api.put("/master/formadores/{fid}/permissions")
async def set_formador_permissions(fid: str, body: PermsIn, master: dict = Depends(require_master)):
    f = await db.users.find_one({"id": fid})
    if not f or f["role"] != "formador":
        raise HTTPException(404, "Formador não encontrado")
    # nunca conceder permissão que o próprio ator não possui; etapas NUNCA são concedidas aqui
    perms = [p for p in body.permissions if p in ALL_PERMISSIONS and p != "MANAGE_FORMATION_STAGE" and has_perm(master, p)]
    await db.users.update_one({"id": fid}, {"$set": {"permissions": perms}})
    await audit("set_permissions", master, target=fid, permissions=perms)
    return {"ok": True, "permissions": perms}

# ================= HIERARQUIA INSTITUCIONAL / RBAC (Fase 1) =================
class RoleChangeIn(BaseModel):
    role: str
    reason: str = ""

class FormationChangeIn(BaseModel):
    new_stage_order: Optional[int] = None
    formation_status: Optional[str] = None
    reason: str

class AssignGeralIn(BaseModel):
    general_formador_id: str
    reason: str = ""

class ResolveReqIn2(BaseModel):
    approve: bool
    reason: str = ""

async def _load_user(uid: str):
    u = await db.users.find_one({"id": uid})
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    return u

@api.get("/me/context")
async def my_context(user: dict = Depends(get_current_user)):
    gname = None
    if user.get("general_formador_id"):
        g = await db.users.find_one({"id": user["general_formador_id"]})
        gname = g["name"] if g else None
    fst, fyr = FORMATION_META.get(user.get("current_stage_order", 1), ("PRE_VOCACIONADO", None))
    return {"role": user["role"], "role_label": ROLE_LABEL.get(user["role"], user["role"]),
            "formation_stage": user.get("formation_stage", fst), "formation_year": user.get("formation_year", fyr),
            "formation_status": user.get("formation_status", "EM_FORMACAO"),
            "general_formador_name": gname, "permissions": sorted(effective_perms(user))}

@api.get("/admin/users")
async def admin_list_users(role: Optional[str] = None, search: Optional[str] = None,
                           actor: dict = Depends(get_current_user)):
    is_fg = actor["role"] == "formador_geral"
    if not (has_perm(actor, "MANAGE_USERS") or is_fg):
        raise HTTPException(403, "Permissão necessária: MANAGE_USERS")
    q = {}
    if role:
        q["role"] = role
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"name": rx}, {"email": rx}]
    users = await db.users.find(q).sort("name", 1).to_list(2000)
    if is_fg:
        # escopo: apenas formadores vinculados + membros desses formadores
        my_formadores = {u["id"] async for u in db.users.find({"role": "formador", "general_formador_id": actor["id"]})}
        users = [u for u in users if u["id"] in my_formadores or u.get("formador_id") in my_formadores]
    return [{"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"],
             "role_label": ROLE_LABEL.get(u["role"], u["role"]),
             "current_stage_order": u.get("current_stage_order"), "formation_stage": u.get("formation_stage"),
             "formation_year": u.get("formation_year"), "formation_status": u.get("formation_status"),
             "admin_protected": is_admin_protected(u), "blocked": u.get("blocked", False),
             "general_formador_id": u.get("general_formador_id"), "formador_id": u.get("formador_id"),
             "manageable": can_manage_target(actor, u)} for u in users]

@api.patch("/admin/users/{uid}/role")
async def change_user_role(uid: str, body: RoleChangeIn, actor: dict = Depends(require_perm("MANAGE_USERS"))):
    target = await _load_user(uid)
    if body.role not in ROLES:
        raise HTTPException(400, "Função inválida.")
    if is_admin_protected(target) and actor["role"] != "admin":
        raise HTTPException(403, ADMIN_PROTECTED_MSG)
    if actor["id"] == uid:
        raise HTTPException(403, "Você não pode alterar a própria função.")
    if not can_manage_target(actor, target):
        raise HTTPException(403, "Você não pode gerenciar este usuário.")
    if body.role == "admin" and actor["role"] != "admin":
        raise HTTPException(403, ADMIN_PROTECTED_MSG)
    if actor["role"] != "admin" and role_rank(body.role) >= role_rank(actor["role"]):
        raise HTTPException(403, "Você não pode atribuir uma função igual ou superior à sua.")
    await db.users.update_one({"id": uid}, {"$set": {"role": body.role}})
    await audit("ROLE_CHANGED", actor, user_id=uid, previous=target["role"], new=body.role, reason=body.reason)
    return {"ok": True, "role": body.role}

@api.put("/admin/users/{uid}/permissions")
async def set_user_permissions(uid: str, body: PermsIn, actor: dict = Depends(require_perm("MANAGE_PERMISSIONS"))):
    target = await _load_user(uid)
    if is_admin_protected(target) and actor["role"] != "admin":
        raise HTTPException(403, ADMIN_PROTECTED_MSG)
    if not can_manage_target(actor, target):
        raise HTTPException(403, "Você não pode gerenciar este usuário.")
    perms = [p for p in body.permissions if p in ALL_PERMISSIONS and p != "MANAGE_FORMATION_STAGE" and has_perm(actor, p)]
    await db.users.update_one({"id": uid}, {"$set": {"permissions": perms}})
    await audit("PERMISSIONS_CHANGED", actor, user_id=uid, permissions=perms)
    return {"ok": True, "permissions": perms}

@api.post("/admin/formadores/{fid}/assign-geral")
async def assign_formador_geral(fid: str, body: AssignGeralIn, actor: dict = Depends(require_perm("MANAGE_FORMADORES"))):
    f = await _load_user(fid)
    if f["role"] != "formador":
        raise HTTPException(400, "O usuário não é um Formador.")
    g = await _load_user(body.general_formador_id)
    if g["role"] != "formador_geral":
        raise HTTPException(400, "O destino não é um Formador Geral.")
    prev = f.get("general_formador_id")
    await db.users.update_one({"id": fid}, {"$set": {"general_formador_id": body.general_formador_id}})
    await db.formador_relationships.insert_one({"id": str(uuid.uuid4()), "formador_id": fid,
        "formador_geral_id": body.general_formador_id, "previous_geral_id": prev,
        "assigned_by": actor["id"], "assigned_at": now_iso(), "status": "active", "reason": body.reason})
    await audit("TRANSFER_FORMADOR", actor, formador_id=fid, previous=prev, new=body.general_formador_id)
    return {"ok": True}

@api.patch("/admin/users/{uid}/formation")
async def change_user_formation(uid: str, body: FormationChangeIn, request: Request, actor: dict = Depends(get_current_user)):
    if not body.reason.strip():
        raise HTTPException(400, "O motivo é obrigatório.")
    if actor["id"] == uid:
        raise HTTPException(403, "Você não pode alterar a própria etapa de formação.")
    target = await _load_user(uid)
    if is_admin_protected(target) and actor["role"] != "admin":
        raise HTTPException(403, ADMIN_PROTECTED_MSG)
    settings = await db.settings.find_one({"key": "app"}) or {}
    requires_approval = settings.get("stage_change_requires_approval", True)
    cofound_can = settings.get("cofundador_can_change_stage", False)
    role = actor["role"]
    direct = False
    if role in ("admin", "fundador"):
        direct = True
    elif role == "cofundador" and cofound_can and has_perm(actor, "CHANGE_FORMATION_STAGE"):
        direct = True
    elif role == "formador_geral" and has_perm(actor, "CHANGE_FORMATION_STAGE"):
        resp = False
        if target.get("role") == "formador":
            resp = target.get("general_formador_id") == actor["id"]
        elif target.get("role") == "membro" and target.get("formador_id"):
            fm = await db.users.find_one({"id": target["formador_id"]})
            resp = bool(fm and fm.get("general_formador_id") == actor["id"])
        if not resp:
            raise HTTPException(403, "Este usuário não está sob a sua responsabilidade.")
        direct = not requires_approval
    else:
        raise HTTPException(403, "Você não tem autoridade para alterar etapas de formação.")
    if body.formation_status:
        if body.formation_status not in FORMATION_STATUSES:
            raise HTTPException(400, "Status inválido.")
        await db.users.update_one({"id": uid}, {"$set": {"formation_status": body.formation_status}})
        await audit("FORMATION_STATUS_CHANGED", actor, user_id=uid, status=body.formation_status)
    if body.new_stage_order is None:
        return {"ok": True, "status": "status_updated" if body.formation_status else "noop"}
    if not (1 <= body.new_stage_order <= 6):
        raise HTTPException(400, "Etapa inválida.")
    if not direct:
        req = {"id": str(uuid.uuid4()), "user_id": uid, "user_name": target["name"],
               "from_order": target["current_stage_order"], "to_order": body.new_stage_order,
               "requested_by": actor["id"], "requested_by_name": actor["name"], "reason": body.reason.strip(),
               "status": "pending", "created_at": now_iso()}
        await db.stage_change_requests.insert_one(req)
        await audit("FORMATION_STAGE_CHANGE_REQUESTED", actor, user_id=uid, to_order=body.new_stage_order)
        async for a in db.users.find({"role": {"$in": ["admin", "fundador"]}}):
            await notify(a["id"], "Solicitação de mudança de etapa", f"{actor['name']} solicitou mudança de etapa para {target['name']}.")
        req.pop("_id", None)
        return {"ok": True, "status": "requested", "request": req}
    ip = request.client.host if request.client else None
    log = await _apply_stage(uid, body.new_stage_order, body.reason, "change", actor, ip)
    return {"ok": True, "status": "applied", "log": log}

@api.get("/formation/stage-requests")
async def list_stage_requests(actor: dict = Depends(require_master)):
    reqs = await db.stage_change_requests.find({"status": "pending"}).sort("created_at", -1).to_list(200)
    for r in reqs:
        r.pop("_id", None)
    return reqs

@api.post("/formation/stage-requests/{rid}/resolve")
async def resolve_stage_request(rid: str, body: ResolveReqIn2, request: Request, actor: dict = Depends(require_master)):
    r = await db.stage_change_requests.find_one({"id": rid})
    if not r:
        raise HTTPException(404, "Solicitação não encontrada")
    if r["status"] != "pending":
        raise HTTPException(400, "Solicitação já resolvida.")
    if not body.approve:
        await db.stage_change_requests.update_one({"id": rid}, {"$set": {"status": "rejected", "resolved_by": actor["id"], "resolved_at": now_iso(), "resolution_reason": body.reason}})
        await audit("FORMATION_STAGE_CHANGE_REJECTED", actor, request_id=rid)
        await notify(r["requested_by"], "Solicitação recusada", f"A mudança de etapa de {r['user_name']} foi recusada.")
        return {"ok": True, "status": "rejected"}
    ip = request.client.host if request.client else None
    log = await _apply_stage(r["user_id"], r["to_order"], r.get("reason") or (body.reason or "Aprovado"), "change", actor, ip)
    await db.stage_change_requests.update_one({"id": rid}, {"$set": {"status": "approved", "resolved_by": actor["id"], "resolved_at": now_iso()}})
    await audit("FORMATION_STAGE_CHANGE_APPROVED", actor, request_id=rid)
    await notify(r["requested_by"], "Solicitação aprovada", f"A mudança de etapa de {r['user_name']} foi aprovada.")
    return {"ok": True, "status": "approved", "log": log}

# --- cursos ---
@api.post("/courses")
async def create_course(body: CourseIn, user: dict = Depends(require_perm("CREATE_COURSE"))):
    doc = {"id": str(uuid.uuid4()), "title": body.title, "description": body.description, "category": body.category,
           "stages": body.stages, "owner_id": user["id"], "owner_name": user["name"],
           "status": "published" if body.publish else "draft", "created_at": now_iso()}
    await db.courses.insert_one(doc)
    await audit("create_course", user, course_id=doc["id"])
    doc.pop("_id", None)
    return doc

@api.get("/courses")
async def list_courses(user: dict = Depends(get_current_user)):
    if user["role"] in STAFF_ROLES:
        items = await db.courses.find().sort("created_at", -1).to_list(500)
    else:
        items = await db.courses.find({"status": "published"}).to_list(500)
        items = [c for c in items if not c.get("stages") or user["current_stage_order"] in c["stages"]]
    for c in items:
        c.pop("_id", None)
    return items

# --- módulos/aulas (autoria) ---
@api.post("/modules")
async def create_module(body: ModuleIn, user: dict = Depends(require_perm("CREATE_MODULE"))):
    count = await db.modules.count_documents({"stage_order": body.stage_order})
    doc = {"id": str(uuid.uuid4()), "stage_order": body.stage_order, "order": count + 1,
           "title": body.title, "description": body.description, "owner_id": user["id"]}
    await db.modules.insert_one(doc)
    await audit("create_module", user, module_id=doc["id"])
    doc.pop("_id", None)
    return doc

@api.post("/lessons")
async def create_lesson(body: LessonIn, user: dict = Depends(require_perm("CREATE_LESSON"))):
    m = await db.modules.find_one({"id": body.module_id})
    if not m:
        raise HTTPException(404, "Módulo não encontrado")
    count = await db.lessons.count_documents({"module_id": body.module_id})
    doc = {"id": str(uuid.uuid4()), "module_id": body.module_id, "module_title": m["title"],
           "stage_order": body.stage_order, "order": count + 1, "title": body.title,
           "dimension": body.dimension, "duration_min": body.duration_min, "video_url": body.video_url,
           "content": body.content, "required": body.required, "owner_id": user["id"],
           "status": "published" if body.publish else "draft"}
    await db.lessons.insert_one(doc)
    await audit("create_lesson", user, lesson_id=doc["id"])
    doc.pop("_id", None)
    return doc

@api.patch("/lessons/{lid}")
async def edit_lesson(lid: str, body: LessonPatch, user: dict = Depends(require_perm("EDIT_LESSON"))):
    l = await db.lessons.find_one({"id": lid})
    if not l:
        raise HTTPException(404, "Aula não encontrada")
    if not can_edit(user, l):
        raise HTTPException(403, "Você só pode editar seus próprios conteúdos.")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.lessons.update_one({"id": lid}, {"$set": updates})
        await audit("edit_lesson", user, lesson_id=lid)
    return {"ok": True}

# --- avisos ---
@api.post("/announcements")
async def create_announcement(body: AnnouncementIn, user: dict = Depends(require_perm("CREATE_ANNOUNCEMENT"))):
    doc = {"id": str(uuid.uuid4()), "title": body.title, "message": body.message, "priority": body.priority,
           "stages": body.stages, "pinned": body.pinned, "owner_id": user["id"], "owner_name": user["name"],
           "status": "published" if body.publish else "draft", "created_at": now_iso()}
    await db.announcements.insert_one(doc)
    await audit("create_announcement", user, announcement_id=doc["id"])
    doc.pop("_id", None)
    return doc

@api.get("/announcements")
async def list_announcements(user: dict = Depends(get_current_user)):
    if user["role"] in STAFF_ROLES:
        items = await db.announcements.find().sort([("pinned", -1), ("created_at", -1)]).to_list(200)
    else:
        items = await db.announcements.find({"status": "published"}).sort([("pinned", -1), ("created_at", -1)]).to_list(200)
        items = [a for a in items if not a.get("stages") or user["current_stage_order"] in a["stages"]]
    for a in items:
        a.pop("_id", None)
    return items

@api.delete("/announcements/{aid}")
async def delete_announcement(aid: str, user: dict = Depends(require_perm("DELETE_ANNOUNCEMENT"))):
    a = await db.announcements.find_one({"id": aid})
    if not a:
        raise HTTPException(404, "Aviso não encontrado")
    if not can_edit(user, a):
        raise HTTPException(403, "Você só pode remover seus próprios avisos.")
    await db.announcements.delete_one({"id": aid})
    await audit("delete_announcement", user, announcement_id=aid)
    return {"ok": True}

# --- lives: criar / editar / iniciar / encerrar ---
@api.post("/lives")
async def create_live(body: LiveIn, user: dict = Depends(require_perm("CREATE_LIVE"))):
    doc = {"id": str(uuid.uuid4()), "title": body.title, "description": body.description,
           "date": body.date or now_iso(), "former": body.presenter or user["name"], "presenter": body.presenter or user["name"],
           "stages": body.stages, "stage_order": (body.stages[0] if body.stages else None),
           "chat_enabled": body.chat_enabled, "required": body.required, "min_presence": body.min_presence,
           "stream_url": body.stream_url, "status": "scheduled", "owner_id": user["id"], "created_at": now_iso()}
    await db.lives.insert_one(doc)
    await audit("create_live", user, live_id=doc["id"])
    doc.pop("_id", None)
    return doc

@api.patch("/lives/{lid}")
async def edit_live(lid: str, body: LivePatch, user: dict = Depends(require_perm("EDIT_LIVE"))):
    l = await db.lives.find_one({"id": lid})
    if not l:
        raise HTTPException(404, "Live não encontrada")
    if not can_edit(user, l):
        raise HTTPException(403, "Você só pode editar suas próprias lives.")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "stages" in updates:
        updates["stage_order"] = updates["stages"][0] if updates["stages"] else None
    if updates:
        await db.lives.update_one({"id": lid}, {"$set": updates})
        await audit("edit_live", user, live_id=lid)
    return {"ok": True}

@api.post("/lives/{lid}/start")
async def start_live(lid: str, user: dict = Depends(require_perm("START_LIVE"))):
    l = await db.lives.find_one({"id": lid})
    if not l:
        raise HTTPException(404, "Live não encontrada")
    if not can_edit(user, l):
        raise HTTPException(403, "Você não é responsável por esta live.")
    await db.lives.update_one({"id": lid}, {"$set": {"status": "live", "started_at": now_iso()}})
    await audit("start_live", user, live_id=lid)
    # notifica membros autorizados
    stages = l.get("stages") or ([l["stage_order"]] if l.get("stage_order") else [])
    q = {"role": "membro"} if not stages else {"role": "membro", "current_stage_order": {"$in": stages}}
    async for m in db.users.find(q):
        await notify(m["id"], "🔴 Ao vivo agora", f"A live '{l['title']}' começou. Entre na transmissão.")
    return {"ok": True, "status": "live"}

@api.post("/lives/{lid}/end")
async def end_live(lid: str, user: dict = Depends(require_perm("END_LIVE"))):
    l = await db.lives.find_one({"id": lid})
    if not l:
        raise HTTPException(404, "Live não encontrada")
    if not can_edit(user, l):
        raise HTTPException(403, "Você não é responsável por esta live.")
    started = l.get("started_at")
    dur = None
    if started:
        try:
            dur = int((datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds() // 60)
        except Exception:
            dur = None
    await db.lives.update_one({"id": lid}, {"$set": {"status": "ended", "ended_at": now_iso(), "duration_min": dur}})
    await audit("end_live", user, live_id=lid, duration_min=dur)
    return {"ok": True, "status": "ended", "duration_min": dur}

# ================= CENTRAL DE MÍDIA EXTERNA (embed oficial) =================
# Só armazena URL/provider/ID/metadados. NUNCA baixa, copia ou faz scraping de vídeo.
# Arquitetura de adaptadores pronta para futuros provedores/APIs oficiais.

LIVE_STATUSES = ["draft", "scheduled", "waiting", "live", "ended", "unavailable"]

class MediaProvider:
    key = "base"
    name = "Base"
    embeddable = True
    _patterns: List = []

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(p.search(url) for p in cls._patterns)

    @classmethod
    def extract_id(cls, url: str) -> Optional[str]:
        for p in cls._patterns:
            m = p.search(url)
            if m:
                return m.group(1)
        return None

    @classmethod
    def embed_url(cls, ext_id: str) -> str:
        raise NotImplementedError

    @classmethod
    def watch_url(cls, ext_id: str) -> str:
        raise NotImplementedError

    @classmethod
    def thumbnail(cls, ext_id: str) -> str:
        return ""


class YouTubeProvider(MediaProvider):
    key = "youtube"
    name = "YouTube"
    embeddable = True
    _patterns = [
        re.compile(r"(?:youtube\.com/watch\?(?:.*&)?v=)([\w-]{11})"),
        re.compile(r"(?:youtu\.be/)([\w-]{11})"),
        re.compile(r"(?:youtube\.com/live/)([\w-]{11})"),
        re.compile(r"(?:youtube\.com/embed/)([\w-]{11})"),
        re.compile(r"(?:youtube\.com/shorts/)([\w-]{11})"),
    ]

    @classmethod
    def embed_url(cls, ext_id: str) -> str:
        return f"https://www.youtube.com/embed/{ext_id}"

    @classmethod
    def watch_url(cls, ext_id: str) -> str:
        return f"https://www.youtube.com/watch?v={ext_id}"

    @classmethod
    def thumbnail(cls, ext_id: str) -> str:
        return f"https://img.youtube.com/vi/{ext_id}/hqdefault.jpg"


class VimeoProvider(MediaProvider):
    key = "vimeo"
    name = "Vimeo"
    embeddable = True
    _patterns = [
        re.compile(r"(?:player\.vimeo\.com/video/)(\d+)"),
        re.compile(r"(?:vimeo\.com/)(\d+)"),
    ]

    @classmethod
    def embed_url(cls, ext_id: str) -> str:
        return f"https://player.vimeo.com/video/{ext_id}"

    @classmethod
    def watch_url(cls, ext_id: str) -> str:
        return f"https://vimeo.com/{ext_id}"


PROVIDERS = [YouTubeProvider, VimeoProvider]

async def enabled_providers() -> List[str]:
    s = await db.settings.find_one({"key": "media_providers"})
    if not s:
        return [p.key for p in PROVIDERS]
    return s.get("enabled", [p.key for p in PROVIDERS])

def resolve_provider(url: str):
    for p in PROVIDERS:
        if p.matches(url):
            ext_id = p.extract_id(url)
            if ext_id:
                return p, ext_id
    return None, None

async def parse_media_url(url: str) -> dict:
    url = (url or "").strip()
    if not url or not re.match(r"^https?://", url):
        raise HTTPException(400, "URL inválida. Informe um link http(s) completo.")
    prov, ext_id = resolve_provider(url)
    if not prov:
        raise HTTPException(400, "Provedor não suportado. Use YouTube ou Vimeo (links oficiais).")
    if prov.key not in await enabled_providers():
        raise HTTPException(400, f"O provedor {prov.name} está desativado pelo Login Mestre.")
    return {
        "provider": prov.key, "provider_name": prov.name, "external_id": ext_id,
        "embed_url": prov.embed_url(ext_id), "watch_url": prov.watch_url(ext_id),
        "can_embed": prov.embeddable, "thumbnail": prov.thumbnail(ext_id),
    }

def media_public(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc

def media_accessible(user: dict, doc: dict) -> bool:
    if user["role"] in STAFF_ROLES:
        return True
    if doc.get("status") != "published":
        return False
    st = doc.get("stages") or []
    return (not st) or (user["current_stage_order"] in st)

class ExternalMediaIn(BaseModel):
    url: str
    title: str
    description: str = ""
    kind: str = "video"          # "video" | "live"
    category: str = ""
    thumbnail: str = ""
    stages: List[int] = []
    scheduled_at: str = ""
    live_status: str = "scheduled"
    chat_enabled: bool = False
    publish: bool = True

class ExternalMediaPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail: Optional[str] = None
    stages: Optional[List[int]] = None
    scheduled_at: Optional[str] = None
    publish: Optional[bool] = None

class LiveStatusIn(BaseModel):
    live_status: str

class ProvidersIn(BaseModel):
    enabled: List[str]

# --- provedores (config do Mestre) ---
@api.get("/media/providers")
async def get_media_providers(user: dict = Depends(get_current_user)):
    enabled = await enabled_providers()
    return {"providers": [{"key": p.key, "name": p.name, "embeddable": p.embeddable,
                           "enabled": p.key in enabled} for p in PROVIDERS]}

@api.put("/master/media/providers")
async def set_media_providers(body: ProvidersIn, master: dict = Depends(require_master)):
    enabled = [k for k in body.enabled if k in [p.key for p in PROVIDERS]]
    await db.settings.update_one({"key": "media_providers"},
                                 {"$set": {"key": "media_providers", "enabled": enabled}}, upsert=True)
    await audit("set_media_providers", master, enabled=enabled)
    return {"ok": True, "enabled": enabled}

# --- validação/normalização de URL ---
@api.post("/media/parse")
async def media_parse(body: dict, user: dict = Depends(require_perm("MANAGE_EXTERNAL_MEDIA"))):
    return await parse_media_url(body.get("url", ""))

# --- CRUD mídia externa ---
@api.post("/external-media")
async def create_external_media(body: ExternalMediaIn, user: dict = Depends(require_perm("MANAGE_EXTERNAL_MEDIA"))):
    info = await parse_media_url(body.url)
    if body.kind == "live" and body.live_status not in LIVE_STATUSES:
        raise HTTPException(400, "Status de live inválido.")
    doc = {
        "id": str(uuid.uuid4()), "title": body.title, "description": body.description,
        "kind": body.kind, "category": body.category,
        "source_url": body.url, "provider": info["provider"], "provider_name": info["provider_name"],
        "external_id": info["external_id"], "embed_url": info["embed_url"], "watch_url": info["watch_url"],
        "can_embed": info["can_embed"], "thumbnail": body.thumbnail or info["thumbnail"],
        "stages": body.stages, "scheduled_at": body.scheduled_at,
        "live_status": body.live_status if body.kind == "live" else None,
        "chat_enabled": body.chat_enabled,
        "status": "published" if body.publish else "draft",
        "owner_id": user["id"], "owner_name": user["name"], "created_at": now_iso(),
    }
    await db.external_media.insert_one(doc)
    await audit("create_external_media", user, media_id=doc["id"], provider=info["provider"])
    return media_public(doc)

@api.get("/external-media")
async def list_external_media(kind: Optional[str] = None, q: Optional[str] = None,
                              user: dict = Depends(get_current_user)):
    query = {}
    if kind in ("video", "live"):
        query["kind"] = kind
    items = await db.external_media.find(query).sort("created_at", -1).to_list(500)
    out = []
    for m in items:
        if not media_accessible(user, m):
            continue
        if q and q.lower() not in (m.get("title", "") + " " + m.get("description", "") + " " + m.get("category", "")).lower():
            continue
        out.append(media_public(m))
    return out

@api.get("/external-media/favorites")
async def media_favorites(user: dict = Depends(get_current_user)):
    favs = await db.media_favorites.find({"user_id": user["id"]}).to_list(500)
    ids = [f["media_id"] for f in favs]
    items = await db.external_media.find({"id": {"$in": ids}}).to_list(500)
    return [media_public(m) for m in items if media_accessible(user, m)]

@api.get("/external-media/history")
async def media_history(user: dict = Depends(get_current_user)):
    hist = await db.media_history.find({"user_id": user["id"]}).sort("accessed_at", -1).to_list(50)
    ids = [h["media_id"] for h in hist]
    items = {m["id"]: m async for m in db.external_media.find({"id": {"$in": ids}})}
    out = []
    for h in hist:
        m = items.get(h["media_id"])
        if m and media_accessible(user, m):
            d = media_public(m)
            d["accessed_at"] = h["accessed_at"]
            out.append(d)
    return out

@api.get("/external-media/{mid}")
async def get_external_media(mid: str, user: dict = Depends(get_current_user)):
    m = await db.external_media.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Mídia não encontrada")
    if not media_accessible(user, m):
        raise HTTPException(403, "Este conteúdo não está liberado para a sua etapa atual.")
    fav = await db.media_favorites.find_one({"user_id": user["id"], "media_id": mid})
    # registra "acessado" (progresso mínimo sem evento oficial do player)
    await db.media_history.update_one(
        {"user_id": user["id"], "media_id": mid},
        {"$set": {"accessed_at": now_iso()}, "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    d = media_public(m)
    d["favorited"] = bool(fav)
    return d

@api.patch("/external-media/{mid}")
async def edit_external_media(mid: str, body: ExternalMediaPatch, user: dict = Depends(require_perm("MANAGE_EXTERNAL_MEDIA"))):
    m = await db.external_media.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Mídia não encontrada")
    if not can_edit(user, m):
        raise HTTPException(403, "Você só pode editar suas próprias mídias.")
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "publish"}
    if body.publish is not None:
        updates["status"] = "published" if body.publish else "draft"
    if updates:
        await db.external_media.update_one({"id": mid}, {"$set": updates})
        await audit("edit_external_media", user, media_id=mid)
    return {"ok": True}

@api.delete("/external-media/{mid}")
async def delete_external_media(mid: str, user: dict = Depends(require_perm("MANAGE_EXTERNAL_MEDIA"))):
    m = await db.external_media.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Mídia não encontrada")
    if not can_edit(user, m):
        raise HTTPException(403, "Você só pode remover suas próprias mídias.")
    await db.external_media.delete_one({"id": mid})
    await audit("delete_external_media", user, media_id=mid)
    return {"ok": True}

@api.post("/external-media/{mid}/live-status")
async def set_media_live_status(mid: str, body: LiveStatusIn, user: dict = Depends(require_perm("MANAGE_EXTERNAL_MEDIA"))):
    m = await db.external_media.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Mídia não encontrada")
    if m.get("kind") != "live":
        raise HTTPException(400, "Esta mídia não é uma live externa.")
    if not can_edit(user, m):
        raise HTTPException(403, "Você não é responsável por esta live.")
    if body.live_status not in LIVE_STATUSES:
        raise HTTPException(400, "Status de live inválido.")
    await db.external_media.update_one({"id": mid}, {"$set": {"live_status": body.live_status}})
    await audit("set_media_live_status", user, media_id=mid, live_status=body.live_status)
    if body.live_status == "live":
        stages = m.get("stages") or []
        q = {"role": "membro"} if not stages else {"role": "membro", "current_stage_order": {"$in": stages}}
        async for mm in db.users.find(q):
            await notify(mm["id"], "🔴 Live externa ao vivo", f"'{m['title']}' está ao vivo agora.")
    return {"ok": True, "live_status": body.live_status}

@api.post("/external-media/{mid}/favorite")
async def toggle_media_favorite(mid: str, user: dict = Depends(get_current_user)):
    m = await db.external_media.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Mídia não encontrada")
    if not media_accessible(user, m):
        raise HTTPException(403, "Conteúdo não liberado para a sua etapa.")
    existing = await db.media_favorites.find_one({"user_id": user["id"], "media_id": mid})
    if existing:
        await db.media_favorites.delete_one({"user_id": user["id"], "media_id": mid})
        return {"ok": True, "favorited": False}
    if not media_accessible(user, m):
        raise HTTPException(403, "Conteúdo não liberado para a sua etapa.")
    await db.media_favorites.insert_one({"id": str(uuid.uuid4()), "user_id": user["id"], "media_id": mid, "at": now_iso()})
    return {"ok": True, "favorited": True}

# ================= CENTRAL DE TRANSMISSÃO AO VIVO (LiveKit WebRTC) =================
# Captura via APIs oficiais do navegador (getUserMedia/getDisplayMedia) no frontend.
# Streaming via LiveKit SFU. Tokens curtos gerados SÓ no backend. Segredos nunca no frontend.
try:
    from livekit import api as lk_api
    _LK_OK = True
except Exception:
    _LK_OK = False

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")

def livekit_configured() -> bool:
    return bool(_LK_OK and LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET)

def lk_client():
    return lk_api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)

def broadcast_accessible(user: dict, b: dict) -> bool:
    if user["role"] in STAFF_ROLES:
        return True
    st = b.get("stages") or []
    return (not st) or (user["current_stage_order"] in st)

def can_operate_broadcast(user: dict, b: dict) -> bool:
    # dono, apresentador atual, ou EDIT_ALL_CONTENT/mestre
    return (is_top_authority(user) or b.get("owner_id") == user["id"]
            or b.get("presenter_id") == user["id"] or has_perm(user, "EDIT_ALL_CONTENT"))

class BroadcastIn(BaseModel):
    title: str
    description: str = ""
    stages: List[int] = []
    scheduled_at: str = ""
    preset: str = ""
    mode: str = "simple"   # "simple" | "pro"

class BroadcastPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[List[int]] = None
    scheduled_at: Optional[str] = None
    preset: Optional[str] = None
    mode: Optional[str] = None

class ChatMsgIn(BaseModel):
    text: str

DEFAULT_SCENE = {"layout": "full", "lower_third": {"name": "", "role": "", "visible": False},
                 "banner": {"text": "", "visible": False}}

class Overlay(BaseModel):
    layout: str = "full"
    lower_third: dict = Field(default_factory=lambda: {"name": "", "role": "", "visible": False})
    banner: dict = Field(default_factory=lambda: {"text": "", "visible": False})

class ScenesIn(BaseModel):
    scenes: List[dict] = []

def broadcast_public(b: dict) -> dict:
    b = dict(b)
    b.pop("_id", None)
    return b

@api.get("/broadcasts")
async def list_broadcasts(user: dict = Depends(get_current_user)):
    staff = user["role"] in STAFF_ROLES
    items = await db.broadcasts.find().sort("created_at", -1).to_list(300)
    reminded = set(await db.broadcast_reminders.distinct("broadcast_id", {"user_id": user["id"]}))
    out = []
    for b in items:
        if not broadcast_accessible(user, b):
            continue
        if not staff and b.get("status") not in ("live", "scheduled"):
            continue
        d = broadcast_public(b)
        d["reminded"] = b["id"] in reminded
        out.append(d)
    return out

@api.post("/broadcasts")
async def create_broadcast(body: BroadcastIn, user: dict = Depends(require_perm("CREATE_LIVE"))):
    bid = str(uuid.uuid4())
    doc = {
        "id": bid, "title": body.title, "description": body.description,
        "stages": body.stages, "scheduled_at": body.scheduled_at, "preset": body.preset,
        "mode": body.mode if body.mode in ("simple", "pro") else "simple",
        "status": "scheduled" if body.scheduled_at else "idle", "room_name": f"caminho-{bid[:8]}",
        "owner_id": user["id"], "owner_name": user["name"],
        "presenter_id": user["id"], "presenter_name": user["name"],
        "chat_enabled": True, "created_at": now_iso(),
        "started_at": None, "ended_at": None,
        "viewers_peak": 0, "duration_min": None,
        "scenes": [], "active_scene": dict(DEFAULT_SCENE),
    }
    await db.broadcasts.insert_one(doc)
    await audit("create_broadcast", user, broadcast_id=bid)
    return broadcast_public(doc)

@api.get("/broadcasts/{bid}")
async def get_broadcast(bid: str, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not broadcast_accessible(user, b):
        raise HTTPException(403, "Esta transmissão não está liberada para a sua etapa atual.")
    d = broadcast_public(b)
    d["reminded"] = bool(await db.broadcast_reminders.find_one({"broadcast_id": bid, "user_id": user["id"]}))
    return d

@api.patch("/broadcasts/{bid}")
async def edit_broadcast(bid: str, body: BroadcastPatch, user: dict = Depends(require_perm("EDIT_LIVE"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not can_operate_broadcast(user, b):
        raise HTTPException(403, "Você só pode editar suas próprias transmissões.")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.broadcasts.update_one({"id": bid}, {"$set": updates})
        await audit("edit_broadcast", user, broadcast_id=bid)
    return {"ok": True}

@api.delete("/broadcasts/{bid}")
async def delete_broadcast(bid: str, user: dict = Depends(require_perm("MANAGE_LIVE"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not can_operate_broadcast(user, b):
        raise HTTPException(403, "Você só pode remover suas próprias transmissões.")
    await db.broadcasts.delete_one({"id": bid})
    await audit("delete_broadcast", user, broadcast_id=bid)
    return {"ok": True}

@api.post("/broadcasts/{bid}/start")
async def start_broadcast(bid: str, user: dict = Depends(require_perm("START_LIVE"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not can_operate_broadcast(user, b):
        raise HTTPException(403, "Você não é responsável por esta transmissão.")
    if livekit_configured():
        try:
            async with lk_client() as lk:
                await lk.room.create_room(lk_api.CreateRoomRequest(name=b["room_name"], empty_timeout=600, max_participants=1000))
        except Exception as e:
            logging.warning(f"LiveKit create_room: {e}")
    await db.broadcasts.update_one({"id": bid}, {"$set": {"status": "live", "started_at": now_iso()}})
    await audit("start_broadcast", user, broadcast_id=bid)
    # AVISO AUTOMÁTICO: notifica membros da(s) etapa(s) autorizada(s)
    stages = b.get("stages") or []
    q = {"role": "membro"} if not stages else {"role": "membro", "current_stage_order": {"$in": stages}}
    async for m in db.users.find(q):
        await notify(m["id"], "🔴 Estamos ao vivo!", f"A transmissão '{b['title']}' começou. Entre agora.")
    return {"ok": True, "status": "live"}

@api.post("/broadcasts/{bid}/end")
async def end_broadcast(bid: str, user: dict = Depends(require_perm("END_LIVE"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not can_operate_broadcast(user, b):
        raise HTTPException(403, "Você não é responsável por esta transmissão.")
    dur = None
    if b.get("started_at"):
        try:
            dur = int((datetime.now(timezone.utc) - datetime.fromisoformat(b["started_at"])).total_seconds() // 60)
        except Exception:
            dur = None
    if livekit_configured():
        try:
            async with lk_client() as lk:
                await lk.room.delete_room(lk_api.DeleteRoomRequest(room=b["room_name"]))
        except Exception as e:
            logging.warning(f"LiveKit delete_room: {e}")
    await db.broadcasts.update_one({"id": bid}, {"$set": {"status": "ended", "ended_at": now_iso(), "duration_min": dur}})
    await audit("end_broadcast", user, broadcast_id=bid, duration_min=dur)
    return {"ok": True, "status": "ended", "duration_min": dur}

@api.post("/broadcasts/{bid}/takeover")
async def takeover_broadcast(bid: str, user: dict = Depends(require_perm("TAKE_OVER_LIVE"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    await db.broadcasts.update_one({"id": bid}, {"$set": {"presenter_id": user["id"], "presenter_name": user["name"]}})
    await audit("takeover_broadcast", user, broadcast_id=bid, note="Transmissão assumida pelo Login Mestre.")
    if b.get("owner_id"):
        await notify(b["owner_id"], "Transmissão assumida", f"O Login Mestre assumiu a transmissão '{b['title']}'.")
    return {"ok": True, "presenter_name": user["name"]}

@api.post("/broadcasts/{bid}/token")
async def broadcast_token(bid: str, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not livekit_configured():
        raise HTTPException(503, "Serviço de transmissão não configurado. Informe as credenciais do LiveKit ao Login Mestre.")
    # papel derivado no backend (nunca confiar no cliente)
    is_operator = can_operate_broadcast(user, b) and has_perm(user, "START_LIVE")
    if not is_operator:
        if not broadcast_accessible(user, b):
            raise HTTPException(403, "Esta transmissão não está liberada para a sua etapa.")
        if b.get("status") != "live":
            raise HTTPException(403, "A transmissão ainda não está ao vivo.")
        if await db.broadcast_bans.find_one({"broadcast_id": bid, "user_id": user["id"]}):
            raise HTTPException(403, "Você foi bloqueado desta transmissão.")
    grants = lk_api.VideoGrants(
        room_join=True, room=b["room_name"], can_subscribe=True,
        can_publish=is_operator, can_publish_data=is_operator,
    )
    token = (lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
             .with_ttl(timedelta(minutes=15))
             .with_identity(user["id"]).with_name(user["name"])
             .with_grants(grants).to_jwt())
    return {"token": token, "server_url": LIVEKIT_URL, "room": b["room_name"],
            "role": "broadcaster" if is_operator else "viewer"}

# --- presença/espectadores (heartbeat) ---
@api.post("/broadcasts/{bid}/heartbeat")
async def broadcast_heartbeat(bid: str, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    await db.broadcast_presence.update_one(
        {"broadcast_id": bid, "user_id": user["id"]},
        {"$set": {"at": now_iso(), "name": user["name"]}, "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    count = await db.broadcast_presence.count_documents({"broadcast_id": bid, "at": {"$gt": cutoff}})
    if count > (b.get("viewers_peak") or 0):
        await db.broadcasts.update_one({"id": bid}, {"$set": {"viewers_peak": count}})
    return {"viewers": count, "viewers_peak": max(count, b.get("viewers_peak") or 0),
            "active_scene": b.get("active_scene") or dict(DEFAULT_SCENE)}

@api.get("/broadcasts/{bid}/stats")
async def broadcast_stats(bid: str, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    count = await db.broadcast_presence.count_documents({"broadcast_id": bid, "at": {"$gt": cutoff}})
    return {"viewers": count, "viewers_peak": b.get("viewers_peak") or 0,
            "status": b.get("status"), "started_at": b.get("started_at"),
            "duration_min": b.get("duration_min"), "presenter_name": b.get("presenter_name"),
            "active_scene": b.get("active_scene") or dict(DEFAULT_SCENE)}

# --- Fase 2: cenas e overlays (produção visual) ---
@api.put("/broadcasts/{bid}/scenes")
async def save_scenes(bid: str, body: ScenesIn, user: dict = Depends(require_perm("MANAGE_SCENES"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not can_operate_broadcast(user, b):
        raise HTTPException(403, "Você não é responsável por esta transmissão.")
    await db.broadcasts.update_one({"id": bid}, {"$set": {"scenes": body.scenes}})
    return {"ok": True, "scenes": body.scenes}

@api.post("/broadcasts/{bid}/active-scene")
async def set_active_scene(bid: str, body: Overlay, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not can_operate_broadcast(user, b):
        raise HTTPException(403, "Você não é responsável por esta transmissão.")
    scene = {"layout": body.layout, "lower_third": body.lower_third, "banner": body.banner}
    await db.broadcasts.update_one({"id": bid}, {"$set": {"active_scene": scene}})
    return {"ok": True, "active_scene": scene}

# --- badge ao vivo (dashboard) ---
@api.get("/live-broadcasts")
async def live_broadcasts(user: dict = Depends(get_current_user)):
    items = await db.broadcasts.find({"status": "live"}).sort("started_at", -1).to_list(50)
    return [broadcast_public(b) for b in items if broadcast_accessible(user, b)]

# --- agenda: lembrar-me ---
@api.post("/broadcasts/{bid}/remind")
async def remind_broadcast(bid: str, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not broadcast_accessible(user, b):
        raise HTTPException(403, "Sem acesso a esta transmissão.")
    existing = await db.broadcast_reminders.find_one({"broadcast_id": bid, "user_id": user["id"]})
    if existing:
        await db.broadcast_reminders.delete_one({"broadcast_id": bid, "user_id": user["id"]})
        return {"ok": True, "reminded": False}
    await db.broadcast_reminders.insert_one({"id": str(uuid.uuid4()), "broadcast_id": bid,
        "user_id": user["id"], "notified": False, "at": now_iso()})
    return {"ok": True, "reminded": True}

# --- cron: lembretes de lives agendadas (dispara ~15 min antes) ---
async def _process_broadcast_reminders():
    now = datetime.now(timezone.utc)
    window = (now + timedelta(minutes=15)).isoformat()
    now_s = now.isoformat()
    async for b in db.broadcasts.find({"status": "scheduled", "scheduled_at": {"$gt": now_s, "$lte": window}}):
        async for r in db.broadcast_reminders.find({"broadcast_id": b["id"], "notified": False}):
            await notify(r["user_id"], "📺 Sua live começa em breve", f"'{b['title']}' começa em poucos minutos.")
            await db.broadcast_reminders.update_one({"id": r["id"]}, {"$set": {"notified": True}})

@api.post("/cron/broadcast-reminders")
async def cron_broadcast_reminders(request: Request, background: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not secrets.compare_digest(token, secret):
        raise HTTPException(401, "Não autorizado")
    background.add_task(_process_broadcast_reminders)
    return {"ok": True}

# --- chat + moderação ---
@api.get("/broadcasts/{bid}/chat")
async def get_chat(bid: str, since: Optional[str] = None, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not broadcast_accessible(user, b):
        raise HTTPException(403, "Sem acesso a esta transmissão.")
    q = {"broadcast_id": bid, "deleted": {"$ne": True}}
    if since:
        q["at"] = {"$gt": since}
    msgs = await db.broadcast_chat.find(q).sort("at", 1).to_list(200)
    for m in msgs:
        m.pop("_id", None)
    return {"messages": msgs, "chat_enabled": b.get("chat_enabled", True)}

@api.post("/broadcasts/{bid}/chat")
async def post_chat(bid: str, body: ChatMsgIn, user: dict = Depends(get_current_user)):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    if not broadcast_accessible(user, b):
        raise HTTPException(403, "Sem acesso a esta transmissão.")
    if not b.get("chat_enabled", True):
        raise HTTPException(403, "O chat está desativado.")
    if await db.broadcast_bans.find_one({"broadcast_id": bid, "user_id": user["id"]}):
        raise HTTPException(403, "Você foi bloqueado do chat.")
    if await db.broadcast_mutes.find_one({"broadcast_id": bid, "user_id": user["id"]}):
        raise HTTPException(403, "Você está silenciado neste chat.")
    text = (body.text or "").strip()[:500]
    if not text:
        raise HTTPException(400, "Mensagem vazia.")
    doc = {"id": str(uuid.uuid4()), "broadcast_id": bid, "user_id": user["id"], "name": user["name"],
           "text": text, "at": now_iso(), "highlighted": False, "deleted": False}
    await db.broadcast_chat.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api.delete("/broadcasts/{bid}/chat/{msg_id}")
async def delete_chat(bid: str, msg_id: str, user: dict = Depends(require_perm("MODERATE_LIVE"))):
    await db.broadcast_chat.update_one({"id": msg_id, "broadcast_id": bid}, {"$set": {"deleted": True}})
    await audit("chat_delete", user, broadcast_id=bid, msg_id=msg_id)
    return {"ok": True}

@api.post("/broadcasts/{bid}/chat/{msg_id}/highlight")
async def highlight_chat(bid: str, msg_id: str, user: dict = Depends(require_perm("MODERATE_LIVE"))):
    m = await db.broadcast_chat.find_one({"id": msg_id, "broadcast_id": bid})
    if not m:
        raise HTTPException(404, "Mensagem não encontrada")
    await db.broadcast_chat.update_one({"id": msg_id}, {"$set": {"highlighted": not m.get("highlighted", False)}})
    return {"ok": True, "highlighted": not m.get("highlighted", False)}

@api.post("/broadcasts/{bid}/moderate")
async def moderate_broadcast(bid: str, body: dict, user: dict = Depends(require_perm("MODERATE_LIVE"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    action = body.get("action")
    target = body.get("user_id")
    if action == "toggle_chat":
        await db.broadcasts.update_one({"id": bid}, {"$set": {"chat_enabled": not b.get("chat_enabled", True)}})
        await audit("chat_toggle", user, broadcast_id=bid)
        return {"ok": True, "chat_enabled": not b.get("chat_enabled", True)}
    if not target:
        raise HTTPException(400, "user_id obrigatório.")
    if action == "mute":
        await db.broadcast_mutes.update_one({"broadcast_id": bid, "user_id": target},
            {"$set": {"broadcast_id": bid, "user_id": target}}, upsert=True)
    elif action == "unmute":
        await db.broadcast_mutes.delete_one({"broadcast_id": bid, "user_id": target})
    elif action == "block":
        await db.broadcast_bans.update_one({"broadcast_id": bid, "user_id": target},
            {"$set": {"broadcast_id": bid, "user_id": target}}, upsert=True)
        if livekit_configured():
            try:
                async with lk_client() as lk:
                    await lk.room.remove_participant(lk_api.RoomParticipantIdentity(room=b["room_name"], identity=target))
            except Exception as e:
                logging.warning(f"LiveKit remove_participant: {e}")
    elif action == "unblock":
        await db.broadcast_bans.delete_one({"broadcast_id": bid, "user_id": target})
    else:
        raise HTTPException(400, "Ação inválida.")
    await audit(f"moderate_{action}", user, broadcast_id=bid, target=target)
    return {"ok": True}

@api.get("/broadcasts/{bid}/report")
async def broadcast_report(bid: str, user: dict = Depends(require_perm("VIEW_LIVE_ANALYTICS"))):
    b = await db.broadcasts.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Transmissão não encontrada")
    total_msgs = await db.broadcast_chat.count_documents({"broadcast_id": bid})
    blocked = await db.broadcast_bans.count_documents({"broadcast_id": bid})
    unique_viewers = len(await db.broadcast_presence.distinct("user_id", {"broadcast_id": bid}))
    logs = await db.audit_logs.find({"broadcast_id": bid}).sort("at", 1).to_list(300)
    for l in logs:
        l.pop("_id", None)
    return {"title": b["title"], "duration_min": b.get("duration_min"),
            "viewers_peak": b.get("viewers_peak") or 0, "unique_viewers": unique_viewers,
            "messages": total_msgs, "blocked_users": blocked,
            "started_at": b.get("started_at"), "ended_at": b.get("ended_at"), "logs": logs}

@api.get("/livekit/status")
async def livekit_status(user: dict = Depends(get_current_user)):
    return {"configured": livekit_configured()}


# ---------------- seed ----------------
STAGES = [
    {"order": 1, "slug": "PRE_VOCACIONADO", "name": "Pré-Vocacionado", "theme": "Descobrir", "icon": "sprout",
     "question": "Quem é Jesus e o que Ele está fazendo na minha vida?",
     "description": "O primeiro encontro. Descobrir o amor de Deus e abrir o coração."},
    {"order": 2, "slug": "VOCACIONADO", "name": "Vocacionado", "theme": "Discernir", "icon": "flame",
     "question": "Senhor, o que queres de mim?",
     "description": "Tempo de discernimento e escuta da voz de Deus."},
    {"order": 3, "slug": "DISCIPULO_ANO_1", "name": "Discípulo — Ano 1", "theme": "Seguir", "icon": "shield",
     "question": "Como viver como discípulo de Cristo?",
     "description": "Aprender a seguir Jesus na vida cotidiana."},
    {"order": 4, "slug": "DISCIPULO_ANO_2", "name": "Discípulo — Ano 2", "theme": "Servir", "icon": "swords",
     "question": "Como transformar minha vida em missão?",
     "description": "Colocar os dons a serviço do Reino."},
    {"order": 5, "slug": "COMPROMISSADO", "name": "Compromissado", "theme": "Entregar-se", "icon": "handshake",
     "question": "Até onde estou disposto a entregar minha vida?",
     "description": "O compromisso maduro com a comunidade e a missão."},
    {"order": 6, "slug": "CONSAGRADO", "name": "Consagrado", "theme": "Permanecer", "icon": "crown",
     "question": "Como permanecer fiel à missão e formar outros?",
     "description": "Permanecer, liderar e gerar novos discípulos."},
]

SEED_MODULES = {
    1: [("Encontro com Jesus", ["Deus me ama primeiro", "O anúncio do Kerigma", "A conversão do coração"]),
        ("A oração que transforma", ["Como rezar todos os dias", "Ler a Palavra com o coração"])],
    2: [("Escuta e discernimento", ["O que é vocação", "Silêncio e escuta interior", "Sinais de Deus na minha história"]),
        ("Vida sacramental", ["A graça dos sacramentos", "A Eucaristia, fonte e ápice"])],
    3: [("Fundamentos do discipulado", ["Quem é o discípulo", "A cruz de cada dia", "Comunidade e fraternidade"]),
        ("Formação doutrinal", ["Introdução ao Catecismo", "A Igreja e sua missão"])],
}

DIM = ["Oração", "Formação", "Comunidade", "Missão", "Vocação"]


async def seed():
    seed_demo_users = os.environ.get("SEED_DEMO_USERS", "false").lower() == "true"

    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)

    # stages
    for s in STAGES:
        await db.stages.update_one(
            {"order": s["order"]},
            {"$setOnInsert": s},
            upsert=True
        )
    # modules + lessons
    if await db.modules.count_documents({}) == 0:
        for stage_order, mods in SEED_MODULES.items():
            for mi, (mtitle, lessons) in enumerate(mods, start=1):
                mid = str(uuid.uuid4())
                await db.modules.insert_one({"id": mid, "stage_order": stage_order, "order": mi,
                                             "title": mtitle, "description": f"Módulo {mi} da etapa."})
                for li, ltitle in enumerate(lessons, start=1):
                    await db.lessons.insert_one({
                        "id": str(uuid.uuid4()), "module_id": mid, "module_title": mtitle,
                        "stage_order": stage_order, "order": li, "title": ltitle,
                        "dimension": DIM[(li - 1) % len(DIM)],
                        "duration_min": 8 + li * 2,
                        "video_url": "",
                        "content": f"Nesta aula vamos refletir sobre '{ltitle}'. "
                                   f"Leia com calma, faça a oração proposta e registre no seu diário o que Deus falar ao seu coração.\n\n"
                                   f"Passagem sugerida: Jo 15,1-11.\n\nDesafio: dedique 15 minutos hoje à oração pessoal.",
                    })

    # missions
    if await db.missions.count_documents({}) == 0:
        missions = [
            ("Ler João 15 e sublinhar um versículo", "Oração"),
            ("Rezar 15 minutos em silêncio", "Oração"),
            ("Participar da Santa Missa", "Comunidade"),
            ("Evangelizar uma pessoa esta semana", "Missão"),
            ("Fazer uma ação de serviço", "Comunidade"),
        ]
        for i, (t, dim) in enumerate(missions, start=1):
            await db.missions.insert_one({"id": str(uuid.uuid4()), "order": i, "title": t,
                                          "dimension": dim, "active": True, "week": "Semana atual"})
    # daily word
    if await db.daily_readings.count_documents({"kind": "word"}) == 0:
        await db.daily_readings.insert_one({
            "kind": "word",
            "reference": "João 15, 5",
            "text": "Eu sou a videira, vós os ramos. Quem permanece em mim e eu nele, esse dá muito fruto; porque sem mim nada podeis fazer.",
            "reflection": "Permanecer em Cristo é a fonte de toda a nossa vida e missão. Hoje, procure permanecer nEle em cada gesto.",
            "prayer": "Senhor, ensina-me a permanecer em Ti. Que a minha vida dê muito fruto para o Teu Reino. Amém.",
            "challenge": "Reserve 10 minutos de silêncio para permanecer diante de Deus.",
        })

    # events
    if await db.events.count_documents({}) == 0:
        base = datetime.now(timezone.utc)
        evs = [("Cerco de Jericó", "vigília", 2), ("Encontro de Formação", "formação", 5), ("Missa da Comunidade", "missa", 7)]
        for t, kind, d in evs:
            await db.events.insert_one({"id": str(uuid.uuid4()), "title": t, "kind": kind,
                                        "date": (base + timedelta(days=d)).isoformat(),
                                        "location": "Sede da Comunidade"})

    # demo external media (embed oficial — apenas URLs públicas)
    if await db.external_media.count_documents({}) == 0:
        owner = await db.users.find_one({"email": "formador@caminho.app"})
        oid = owner["id"] if owner else "system"
        oname = owner["name"] if owner else "Comunidade CAMINHO"
        demo_media = [
            {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "Louvor e Adoração", "description": "Momento de música e oração para todos.", "kind": "video", "category": "Oração", "stages": []},
            {"url": "https://youtu.be/hFZFjoX2cGg", "title": "Catequese: O Kerigma", "description": "Formação doutrinal para a etapa Pré-Vocacionado.", "kind": "video", "category": "Formação", "stages": [1]},
            {"url": "https://www.youtube.com/live/5qap5aO4i9A", "title": "Live: Adoração ao Santíssimo", "description": "Transmissão ao vivo hospedada no YouTube.", "kind": "live", "category": "Comunidade", "stages": [], "live_status": "scheduled"},
            {"url": "https://vimeo.com/76979871", "title": "Testemunho de Vocação", "description": "Vídeo hospedado no Vimeo (etapa Discípulo Ano 1).", "kind": "video", "category": "Vocação", "stages": [3]},
        ]
        for dm in demo_media:
            try:
                info = await parse_media_url(dm["url"])
            except Exception:
                continue
            await db.external_media.insert_one({
                "id": str(uuid.uuid4()), "title": dm["title"], "description": dm["description"],
                "kind": dm["kind"], "category": dm["category"], "source_url": dm["url"],
                "provider": info["provider"], "provider_name": info["provider_name"],
                "external_id": info["external_id"], "embed_url": info["embed_url"],
                "watch_url": info["watch_url"], "can_embed": info["can_embed"],
                "thumbnail": info["thumbnail"], "stages": dm["stages"], "scheduled_at": "",
                "live_status": dm.get("live_status") if dm["kind"] == "live" else None,
                "chat_enabled": False, "status": "published",
                "owner_id": oid, "owner_name": oname, "created_at": now_iso(),
            })
    # lives
    if await db.lives.count_documents({}) == 0:
        base = datetime.now(timezone.utc)
        lives = [
            {"title": "Adoração ao Vivo", "description": "Momento de adoração e louvor com toda a comunidade.", "status": "live", "stage_order": None, "required": False, "former": "Comunidade CAMINHO", "min_presence": 75, "date": base.isoformat()},
            {"title": "Formação: Viver como Discípulo", "description": "Encontro ao vivo — LIVE OBRIGATÓRIA da etapa Discípulo Ano 1.", "status": "upcoming", "stage_order": 3, "required": True, "former": "Maria Formadora", "min_presence": 75, "date": (base + timedelta(days=1)).isoformat()},
            {"title": "Kerigma: O primeiro anúncio", "description": "Live introdutória aberta a todos.", "status": "upcoming", "stage_order": 1, "required": False, "former": "Equipe de Missão", "min_presence": 75, "date": (base + timedelta(days=3)).isoformat()},
            {"title": "Discernindo a vontade de Deus", "description": "Live gravada sobre discernimento vocacional.", "status": "recorded", "stage_order": 2, "required": False, "former": "Padre Convidado", "min_presence": 75, "date": (base - timedelta(days=5)).isoformat()},
        ]
        for i, l in enumerate(lives):
            l["id"] = str(uuid.uuid4()); l["order"] = i
            await db.lives.insert_one(l)

    # apologetics / Defesa da Fé
    if await db.apologetics.count_documents({}) == 0:
        entries = [
            {"category": "Eucaristia", "question": "A Eucaristia é realmente o Corpo de Cristo?",
             "answer": "Sim. A Igreja professa a presença real de Cristo — Corpo, Sangue, Alma e Divindade — sob as espécies do pão e do vinho.",
             "explanation": "Na consagração da Missa acontece a transubstanciação: a substância do pão e do vinho converte-se no Corpo e Sangue de Cristo, permanecendo as aparências. Não é símbolo, é presença real.",
             "bible": "Jo 6,51-58; Mt 26,26-28; 1Cor 11,23-29", "tradition": "Testemunho unânime dos Padres da Igreja (Santo Inácio de Antioquia, São Justino).",
             "catechism": "CIC 1373-1381", "magisterium": "Concílio de Trento; Ecclesia de Eucharistia (São João Paulo II)", "extra": ""},
            {"category": "Nossa Senhora", "question": "Por que os católicos honram Maria?",
             "answer": "Nós veneramos (não adoramos) Maria como Mãe de Deus e primeira discípula. A adoração é só de Deus.",
             "explanation": "A honra a Maria conduz sempre a Cristo. Chamá-la Mãe de Deus (Theotokos) protege a verdade de que Jesus é Deus e homem.",
             "bible": "Lc 1,28.42-48; Jo 2,1-11; Jo 19,26-27", "tradition": "Concílio de Éfeso (431) proclamou Maria Theotokos.",
             "catechism": "CIC 963-975; 971", "magisterium": "Lumen Gentium, cap. VIII", "extra": ""},
            {"category": "Papado", "question": "De onde vem a autoridade do Papa?",
             "answer": "Do próprio Cristo, que confiou a Pedro o primado sobre a Igreja.",
             "explanation": "O Papa é o sucessor de Pedro e princípio visível de unidade dos bispos e dos fiéis.",
             "bible": "Mt 16,18-19; Lc 22,32; Jo 21,15-17", "tradition": "Sucessão apostólica ininterrupta dos bispos de Roma.",
             "catechism": "CIC 880-882", "magisterium": "Vaticano I (Pastor Aeternus); Lumen Gentium 22-23", "extra": ""},
            {"category": "Confissão", "question": "Por que confessar os pecados a um padre?",
             "answer": "Porque Cristo deu aos apóstolos o poder de perdoar os pecados em Seu nome.",
             "explanation": "No sacramento da Reconciliação, o sacerdote age in persona Christi. É Deus quem perdoa, pelo ministério da Igreja.",
             "bible": "Jo 20,21-23; Tg 5,16; 2Cor 5,18-20", "tradition": "Prática penitencial da Igreja desde os primeiros séculos.",
             "catechism": "CIC 1441-1449", "magisterium": "Concílio de Trento, sessão XIV", "extra": ""},
            {"category": "Purgatório", "question": "O purgatório está na Bíblia?",
             "answer": "Sim, a doutrina tem fundamento bíblico e na Tradição: uma purificação final dos que morrem na graça de Deus.",
             "explanation": "O purgatório não é uma segunda chance, mas a purificação de quem já está salvo, para entrar na plena santidade do Céu.",
             "bible": "2Mac 12,46; 1Cor 3,13-15; Mt 12,32", "tradition": "Oração pelos mortos, atestada desde a Igreja primitiva.",
             "catechism": "CIC 1030-1032", "magisterium": "Concílios de Florença e de Trento", "extra": ""},
            {"category": "Bíblia e Tradição", "question": "A fé católica se baseia só na Bíblia?",
             "answer": "Não. A Revelação chega a nós pela Sagrada Escritura e pela Sagrada Tradição, interpretadas pelo Magistério.",
             "explanation": "Escritura e Tradição formam um único depósito da fé. Foi a própria Igreja, guiada pela Tradição, que definiu o cânon bíblico.",
             "bible": "2Ts 2,15; 2Tm 2,2; Jo 21,25", "tradition": "Transmissão viva da fé pelos apóstolos e seus sucessores.",
             "catechism": "CIC 80-83; 95", "magisterium": "Dei Verbum, cap. II", "extra": ""},
        ]
        for i, e in enumerate(entries):
            e["id"] = str(uuid.uuid4()); e["order"] = i
            await db.apologetics.insert_one(e)

    # FUNDADOR (owner) — Kelvin. Autoridade institucional máxima (INDEPENDE da etapa)
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({"id": str(uuid.uuid4()), "name": "Kelvin (Fundador)", "email": admin_email,
                                   "password_hash": hash_password(admin_pw), "role": "fundador",
                                   "current_stage_order": 6, "formation_stage": "CONSAGRADO", "formation_year": None,
                                   "formation_status": "ATIVO", "formador_id": None, "general_formador_id": None,
                                   "permissions": [], "onboarded": True, "blocked": False, "avatar": None,
                                   "created_at": now_iso(), "last_active": now_iso()})
    # ADMIN técnico PROTEGIDO (imutável por Fundador/Cofundador)
    technical_admin_email = os.environ["TECHNICAL_ADMIN_EMAIL"].lower()
    technical_admin_password = os.environ["TECHNICAL_ADMIN_PASSWORD"]

    adm = await db.users.find_one({"email": technical_admin_email})

    if not adm:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "name": "Admin Técnico",
            "email": technical_admin_email,
            "password_hash": hash_password(technical_admin_password),
            "role": "admin",
            "admin_protected": True,
            "current_stage_order": 6,
            "formation_stage": "CONSAGRADO",
            "formation_year": None,
            "formation_status": "ATIVO",
            "formador_id": None,
            "general_formador_id": None,
            "permissions": [],
            "onboarded": True,
            "blocked": False,
            "avatar": None,
            "created_at": now_iso(),
            "last_active": now_iso()
        })
    # settings
    await db.settings.update_one(
        {"key": "app"},
        {"$setOnInsert": {"key": "app", "allow_stage_skip": True}},
        upsert=True
    )

    for _k, _v in {
        "stage_change_requires_approval": True,
        "cofundador_can_change_stage": False
    }.items():
        await db.settings.update_one(
            {"key": "app", _k: {"$exists": False}},
            {"$set": {_k: _v}}
        )

    # backfill separação role×etapa em todos os usuários
    async for _u in db.users.find({"$or": [{"formation_stage": {"$exists": False}}, {"formation_status": {"$exists": False}}, {"general_formador_id": {"$exists": False}}]}):
        _fst, _fyr = FORMATION_META.get(_u.get("current_stage_order", 1), ("PRE_VOCACIONADO", None))
        _upd = {}
        if "formation_stage" not in _u: _upd["formation_stage"] = _fst
        if "formation_year" not in _u: _upd["formation_year"] = _fyr
        if "formation_status" not in _u: _upd["formation_status"] = "EM_FORMACAO" if _u.get("role") == "membro" else "ATIVO"
        if "general_formador_id" not in _u: _upd["general_formador_id"] = None
        if _upd:
            await db.users.update_one({"id": _u["id"]}, {"$set": _upd})

    # requisitos por etapa (padrão: exige 100% aulas + lives obrigatórias)
    for s in STAGES:
        await db.stage_requirements.update_one({"order": s["order"]},
            {"$setOnInsert": {"order": s["order"], "require_lessons": True, "require_mandatory_lives": True}}, upsert=True)

    # Permissões: garante o campo em todos os usuários.
    # Esta correção estrutural não depende dos usuários demo.
    await db.users.update_many(
        {"permissions": {"$exists": False}},
        {"$set": {"permissions": []}}
    )

    # Usuários e permissões de demonstração.
    # DESATIVADO por padrão.
    # Ativar somente em ambiente de desenvolvimento/testes controlados
    # através de SEED_DEMO_USERS=true.
    if seed_demo_users:
        demo_password = os.environ["DEMO_USER_PASSWORD"]

        demo_former_perms = [
            "CREATE_COURSE",
            "EDIT_COURSE",
            "CREATE_MODULE",
            "CREATE_LESSON",
            "EDIT_LESSON",
            "PUBLISH_LESSON",
            "UPLOAD_VIDEO",
            "UPLOAD_AUDIO",
            "UPLOAD_DOCUMENT",
            "CREATE_ANNOUNCEMENT",
            "DELETE_ANNOUNCEMENT",
            "CREATE_LIVE",
            "EDIT_LIVE",
            "START_LIVE",
            "END_LIVE",
            "MODERATE_LIVE",
            "VIEW_ANALYTICS",
            "MANAGE_EXTERNAL_MEDIA",
            "MANAGE_LIVE",
            "MANAGE_CAMERA",
            "MANAGE_MICROPHONE",
            "MANAGE_SCENES",
            "MANAGE_SOURCES",
            "VIEW_LIVE_ANALYTICS",
        ]

        # Demo formador
        former = await db.users.find_one(
            {"email": "formador@caminho.app"}
        )

        if not former:
            fid = str(uuid.uuid4())

            await db.users.insert_one({
                "id": fid,
                "name": "Maria Formadora",
                "email": "formador@caminho.app",
                "password_hash": hash_password(demo_password),
                "role": "formador",
                "current_stage_order": 6,
                "formation_stage": _formador_stage,
                "formation_year": _formador_year,
                "formation_status": "ATIVO",
                "general_formador_id": None,
                "formador_id": None,
                "permissions": demo_former_perms,
                "onboarded": True,
                "blocked": False,
                "avatar": None,
                "created_at": now_iso(),
                "last_active": now_iso(),
            })
        else:
            fid = former["id"]

        # Demo membro
        membro = await db.users.find_one(
            {"email": "membro@caminho.app"}
        )
        if not membro:
            mid = str(uuid.uuid4())
            _membro_stage, _membro_year = FORMATION_META.get(
                3,
                ("PRE_VOCACIONADO", None),
            )

            await db.users.insert_one({
                "id": mid,
                "name": "João Membro",
                "email": "membro@caminho.app",
                "password_hash": hash_password(demo_password),
                "role": "membro",
                "current_stage_order": 3,
                "formation_stage": _membro_stage,
                "formation_year": _membro_year,
                "formation_status": "EM_FORMACAO",
                "general_formador_id": None,
                "formador_id": fid,
                "onboarded": True,
                "blocked": False,
                "avatar": None,
                "created_at": now_iso(),
                "last_active": (
                    datetime.now(timezone.utc)
                    - timedelta(days=6)
                ).isoformat(),
            })

        # Usuários demo, um por etapa.
        # Somente criados quando SEED_DEMO_USERS=true.
        stage_users = [
            (
                "prevocacionado@caminho.app",
                "Ana Pré-Vocacionada",
                1,
                0,
            ),
            (
                "vocacionado@caminho.app",
                "Pedro Vocacionado",
                2,
                1,
            ),
            (
                "discipulo2@caminho.app",
                "Tiago Discípulo II",
                4,
                12,
            ),
            (
                "compromissado@caminho.app",
                "Clara Compromissada",
                5,
                3,
            ),
            (
                "consagrado@caminho.app",
                "Lucas Consagrado",
                6,
                2,
            ),
        ]

        for email, name, order, inactive_days in stage_users:
            existing_user = await db.users.find_one(
                {"email": email}
            )

            if not existing_user:
                _stage, _year = FORMATION_META.get(
                    order,
                    ("PRE_VOCACIONADO", None),
                )

                await db.users.insert_one({
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "email": email,
                    "password_hash": hash_password(demo_password),
                    "role": "membro",
                    "current_stage_order": order,
                    "formation_stage": _stage,
                    "formation_year": _year,
                    "formation_status": "EM_FORMACAO",
                    "general_formador_id": None,
                    "permissions": [],
                    "formador_id": fid,
                    "onboarded": True,
                    "blocked": False,
                    "avatar": None,
                    "created_at": now_iso(),
                    "last_active": (
                        datetime.now(timezone.utc)
                        - timedelta(days=inactive_days)
                    ).isoformat(),
                })
        # Demo FORMADOR GERAL + vínculo do formador e membros.
        geral = await db.users.find_one(
            {"email": "geral@caminho.app"}
        )

        if not geral:
            gid = str(uuid.uuid4())

            await db.users.insert_one({
                "id": gid,
                "name": "Pe. João (Formador Geral)",
                "email": "geral@caminho.app",
                "password_hash": hash_password(demo_password),
                "role": "formador_geral",
                "current_stage_order": 4,
                "formation_stage": "DISCIPULO",
                "formation_year": 2,
                "formation_status": "ATIVO",
                "formador_id": None,
                "general_formador_id": None,
                "permissions": [],
                "onboarded": True,
                "blocked": False,
                "avatar": None,
                "created_at": now_iso(),
                "last_active": now_iso(),
            })

            geral = await db.users.find_one(
                {"id": gid}
            )

@app.on_event("startup")
async def startup_event():
    await seed()

app.include_router(api)

logging.basicConfig(level=logging.INFO)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
