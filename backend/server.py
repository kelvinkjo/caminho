from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import logging, uuid, bcrypt, jwt

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

def create_token(uid: str, ttl_hours=720):
    payload = {"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(hours=ttl_hours), "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def public_user(u: dict) -> dict:
    u = dict(u)
    u.pop("_id", None)
    u.pop("password_hash", None)
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
        if user["role"] not in roles:
            raise HTTPException(403, "Acesso não autorizado")
        return user
    return dep

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
    current_stage_order: Optional[int] = None
    formador_id: Optional[str] = None
    blocked: Optional[bool] = None

# ---------------- auth endpoints ----------------
def set_cookie(resp: Response, token: str):
    resp.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=2592000, path="/")

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
        "onboarded": False, "blocked": False, "avatar": None,
        "created_at": now_iso(), "last_active": now_iso(),
    }
    await db.users.insert_one(doc)
    token = create_token(uid)
    set_cookie(response, token)
    return {"user": public_user(doc), "token": token}

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
    return {"user": public_user(u), "token": token}

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
    if user["role"] not in ("admin", "formador") and order > user["current_stage_order"]:
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
    if user["role"] not in ("admin", "formador") and l["stage_order"] > user["current_stage_order"]:
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
    if user["role"] not in ("admin", "formador") and l["stage_order"] > user["current_stage_order"]:
        raise HTTPException(403, "Etapa bloqueada")
    await db.lesson_progress.update_one(
        {"user_id": user["id"], "lesson_id": lesson_id},
        {"$set": {"completed": body.completed, "percent": max(body.percent, 100 if body.completed else 0),
                  "stage_order": l["stage_order"], "updated_at": now_iso()},
         "$setOnInsert": {"id": str(uuid.uuid4()), "started_at": now_iso()}},
        upsert=True)
    return {"ok": True, "progress": await stage_progress(user["id"], l["stage_order"])}

# ---------------- approval flow ----------------
@api.post("/stages/request-approval")
async def request_approval(user: dict = Depends(get_current_user)):
    order = user["current_stage_order"]
    prog = await stage_progress(user["id"], order)
    if prog["percent"] < 100:
        raise HTTPException(400, "Conclua todas as aulas da etapa antes de solicitar avaliação.")
    if await mandatory_lives_pending(user["id"], order):
        raise HTTPException(400, "Confirme presença nas lives obrigatórias da etapa antes de solicitar avaliação.")
    if order >= 6:
        raise HTTPException(400, "Você já está na etapa final.")
    existing = await db.approvals.find_one({"user_id": user["id"], "stage_order": order, "status": "pending"})
    if existing:
        return {"ok": True, "status": "pending"}
    doc = {"id": str(uuid.uuid4()), "user_id": user["id"], "user_name": user["name"],
           "stage_order": order, "formador_id": user.get("formador_id"),
           "status": "pending", "created_at": now_iso(), "note": ""}
    await db.approvals.insert_one(doc)
    await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "action": "request_approval",
                                    "user_id": user["id"], "stage_order": order, "at": now_iso()})
    return {"ok": True, "status": "pending"}

@api.get("/approvals")
async def list_approvals(user: dict = Depends(require_roles("admin", "formador"))):
    q = {"status": "pending"}
    if user["role"] == "formador":
        q["formador_id"] = user["id"]
    items = await db.approvals.find(q).sort("created_at", 1).to_list(500)
    for i in items:
        i.pop("_id", None)
    return items

@api.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, user: dict = Depends(require_roles("admin", "formador"))):
    a = await db.approvals.find_one({"id": approval_id})
    if not a or a["status"] != "pending":
        raise HTTPException(404, "Solicitação não encontrada")
    target = await db.users.find_one({"id": a["user_id"]})
    new_order = min(a["stage_order"] + 1, 6)
    await db.users.update_one({"id": a["user_id"]}, {"$set": {"current_stage_order": new_order}})
    await db.approvals.update_one({"id": approval_id}, {"$set": {"status": "approved", "resolved_at": now_iso(), "resolved_by": user["id"]}})
    await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "action": "approve_stage", "by": user["id"],
                                    "user_id": a["user_id"], "from_stage": a["stage_order"], "to_stage": new_order, "at": now_iso()})
    return {"ok": True}

@api.post("/approvals/{approval_id}/followup")
async def request_followup(approval_id: str, body: FollowupIn, user: dict = Depends(require_roles("admin", "formador"))):
    a = await db.approvals.find_one({"id": approval_id})
    if not a or a["status"] != "pending":
        raise HTTPException(404, "Solicitação não encontrada")
    await db.approvals.update_one({"id": approval_id}, {"$set": {"status": "followup", "note": body.note, "resolved_at": now_iso(), "resolved_by": user["id"]}})
    await db.pastoral_followups.insert_one({"id": str(uuid.uuid4()), "user_id": a["user_id"], "formador_id": user["id"],
                                            "note": body.note, "at": now_iso()})
    return {"ok": True}

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
    q = {} if user["role"] == "admin" else {"formador_id": user["id"]}
    q["role"] = "membro"
    people = await db.users.find(q).to_list(1000)
    stages = {s["order"]: s async for s in db.stages.find()}
    out = []
    for p in people:
        prog = await stage_progress(p["id"], p["current_stage_order"])
        st = stages.get(p["current_stage_order"], {})
        pending = await db.approvals.find_one({"user_id": p["id"], "status": "pending"})
        out.append({
            "id": p["id"], "name": p["name"], "email": p["email"],
            "current_stage_order": p["current_stage_order"],
            "stage_name": st.get("name", ""), "progress": prog,
            "last_active": p.get("last_active"), "radar": radar_status(p.get("last_active", "")),
            "awaiting_approval": bool(pending),
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
    return {
        "user": public_user(user), "stage": stage, "progress": prog,
        "continue_lesson": continue_lesson, "word": word,
        "missions": missions, "events": events, "next_live": live,
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
    pending = await db.approvals.count_documents({"status": "pending"})
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
    await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "action": "admin_update_user", "by": user["id"],
                                    "user_id": uid, "changes": updates, "at": now_iso()})
    return {"ok": True}

@api.get("/formadores")
async def list_formadores(user: dict = Depends(require_roles("admin"))):
    fs = await db.users.find({"role": "formador"}).to_list(500)
    return [{"id": f["id"], "name": f["name"]} for f in fs]

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
    if user["role"] in ("admin", "formador"):
        return True
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
        key = {"live": "live_now", "upcoming": "upcoming", "recorded": "recorded"}.get(l.get("status"), "upcoming")
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
    max_order = 6 if user["role"] in ("admin", "formador") else user["current_stage_order"]
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
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)

    # stages
    for s in STAGES:
        await db.stages.update_one({"order": s["order"]}, {"$set": s}, upsert=True)

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
    await db.daily_readings.update_one({"kind": "word"}, {"$set": {
        "kind": "word", "reference": "João 15, 5",
        "text": "Eu sou a videira, vós os ramos. Quem permanece em mim e eu nele, esse dá muito fruto; porque sem mim nada podeis fazer.",
        "reflection": "Permanecer em Cristo é a fonte de toda a nossa vida e missão. Hoje, procure permanecer nEle em cada gesto.",
        "prayer": "Senhor, ensina-me a permanecer em Ti. Que a minha vida dê muito fruto para o Teu Reino. Amém.",
        "challenge": "Reserve 10 minutos de silêncio para permanecer diante de Deus.",
    }}, upsert=True)

    # events
    if await db.events.count_documents({}) == 0:
        base = datetime.now(timezone.utc)
        evs = [("Cerco de Jericó", "vigília", 2), ("Encontro de Formação", "formação", 5), ("Missa da Comunidade", "missa", 7)]
        for t, kind, d in evs:
            await db.events.insert_one({"id": str(uuid.uuid4()), "title": t, "kind": kind,
                                        "date": (base + timedelta(days=d)).isoformat(),
                                        "location": "Sede da Comunidade"})

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

    # admin
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    admin_id = None
    if not existing:
        admin_id = str(uuid.uuid4())
        await db.users.insert_one({"id": admin_id, "name": "Kelvin (Admin)", "email": admin_email,
                                   "password_hash": hash_password(admin_pw), "role": "admin",
                                   "current_stage_order": 6, "formador_id": None, "onboarded": True,
                                   "blocked": False, "avatar": None, "created_at": now_iso(), "last_active": now_iso()})
    else:
        admin_id = existing["id"]
        if not verify_password(admin_pw, existing["password_hash"]):
            await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_pw)}})

    # demo formador
    former = await db.users.find_one({"email": "formador@caminho.app"})
    if not former:
        fid = str(uuid.uuid4())
        await db.users.insert_one({"id": fid, "name": "Maria Formadora", "email": "formador@caminho.app",
                                   "password_hash": hash_password("***REMOVED***"), "role": "formador",
                                   "current_stage_order": 6, "formador_id": None, "onboarded": True,
                                   "blocked": False, "avatar": None, "created_at": now_iso(), "last_active": now_iso()})
    else:
        fid = former["id"]

    # demo membro
    membro = await db.users.find_one({"email": "membro@caminho.app"})
    if not membro:
        mid = str(uuid.uuid4())
        await db.users.insert_one({"id": mid, "name": "João Membro", "email": "membro@caminho.app",
                                   "password_hash": hash_password("***REMOVED***"), "role": "membro",
                                   "current_stage_order": 3, "formador_id": fid, "onboarded": True,
                                   "blocked": False, "avatar": None, "created_at": now_iso(),
                                   "last_active": (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()})

    # demo users: one per stage (item 59) — all vinculados ao formador
    stage_users = [
        ("prevocacionado@caminho.app", "Ana Pré-Vocacionada", 1, 0),
        ("vocacionado@caminho.app", "Pedro Vocacionado", 2, 1),
        ("discipulo2@caminho.app", "Tiago Discípulo II", 4, 12),
        ("compromissado@caminho.app", "Clara Compromissada", 5, 3),
        ("consagrado@caminho.app", "Lucas Consagrado", 6, 2),
    ]
    for email, name, order, inactive_days in stage_users:
        if not await db.users.find_one({"email": email}):
            await db.users.insert_one({"id": str(uuid.uuid4()), "name": name, "email": email,
                                       "password_hash": hash_password("***REMOVED***"), "role": "membro",
                                       "current_stage_order": order, "formador_id": fid, "onboarded": True,
                                       "blocked": False, "avatar": None, "created_at": now_iso(),
                                       "last_active": (datetime.now(timezone.utc) - timedelta(days=inactive_days)).isoformat()})

@app.on_event("startup")
async def on_startup():
    await seed()

app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.basicConfig(level=logging.INFO)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
