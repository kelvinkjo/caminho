import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, ClipboardList, Clock } from "lucide-react";

export default function PastoralReport() {
  const [data, setData] = useState(null);
  const nav = useNavigate();
  useEffect(() => { api.get("/master/pastoral-report").then((r) => setData(r.data)); }, []);

  if (!data) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  const max = Math.max(1, ...data.by_stage.map((s) => s.total));

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><ClipboardList className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Relatório Pastoral</h1></div>
        <p className="text-stone-500 text-sm mb-6">{data.total_membros} membros · {data.awaiting_count} aguardando decisão da liderança.</p>

        <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Formação concluída por etapa</h3>
        <div className="space-y-3 mb-8">
          {data.by_stage.map((s) => (
            <div key={s.order} data-testid={`report-stage-${s.order}`} className="rounded-2xl border border-stone-800 bg-stone-900 p-4">
              <div className="flex justify-between text-sm mb-2"><span className="font-medium">{s.stage}</span><span className="text-orange-500 font-semibold">{s.concluded}/{s.total} concluíram</span></div>
              <div className="h-2 rounded-full bg-stone-800 overflow-hidden">
                <div className="h-full bg-orange-600 rounded-full" style={{ width: `${(s.total ? s.concluded / s.total : 0) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>

        <h3 className="font-heading font-bold text-sm text-yellow-500 mb-3 flex items-center gap-2"><Clock className="w-4 h-4" /> Aguardando decisão</h3>
        <div className="space-y-2">
          {data.awaiting.length === 0 && <p className="text-stone-500 text-sm">Ninguém aguardando decisão no momento.</p>}
          {data.awaiting.map((m) => (
            <button key={m.id} data-testid={`awaiting-${m.id}`} onClick={() => nav("/app/mestre")}
              className="w-full text-left rounded-xl border border-yellow-500/30 bg-yellow-500/5 p-3.5 active:scale-[0.99] transition-transform">
              <p className="font-medium text-sm">{m.name}</p>
              <p className="text-xs text-stone-400">{m.stage_name} · {m.percent}% · Formador: {m.formador}</p>
            </button>
          ))}
        </div>
      </div>
    </Shell>
  );
}
