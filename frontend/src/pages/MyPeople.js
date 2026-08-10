import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { Loader2, Check, RotateCcw, Users } from "lucide-react";
import { toast } from "sonner";

const radarCls = { green: "bg-green-500", yellow: "bg-yellow-500", red: "bg-red-500" };
const radarLabel = { green: "Bem acompanhado", yellow: "Atenção", red: "Necessita acompanhamento" };

export default function MyPeople() {
  const [people, setPeople] = useState(null);
  const [approvals, setApprovals] = useState([]);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    const [p, a] = await Promise.all([api.get("/formador/people"), api.get("/approvals")]);
    setPeople(p.data); setApprovals(a.data);
  };
  useEffect(() => { load(); }, []);

  const act = async (id, kind) => {
    setBusy(id);
    try {
      if (kind === "approve") await api.post(`/approvals/${id}/approve`);
      else await api.post(`/approvals/${id}/followup`, { note: "Vamos caminhar mais um pouco juntos." });
      toast.success(kind === "approve" ? "Etapa aprovada!" : "Acompanhamento solicitado.");
      await load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  if (!people) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center gap-2 mb-6"><Users className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Minhas Pessoas</h1></div>

        {approvals.length > 0 && (
          <section className="mb-8">
            <h3 className="font-heading font-bold text-sm text-yellow-500 mb-3">Aguardando avaliação</h3>
            <div className="space-y-3">
              {approvals.map((a) => (
                <div key={a.id} data-testid={`approval-${a.id}`} className="rounded-2xl border border-yellow-500/40 bg-yellow-500/5 p-4">
                  <p className="font-medium">{a.user_name}</p>
                  <p className="text-xs text-stone-500 mb-3">Concluiu a etapa {a.stage_order} e pede avaliação.</p>
                  <div className="flex gap-2">
                    <button data-testid={`approve-${a.id}`} disabled={busy === a.id} onClick={() => act(a.id, "approve")}
                      className="flex-1 min-h-[44px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-1 transition-colors">
                      <Check className="w-4 h-4" /> Aprovar
                    </button>
                    <button data-testid={`followup-${a.id}`} disabled={busy === a.id} onClick={() => act(a.id, "followup")}
                      className="flex-1 min-h-[44px] rounded-lg border border-stone-700 text-stone-300 text-sm font-medium flex items-center justify-center gap-1">
                      <RotateCcw className="w-4 h-4" /> Acompanhar
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Radar pastoral</h3>
        <div className="space-y-2">
          {people.map((p) => (
            <div key={p.id} data-testid={`person-${p.id}`} className="rounded-2xl border border-stone-800 bg-stone-900 p-4 flex items-center gap-3">
              <span className={`w-3 h-3 rounded-full shrink-0 ${radarCls[p.radar]}`} title={radarLabel[p.radar]} />
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{p.name}</p>
                <p className="text-xs text-stone-500">{p.stage_name} · {p.progress.percent}% · {radarLabel[p.radar]}</p>
              </div>
              {p.awaiting_approval && <span className="text-[10px] text-yellow-500 border border-yellow-500/40 rounded-full px-2 py-0.5">avaliar</span>}
            </div>
          ))}
          {people.length === 0 && <p className="text-stone-500 text-sm">Nenhuma pessoa vinculada ainda.</p>}
        </div>
      </div>
    </Shell>
  );
}
