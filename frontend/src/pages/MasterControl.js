import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Crown, Search, Check, X, History, Settings, ClipboardList, SlidersHorizontal, Lock } from "lucide-react";
import { toast } from "sonner";

const STAGES = ["Pré-Vocacionado", "Vocacionado", "Discípulo Ano 1", "Discípulo Ano 2", "Compromissado", "Consagrado"];
const typeLabel = { MANUAL_CHANGE: "Alteração", MAINTAIN_STAGE: "Manutenção", ADVANCEMENT: "Avanço", RETROCESSION: "Retrocesso", ADMIN_OVERRIDE: "Override" };

export default function MasterControl() {
  const [users, setUsers] = useState(null);
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState(null);
  const [recs, setRecs] = useState([]);
  const [settings, setSettings] = useState(null);
  const [newStage, setNewStage] = useState(1);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  const loadUsers = (s) => api.get("/master/users", { params: s ? { search: s } : {} }).then((r) => setUsers(r.data));
  const loadRecs = () => api.get("/master/recommendations").then((r) => setRecs(r.data));
  useEffect(() => { loadUsers(); loadRecs(); api.get("/master/settings").then((r) => setSettings(r.data)); }, []);

  const openDetail = async (id) => {
    const { data } = await api.get(`/master/users/${id}`);
    setDetail(data); setNewStage(data.current_stage_order); setReason("");
  };

  const decide = async (action) => {
    if (!reason.trim()) return toast.error("O motivo da decisão é obrigatório.");
    setBusy(true);
    try {
      await api.post(`/master/users/${detail.id}/stage`, { new_stage_order: newStage, reason, action });
      toast.success(action === "maintain" ? "Etapa mantida e registrada." : "Etapa alterada e registrada.");
      await openDetail(detail.id); await loadUsers(q); await loadRecs();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const resolveRec = async (r, accept) => {
    try {
      await api.post(`/master/recommendations/${r.id}/resolve`, { accept, reason: accept ? `Recomendação do formador aceita: ${r.justification}` : "" });
      toast.success(accept ? "Recomendação aceita e etapa aplicada." : "Recomendação recusada.");
      await loadRecs(); await loadUsers(q);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const toggleSkip = async () => {
    const v = !settings.allow_stage_skip;
    await api.put("/master/settings", { allow_stage_skip: v });
    setSettings({ ...settings, allow_stage_skip: v });
    toast.success("Configuração salva.");
  };

  if (!users) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><Crown className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Controle Mestre</h1></div>
        <p className="text-stone-500 text-sm mb-5">Autoridade exclusiva sobre as etapas de formação. Toda decisão exige motivo e é auditada.</p>

        <div className="grid grid-cols-2 gap-3 mb-6">
          <button data-testid="master-report-btn" onClick={() => nav("/app/mestre/relatorio")} className="rounded-xl border border-stone-800 bg-stone-900 p-4 text-left active:scale-[0.99] transition-transform">
            <ClipboardList className="w-5 h-5 text-orange-500 mb-1" /><p className="font-heading font-bold text-sm">Relatório Pastoral</p><p className="text-[11px] text-stone-500">Quem concluiu e aguarda</p>
          </button>
          <button data-testid="master-reqs-btn" onClick={() => nav("/app/mestre/requisitos")} className="rounded-xl border border-stone-800 bg-stone-900 p-4 text-left active:scale-[0.99] transition-transform">
            <SlidersHorizontal className="w-5 h-5 text-orange-500 mb-1" /><p className="font-heading font-bold text-sm">Requisitos por Etapa</p><p className="text-[11px] text-stone-500">O que conta como concluída</p>
          </button>
          <button data-testid="master-perms-btn" onClick={() => nav("/app/mestre/permissoes")} className="rounded-xl border border-stone-800 bg-stone-900 p-4 text-left active:scale-[0.99] transition-transform">
            <Lock className="w-5 h-5 text-orange-500 mb-1" /><p className="font-heading font-bold text-sm">Permissões</p><p className="text-[11px] text-stone-500">Conteúdo e lives por formador</p>
          </button>
        </div>

        {settings && (
          <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 mb-6 flex items-center gap-3">
            <Settings className="w-4 h-4 text-orange-500" />
            <span className="flex-1 text-sm">Permitir salto de etapas</span>
            <button data-testid="toggle-skip" onClick={toggleSkip} className={`text-xs font-semibold rounded-full px-3 py-1 ${settings.allow_stage_skip ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-400"}`}>{settings.allow_stage_skip ? "SIM" : "NÃO"}</button>
          </div>
        )}

        {recs.length > 0 && (
          <section className="mb-6">
            <h3 className="font-heading font-bold text-sm text-yellow-500 mb-3">Recomendações de formadores</h3>
            <div className="space-y-3">
              {recs.map((r) => (
                <div key={r.id} data-testid={`master-rec-${r.id}`} className="rounded-2xl border border-yellow-500/40 bg-yellow-500/5 p-4">
                  <p className="font-medium text-sm">{r.user_name}: {STAGES[r.current_stage_order - 1]} → {STAGES[r.recommended_stage_order - 1]}</p>
                  <p className="text-xs text-stone-400 mt-1">{r.formador_name}: "{r.justification}"</p>
                  <div className="flex gap-2 mt-3">
                    <button data-testid={`rec-accept-${r.id}`} onClick={() => resolveRec(r, true)} className="flex-1 min-h-[42px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-1"><Check className="w-4 h-4" />Aceitar e aplicar</button>
                    <button data-testid={`rec-reject-${r.id}`} onClick={() => resolveRec(r, false)} className="flex-1 min-h-[42px] rounded-lg border border-stone-700 text-stone-300 text-sm flex items-center justify-center gap-1"><X className="w-4 h-4" />Recusar</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Gestão das etapas</h3>
        <div className="flex gap-2 mb-4">
          <input data-testid="master-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome ou e-mail..."
            className="flex-1 min-h-[46px] rounded-xl bg-stone-900 border border-stone-800 px-4 text-stone-50 placeholder-stone-500 outline-none focus:border-orange-600/60" />
          <button data-testid="master-search-btn" onClick={() => loadUsers(q)} className="min-w-[46px] rounded-xl bg-orange-600 flex items-center justify-center text-white"><Search className="w-5 h-5" /></button>
        </div>

        <div className="space-y-2">
          {users.map((u) => (
            <button key={u.id} data-testid={`master-user-${u.id}`} onClick={() => openDetail(u.id)}
              className="w-full text-left rounded-xl border border-stone-800 bg-stone-900 p-3.5 active:scale-[0.99] transition-transform">
              <div className="flex justify-between items-center">
                <div><p className="font-medium text-sm">{u.name}</p><p className="text-xs text-stone-500">{u.stage_name} · {u.progress_percent}%</p></div>
                {u.formation_concluded && <span className="text-[10px] text-orange-400 border border-orange-600/40 rounded-full px-2 py-0.5">formação ok</span>}
              </div>
            </button>
          ))}
        </div>
      </div>

      {detail && (
        <div className="fixed inset-0 z-[60] bg-black/70 flex items-end sm:items-center justify-center p-4 overflow-y-auto" onClick={() => setDetail(null)}>
          <div className="w-full max-w-md rounded-2xl border border-stone-800 bg-stone-900 p-5 my-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-heading font-black text-xl">{detail.name}</h3>
            <p className="text-stone-500 text-sm">{detail.email}</p>
            <div className="grid grid-cols-2 gap-2 my-4 text-sm">
              <div className="rounded-lg bg-stone-800/60 p-3"><p className="text-[10px] text-stone-500 uppercase">Etapa atual</p><p className="font-semibold">{detail.stage_name}</p></div>
              <div className="rounded-lg bg-stone-800/60 p-3"><p className="text-[10px] text-stone-500 uppercase">Progresso</p><p className="font-semibold text-orange-500">{detail.formation.percent}%</p></div>
              <div className="rounded-lg bg-stone-800/60 p-3"><p className="text-[10px] text-stone-500 uppercase">Formação</p><p className="font-semibold">{detail.formation.concluded ? "Concluída" : "Em andamento"}</p></div>
              <div className="rounded-lg bg-stone-800/60 p-3"><p className="text-[10px] text-stone-500 uppercase">Lives obrig.</p><p className="font-semibold">{detail.mandatory_lives.ok}/{detail.mandatory_lives.total}</p></div>
            </div>

            <div className="rounded-xl border border-orange-600/30 bg-orange-600/5 p-4 mb-4">
              <p className="text-[11px] uppercase tracking-widest text-orange-500 mb-2">Decisão sobre a etapa</p>
              <select data-testid="master-stage-select" value={newStage} onChange={(e) => setNewStage(Number(e.target.value))}
                className="w-full mb-3 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100">
                {STAGES.map((s, i) => <option key={i} value={i + 1}>{s}</option>)}
              </select>
              <textarea data-testid="master-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Motivo da decisão (obrigatório)"
                className="w-full mb-3 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
              <div className="flex gap-2">
                <button data-testid="master-maintain" disabled={busy} onClick={() => decide("maintain")} className="flex-1 min-h-[46px] rounded-lg border border-stone-700 text-stone-200 text-sm font-medium">Manter etapa</button>
                <button data-testid="master-change" disabled={busy} onClick={() => decide("change")} className="flex-1 min-h-[46px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-1">{busy && <Loader2 className="w-4 h-4 animate-spin" />}Alterar etapa</button>
              </div>
            </div>

            <p className="font-heading font-bold text-sm text-stone-400 mb-2 flex items-center gap-1"><History className="w-4 h-4" /> Histórico da jornada</p>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {detail.history.length === 0 && <p className="text-stone-600 text-xs">Nenhuma alteração registrada.</p>}
              {detail.history.map((h) => (
                <div key={h.id} className="rounded-lg bg-stone-800/50 p-3 text-xs">
                  <p className="text-stone-300">{STAGES[h.previous_stage - 1]} → {STAGES[h.new_stage - 1]} <span className="text-orange-500">· {typeLabel[h.change_type] || "Alteração"}</span></p>
                  <p className="text-stone-500">{new Date(h.changed_at).toLocaleString("pt-BR")} · {h.changed_by_name}</p>
                  <p className="text-stone-400 mt-1">"{h.reason}"</p>
                </div>
              ))}
            </div>
            <button onClick={() => setDetail(null)} className="mt-4 w-full min-h-[44px] rounded-lg border border-stone-700 text-stone-300 text-sm">Fechar</button>
          </div>
        </div>
      )}
    </Shell>
  );
}
