import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Users, ShieldCheck, ClipboardCheck, Check, X, ChevronDown, Search } from "lucide-react";
import { toast } from "sonner";

const STAGES = ["Pré-Vocacionado", "Vocacionado", "Discípulo Ano 1", "Discípulo Ano 2", "Compromissado", "Consagrado"];
const STATUSES = [["ATIVO", "Ativo"], ["EM_FORMACAO", "Em formação"], ["PAUSADO", "Pausado"], ["AFASTADO", "Afastado"], ["CONCLUIDO", "Concluído"]];
const ROLE_OPTS = [["membro", "Membro"], ["formador", "Formador"], ["formador_geral", "Formador Geral"], ["cofundador", "Cofundador"], ["fundador", "Fundador"]];

function UserEditor({ u, actorRole, gerais, onChanged }) {
  const [role, setRole] = useState(u.role);
  const [stage, setStage] = useState(u.current_stage_order || 1);
  const [status, setStatus] = useState(u.formation_status || "EM_FORMACAO");
  const [geral, setGeral] = useState(u.general_formador_id || "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const canManageInstitucional = ["admin", "fundador", "cofundador"].includes(actorRole);
  const roleChoices = actorRole === "admin" ? [["admin", "Admin Técnico"], ...ROLE_OPTS] : ROLE_OPTS;

  const saveRole = async () => {
    if (role === u.role) return;
    setBusy(true);
    try { await api.patch(`/admin/users/${u.id}/role`, { role, reason: reason || "Ajuste de função" }); toast.success("Função atualizada."); onChanged(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const saveFormation = async () => {
    if (!reason.trim()) return toast.error("Informe o motivo da mudança de etapa.");
    setBusy(true);
    try {
      const { data } = await api.patch(`/admin/users/${u.id}/formation`, { new_stage_order: stage, formation_status: status, reason });
      toast.success(data.status === "requested" ? "Solicitação enviada para aprovação." : "Etapa/status atualizados.");
      onChanged();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const saveGeral = async () => {
    if (!geral) return;
    setBusy(true);
    try { await api.post(`/admin/formadores/${u.id}/assign-geral`, { general_formador_id: geral, reason: reason || "Vínculo" }); toast.success("Formador vinculado."); onChanged(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <div className="mt-3 pt-3 border-t border-stone-800 space-y-3" data-testid={`editor-${u.id}`}>
      <input data-testid={`reason-${u.id}`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motivo (obrigatório para etapa)" className="w-full bg-stone-800 border border-stone-700 rounded-lg px-3 py-2 text-xs text-stone-100 outline-none" />

      {canManageInstitucional && (
        <div className="flex gap-2">
          <select data-testid={`role-select-${u.id}`} value={role} onChange={(e) => setRole(e.target.value)} className="flex-1 bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">
            {roleChoices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button data-testid={`save-role-${u.id}`} disabled={busy} onClick={saveRole} className="px-3 rounded-lg bg-stone-700 text-stone-100 text-xs font-semibold disabled:opacity-50">Função</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <select data-testid={`stage-select-${u.id}`} value={stage} onChange={(e) => setStage(Number(e.target.value))} className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">
          {STAGES.map((s, i) => <option key={i} value={i + 1}>{s}</option>)}
        </select>
        <select data-testid={`status-select-${u.id}`} value={status} onChange={(e) => setStatus(e.target.value)} className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">
          {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <button data-testid={`save-formation-${u.id}`} disabled={busy} onClick={saveFormation} className="w-full min-h-[40px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold disabled:opacity-50">Aplicar etapa / status</button>

      {u.role === "formador" && canManageInstitucional && (
        <div className="flex gap-2">
          <select data-testid={`geral-select-${u.id}`} value={geral} onChange={(e) => setGeral(e.target.value)} className="flex-1 bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">
            <option value="">Vincular a Formador Geral...</option>
            {gerais.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <button data-testid={`save-geral-${u.id}`} disabled={busy} onClick={saveGeral} className="px-3 rounded-lg bg-stone-700 text-stone-100 text-xs font-semibold disabled:opacity-50">Vincular</button>
        </div>
      )}
    </div>
  );
}

export default function Management() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [ctx, setCtx] = useState(null);
  const [users, setUsers] = useState(null);
  const [requests, setRequests] = useState([]);
  const [open, setOpen] = useState(null);
  const [q, setQ] = useState("");

  const isApprover = ["admin", "fundador", "cofundador"].includes(user?.role) || (user?.permissions || []).includes("MANAGE_FORMATION_STAGE");

  const load = async () => {
    try {
      const [c, us] = await Promise.all([api.get("/me/context"), api.get("/admin/users", { params: q ? { search: q } : {} })]);
      setCtx(c.data); setUsers(us.data);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); setUsers([]); }
    if (isApprover) { try { const r = await api.get("/formation/stage-requests"); setRequests(r.data); } catch {} }
  };
  // Load management data once when the page mounts.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const gerais = (users || []).filter((u) => u.role === "formador_geral");

  const resolve = async (rid, approve) => {
    try { await api.post(`/formation/stage-requests/${rid}/resolve`, { approve, reason: approve ? "Aprovado" : "Recusado" }); toast.success(approve ? "Solicitação aprovada." : "Solicitação recusada."); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const stageLabel = (o) => STAGES[(o || 1) - 1];

  return (
    <Shell>
      <div className="fade-up" data-testid="management-page">
        <button data-testid="back-button" onClick={() => nav("/app/perfil")} className="flex items-center gap-1 text-stone-400 mb-3 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><ShieldCheck className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Gestão</h1></div>
        <p className="text-stone-500 text-sm mb-5">{ctx ? `${ctx.role_label} · função e etapa são independentes` : "Carregando..."}</p>

        {isApprover && requests.length > 0 && (
          <section className="rounded-2xl border border-orange-600/40 bg-orange-600/10 p-4 mb-6" data-testid="requests-section">
            <p className="font-heading font-bold text-sm mb-3 flex items-center gap-2"><ClipboardCheck className="w-4 h-4 text-orange-500" /> Solicitações de mudança de etapa</p>
            <div className="space-y-2">
              {requests.map((r) => (
                <div key={r.id} data-testid={`request-${r.id}`} className="rounded-xl bg-stone-900 border border-stone-800 p-3">
                  <p className="text-sm font-medium">{r.user_name}</p>
                  <p className="text-xs text-stone-400">{stageLabel(r.from_order)} → {stageLabel(r.to_order)} · por {r.requested_by_name}</p>
                  <p className="text-xs text-stone-500 italic mt-0.5">"{r.reason}"</p>
                  <div className="flex gap-2 mt-2">
                    <button data-testid={`approve-${r.id}`} onClick={() => resolve(r.id, true)} className="flex-1 min-h-[36px] rounded-lg bg-green-600 hover:bg-green-500 text-white text-xs font-semibold flex items-center justify-center gap-1"><Check className="w-3.5 h-3.5" /> Aprovar</button>
                    <button data-testid={`reject-${r.id}`} onClick={() => resolve(r.id, false)} className="flex-1 min-h-[36px] rounded-lg border border-red-600/50 text-red-400 text-xs font-semibold flex items-center justify-center gap-1"><X className="w-3.5 h-3.5" /> Recusar</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="relative mb-4">
          <Search className="w-4 h-4 text-stone-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input data-testid="user-search" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Buscar usuário..." className="w-full bg-stone-900 border border-stone-800 rounded-xl pl-9 pr-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
        </div>

        {users === null && <div className="flex justify-center py-16"><Loader2 className="animate-spin text-orange-600" /></div>}
        {users && users.length === 0 && <p className="text-stone-500 text-sm text-center py-8" data-testid="users-empty">Nenhum usuário no seu escopo.</p>}

        <div className="space-y-2">
          {users && users.map((u) => (
            <div key={u.id} data-testid={`user-${u.id}`} className="rounded-2xl border border-stone-800 bg-stone-900 p-4">
              <button onClick={() => setOpen(open === u.id ? null : u.id)} disabled={!u.manageable} className="w-full flex items-center gap-3 text-left disabled:opacity-60">
                <div className="flex-1 min-w-0">
                  <p className="font-heading font-bold text-sm truncate">{u.name} {u.admin_protected && <span className="text-[10px] text-yellow-400">🔒 protegido</span>}</p>
                  <p className="text-xs text-stone-400 truncate">{u.email}</p>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <span className="text-[10px] rounded-full px-2 py-0.5 bg-stone-800 text-stone-300" data-testid={`urole-${u.id}`}>{u.role_label}</span>
                    <span className="text-[10px] rounded-full px-2 py-0.5 bg-orange-600/15 text-orange-300 border border-orange-600/30">{stageLabel(u.current_stage_order)}</span>
                  </div>
                </div>
                {u.manageable && <ChevronDown className={`w-4 h-4 text-stone-500 transition-transform ${open === u.id ? "rotate-180" : ""}`} />}
              </button>
              {open === u.id && u.manageable && <UserEditor u={u} actorRole={user.role} gerais={gerais} onChanged={load} />}
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}
