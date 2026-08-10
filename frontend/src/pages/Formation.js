import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { STAGE_ICONS } from "../lib/stages";
import { ChevronRight, Loader2 } from "lucide-react";

export default function Formation() {
  const [stages, setStages] = useState(null);
  const nav = useNavigate();
  useEffect(() => { api.get("/stages").then((r) => setStages(r.data)); }, []);

  if (!stages) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <h1 className="font-heading font-black text-3xl tracking-tight mb-6">Formação</h1>
        <div className="space-y-3">
          {stages.map((s) => {
            const Icon = STAGE_ICONS[s.icon];
            const locked = !s.accessible;
            return (
              <button key={s.order} data-testid={`formation-stage-${s.order}`} disabled={locked}
                onClick={() => nav(`/app/formacao/${s.order}`)}
                className={`w-full flex items-center gap-4 text-left rounded-2xl border border-stone-800 p-4 transition-all ${locked ? "opacity-50 bg-stone-900/50" : "bg-stone-900 active:scale-[0.99]"}`}>
                <div className="w-11 h-11 rounded-xl bg-stone-800 flex items-center justify-center text-orange-500"><Icon className="w-5 h-5" strokeWidth={1.75} /></div>
                <div className="flex-1">
                  <p className="text-[11px] uppercase tracking-wide text-stone-500">{s.theme}</p>
                  <h3 className="font-heading font-bold">{s.name}</h3>
                  {s.accessible && <p className="text-xs text-orange-500 mt-0.5">{s.progress.completed}/{s.progress.total} aulas · {s.progress.percent}%</p>}
                </div>
                {!locked && <ChevronRight className="text-stone-500" />}
              </button>
            );
          })}
        </div>
      </div>
    </Shell>
  );
}
