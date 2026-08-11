import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { STAGE_ICONS, statusMeta } from "../lib/stages";
import { Lock, Check, Loader2, CheckCircle2, Clock } from "lucide-react";

export default function Journey() {
  const [stages, setStages] = useState(null);
  const [fstatus, setFstatus] = useState(null);
  const nav = useNavigate();

  useEffect(() => {
    api.get("/stages").then((r) => setStages(r.data));
    api.get("/formation/status").then((r) => setFstatus(r.data));
  }, []);

  if (!stages) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  const current = stages.find((s) => s.status === "current");

  return (
    <Shell>
      <div className="fade-up">
        <h1 className="font-heading font-black text-3xl tracking-tight mb-1">Minha Jornada</h1>
        <p className="text-stone-500 text-sm mb-8">Encontro · Discernimento · Formação · Discipulado · Missão · Entrega</p>

        <div className="relative pl-2">
          <div className="absolute left-[27px] top-2 bottom-2 w-0.5 bg-stone-800" />
          <div className="space-y-3">
            {stages.map((s) => {
              const Icon = STAGE_ICONS[s.icon];
              const meta = statusMeta(s.status);
              const locked = s.status === "locked";
              const node =
                s.status === "completed" ? "bg-orange-600 border-orange-500 text-white" :
                s.status === "current" ? "border-orange-500 text-orange-500 bg-orange-500/10 glow-current" :
                "border-stone-800 text-stone-600 bg-stone-900";
              return (
                <button key={s.order} data-testid={`journey-stage-${s.order}`}
                  disabled={locked}
                  onClick={() => !locked && nav(`/app/formacao/${s.order}`)}
                  className={`relative z-10 w-full flex items-center gap-4 text-left rounded-2xl border p-4 transition-all ${locked ? "opacity-70 border-stone-800 bg-stone-900/60" : "border-stone-800 bg-stone-900 active:scale-[0.99]"}`}>
                  <div className={`w-12 h-12 shrink-0 rounded-full border-2 flex items-center justify-center ${node}`}>
                    {s.status === "completed" ? <Check className="w-5 h-5" /> : locked ? <Lock className="w-4 h-4" /> : <Icon className="w-5 h-5" strokeWidth={1.75} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-[11px] uppercase tracking-wide ${meta.cls}`}>{s.theme} · {s.status === "current" ? "Etapa atual" : meta.label}</p>
                    <h3 className="font-heading font-bold text-base leading-tight">{s.name}</h3>
                    {!locked && (
                      <div className="mt-2 h-1.5 rounded-full bg-stone-800 overflow-hidden">
                        <div className="h-full bg-orange-600 rounded-full" style={{ width: `${s.progress.percent}%` }} />
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Progresso formativo ≠ etapa: conclusão NÃO promove */}
        {current && (
          <div data-testid="formation-status-card" className="mt-8 rounded-2xl border border-stone-800 bg-stone-900 p-5">
            <p className="text-stone-500 text-xs uppercase tracking-widest mb-2">Progresso formativo — {current.name}</p>
            <div className="h-2 rounded-full bg-stone-800 overflow-hidden mb-3"><div className="h-full bg-orange-600 rounded-full" style={{ width: `${current.progress.percent}%` }} /></div>
            {fstatus?.concluded ? (
              <div>
                <p className="flex items-center gap-2 text-orange-400 font-semibold"><CheckCircle2 className="w-5 h-5" /> Formação concluída</p>
                <p className="text-stone-400 text-sm mt-2 flex items-start gap-2"><Clock className="w-4 h-4 mt-0.5 shrink-0 text-yellow-500" /> {fstatus.next_step}</p>
              </div>
            ) : (
              <p className="text-stone-400 text-sm">{fstatus?.next_step || "Continue sua formação nesta etapa, no seu ritmo."}</p>
            )}
          </div>
        )}
      </div>
    </Shell>
  );
}
