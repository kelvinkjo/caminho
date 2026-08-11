import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { Loader2, Users, Send, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

const radarCls = { green: "bg-green-500", yellow: "bg-yellow-500", red: "bg-red-500" };
const radarLabel = { green: "Bem acompanhado", yellow: "Atenção", red: "Necessita acompanhamento" };
const STAGES = ["Pré-Vocacionado", "Vocacionado", "Discípulo Ano 1", "Discípulo Ano 2", "Compromissado", "Consagrado"];
const recCls = { pending: "text-yellow-500", accepted: "text-green-500", rejected: "text-red-500" };
const recLabel = { pending: "Recomendação pendente", accepted: "Aceita pelo Login Mestre", rejected: "Recusada" };

export default function MyPeople() {
  const [people, setPeople] = useState(null);
  const [recs, setRecs] = useState([]);
  const [form, setForm] = useState(null); // {person}
  const [stage, setStage] = useState(4);
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const [p, r] = await Promise.all([api.get("/formador/people"), api.get("/formador/recommendations").catch(() => ({ data: [] }))]);
    setPeople(p.data); setRecs(r.data);
  };
  useEffect(() => { load(); }, []);

  const openForm = (person) => { setForm(person); setStage(Math.min(person.current_stage_order + 1, 6)); setJustification(""); };

  const submit = async () => {
    if (!justification.trim()) return toast.error("A justificativa é obrigatória.");
    setBusy(true);
    try {
      await api.post("/formador/recommend", { user_id: form.id, recommended_stage_order: stage, justification });
      toast.success("Recomendação enviada ao Login Mestre.");
      setForm(null); await load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  if (!people) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center gap-2 mb-2"><Users className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Minhas Pessoas</h1></div>
        <p className="text-stone-500 text-sm mb-6">Você acompanha e recomenda. A decisão sobre a etapa é do Login Mestre.</p>

        <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Radar pastoral</h3>
        <div className="space-y-2 mb-8">
          {people.map((p) => (
            <div key={p.id} data-testid={`person-${p.id}`} className="rounded-2xl border border-stone-800 bg-stone-900 p-4">
              <div className="flex items-center gap-3">
                <span className={`w-3 h-3 rounded-full shrink-0 ${radarCls[p.radar]}`} title={radarLabel[p.radar]} />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{p.name}</p>
                  <p className="text-xs text-stone-500">{p.stage_name} · {p.progress.percent}% · {radarLabel[p.radar]}</p>
                </div>
                {p.formation_concluded && <span className="text-[10px] text-orange-400 border border-orange-600/40 rounded-full px-2 py-0.5 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />formação ok</span>}
              </div>
              {p.recommendation_pending ? (
                <p className="mt-3 text-xs text-yellow-500">🟡 Recomendação pendente com o Login Mestre</p>
              ) : (
                <button data-testid={`recommend-${p.id}`} onClick={() => openForm(p)}
                  className="mt-3 w-full min-h-[44px] rounded-lg border border-stone-700 text-stone-200 text-sm font-medium flex items-center justify-center gap-2 active:scale-95 transition-transform">
                  <Send className="w-4 h-4" /> Recomendar alteração de etapa
                </button>
              )}
            </div>
          ))}
          {people.length === 0 && <p className="text-stone-500 text-sm">Nenhuma pessoa vinculada ainda.</p>}
        </div>

        {recs.length > 0 && (
          <>
            <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Minhas recomendações</h3>
            <div className="space-y-2">
              {recs.map((r) => (
                <div key={r.id} className="rounded-xl border border-stone-800 bg-stone-900 p-3.5">
                  <p className="font-medium text-sm">{r.user_name} → {STAGES[r.recommended_stage_order - 1]}</p>
                  <p className="text-xs text-stone-500 mt-0.5">{r.justification}</p>
                  <p className={`text-xs mt-1 ${recCls[r.status]}`}>{recLabel[r.status]}</p>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {form && (
        <div className="fixed inset-0 z-[60] bg-black/70 flex items-end sm:items-center justify-center p-4" onClick={() => setForm(null)}>
          <div className="w-full max-w-md rounded-2xl border border-stone-800 bg-stone-900 p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-heading font-bold text-lg mb-1">Recomendar alteração</h3>
            <p className="text-stone-500 text-sm mb-4">{form.name} · atual: {form.stage_name}</p>
            <label className="text-xs text-stone-400">Etapa recomendada</label>
            <select data-testid="recommend-stage-select" value={stage} onChange={(e) => setStage(Number(e.target.value))}
              className="w-full mt-1 mb-4 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100">
              {STAGES.map((s, i) => <option key={i} value={i + 1}>{s}</option>)}
            </select>
            <label className="text-xs text-stone-400">Justificativa (obrigatória)</label>
            <textarea data-testid="recommend-justification" value={justification} onChange={(e) => setJustification(e.target.value)} rows={3}
              placeholder="Ex.: após acompanhamento e discernimento da caminhada..."
              className="w-full mt-1 mb-4 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <div className="flex gap-2">
              <button onClick={() => setForm(null)} className="flex-1 min-h-[46px] rounded-lg border border-stone-700 text-stone-300 text-sm">Cancelar</button>
              <button data-testid="recommend-submit" disabled={busy} onClick={submit} className="flex-1 min-h-[46px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-2">
                {busy && <Loader2 className="w-4 h-4 animate-spin" />} Enviar
              </button>
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
