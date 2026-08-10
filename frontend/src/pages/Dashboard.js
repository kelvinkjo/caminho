import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { STAGE_ICONS, statusMeta } from "../lib/stages";
import { Radio, Flame, CalendarDays, ChevronRight, Play, CheckCircle2, Loader2 } from "lucide-react";

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}

export default function Dashboard() {
  const [d, setD] = useState(null);
  const nav = useNavigate();

  useEffect(() => { api.get("/dashboard").then((r) => setD(r.data)); }, []);

  if (!d) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  const StageIcon = STAGE_ICONS[d.stage?.icon] || Flame;
  const meta = statusMeta("current");

  return (
    <Shell>
      <div className="fade-up space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-stone-500 text-sm">{greeting()},</p>
            <h1 className="font-heading font-black text-2xl tracking-tight">{d.user.name.split(" ")[0]}</h1>
          </div>
          <div className="w-11 h-11 rounded-full bg-stone-800 border border-stone-700 flex items-center justify-center font-heading font-bold text-orange-500">
            {d.user.name[0]}
          </div>
        </header>

        {/* Palavra do dia */}
        {d.word?.reference && (
          <section data-testid="word-of-day" className="rounded-2xl border border-stone-800 bg-stone-900 p-6 relative overflow-hidden">
            <div className="absolute -right-6 -top-6 w-24 h-24 bg-[radial-gradient(circle,_rgba(234,88,12,0.15),_transparent_70%)]" />
            <p className="text-orange-500 uppercase tracking-widest text-[11px] font-semibold mb-3">Palavra do dia</p>
            <p className="font-serifq italic text-2xl text-stone-200 leading-snug">"{d.word.text}"</p>
            <p className="text-stone-500 text-sm mt-3">{d.word.reference}</p>
          </section>
        )}

        {/* Minha jornada */}
        <button data-testid="dash-journey-card" onClick={() => nav("/app/jornada")}
          className="w-full text-left rounded-2xl border border-orange-600/40 bg-orange-600/10 p-5 flex items-center gap-4 active:scale-[0.99] transition-transform">
          <div className="w-12 h-12 rounded-xl bg-orange-600/20 border border-orange-600/40 flex items-center justify-center">
            <StageIcon className="w-6 h-6 text-orange-500" strokeWidth={1.75} />
          </div>
          <div className="flex-1">
            <p className={`text-xs ${meta.cls}`}>Sua etapa · {d.stage?.theme}</p>
            <h3 className="font-heading font-bold text-lg leading-tight">{d.stage?.name}</h3>
            <div className="mt-2 h-1.5 rounded-full bg-stone-800 overflow-hidden">
              <div className="h-full bg-orange-600 rounded-full transition-all" style={{ width: `${d.progress.percent}%` }} />
            </div>
          </div>
          <ChevronRight className="text-stone-500" />
        </button>

        {/* Continue */}
        {d.continue_lesson && (
          <section>
            <h4 className="font-heading font-bold text-sm text-stone-400 mb-2">Continue sua formação</h4>
            <button data-testid="continue-lesson" onClick={() => nav(`/app/aula/${d.continue_lesson.id}`)}
              className="w-full text-left rounded-2xl border border-stone-800 bg-stone-900 p-4 flex items-center gap-3 active:scale-[0.99] transition-transform">
              <div className="w-11 h-11 rounded-xl bg-orange-600 flex items-center justify-center"><Play className="w-5 h-5 text-white" /></div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-stone-500 truncate">{d.continue_lesson.module_title}</p>
                <p className="font-medium truncate">{d.continue_lesson.title}</p>
              </div>
            </button>
          </section>
        )}

        {/* Próxima live */}
        {d.next_live && (
          <section className="rounded-2xl border border-stone-800 bg-stone-900 p-5 flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-red-600/20 border border-red-600/40 flex items-center justify-center"><Radio className="w-5 h-5 text-red-500" /></div>
            <div className="flex-1">
              <p className="text-red-500 text-xs font-semibold uppercase tracking-wide">Próxima live</p>
              <p className="font-medium">{d.next_live.title}</p>
              <p className="text-stone-500 text-xs">{new Date(d.next_live.date).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</p>
            </div>
          </section>
        )}

        {/* Missão da semana */}
        <section>
          <h4 className="font-heading font-bold text-sm text-stone-400 mb-2 flex items-center gap-2"><Flame className="w-4 h-4 text-orange-500" /> Missão da semana</h4>
          <div className="space-y-2">
            {d.missions.map((m) => (
              <button key={m.id} data-testid={`dash-mission-${m.id}`} onClick={() => nav("/app/missao")}
                className="w-full text-left rounded-xl border border-stone-800 bg-stone-900 p-3.5 flex items-center gap-3 active:scale-[0.99] transition-transform">
                <CheckCircle2 className={`w-5 h-5 ${m.completed ? "text-orange-500" : "text-stone-600"}`} />
                <span className={`flex-1 text-sm ${m.completed ? "line-through text-stone-500" : ""}`}>{m.title}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Agenda */}
        {d.events?.length > 0 && (
          <section>
            <h4 className="font-heading font-bold text-sm text-stone-400 mb-2 flex items-center gap-2"><CalendarDays className="w-4 h-4 text-orange-500" /> Agenda</h4>
            <div className="space-y-2">
              {d.events.map((e) => (
                <div key={e.id} className="rounded-xl border border-stone-800 bg-stone-900 p-3.5 flex items-center gap-3">
                  <div className="text-center min-w-[44px]">
                    <p className="font-heading font-bold text-orange-500 text-lg leading-none">{new Date(e.date).getDate()}</p>
                    <p className="text-[10px] text-stone-500 uppercase">{new Date(e.date).toLocaleString("pt-BR", { month: "short" })}</p>
                  </div>
                  <div><p className="font-medium text-sm">{e.title}</p><p className="text-xs text-stone-500 capitalize">{e.kind}</p></div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </Shell>
  );
}
