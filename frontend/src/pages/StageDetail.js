import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, CheckCircle2, Circle, Play, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function StageDetail() {
  const { order } = useParams();
  const [data, setData] = useState(null);
  const nav = useNavigate();
  useEffect(() => {
    api.get(`/stages/${order}/modules`).then((r) => setData(r.data))
      .catch((e) => {
        if (e.response?.status === 403) { toast.error("Etapa bloqueada. Avance na sua jornada primeiro."); nav("/app/jornada", { replace: true }); }
      });
  }, [order, nav]);

  if (!data) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <p className="text-[11px] uppercase tracking-widest text-orange-500">{data.stage?.theme}</p>
        <h1 className="font-heading font-black text-3xl tracking-tight">{data.stage?.name}</h1>
        <p className="font-serifq italic text-xl text-stone-400 mt-2">"{data.stage?.question}"</p>

        <div className="mt-4 rounded-xl border border-stone-800 bg-stone-900 p-4">
          <div className="flex justify-between text-sm mb-2"><span className="text-stone-400">Progresso da etapa</span><span className="font-semibold text-orange-500">{data.progress.percent}%</span></div>
          <div className="h-2 rounded-full bg-stone-800 overflow-hidden"><div className="h-full bg-orange-600 rounded-full transition-all" style={{ width: `${data.progress.percent}%` }} /></div>
        </div>

        <div className="mt-8 space-y-6">
          {data.modules.map((m) => (
            <div key={m.id}>
              <h3 className="font-heading font-bold text-lg mb-3">{m.title}</h3>
              <div className="space-y-2">
                {m.lessons.map((l) => (
                  <button key={l.id} data-testid={`lesson-${l.id}`} onClick={() => nav(`/app/aula/${l.id}`)}
                    className="w-full flex items-center gap-3 text-left rounded-xl border border-stone-800 bg-stone-900 p-3.5 active:scale-[0.99] transition-transform">
                    {l.completed ? <CheckCircle2 className="w-5 h-5 text-orange-500 shrink-0" /> : <Circle className="w-5 h-5 text-stone-600 shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{l.title}</p>
                      <p className="text-xs text-stone-500">{l.dimension} · {l.duration_min} min</p>
                    </div>
                    <Play className="w-4 h-4 text-stone-500" />
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}
