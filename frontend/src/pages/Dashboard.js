import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { STAGE_ICONS, statusMeta } from "../lib/stages";
import { Radio, Flame, CalendarDays, ChevronRight, Play, CheckCircle2, Loader2, Search, Sparkles, BookOpen, Bell, Megaphone } from "lucide-react";

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}

function NotificationsBanner({ items }) {  const [list, setList] = useState(items);
  const dismiss = async () => { try { await api.post("/notifications/read"); } catch {} setList([]); };
  if (!list.length) return null;
  return (
    <section data-testid="notifications-banner" className="rounded-2xl border border-orange-600/40 bg-orange-600/10 p-4">
      <div className="flex items-start gap-3">
        <Bell className="w-5 h-5 text-orange-500 shrink-0 mt-0.5" />
        <div className="flex-1">
          {list.slice(0, 3).map((n) => (
            <div key={n.id} className="mb-1 last:mb-0">
              <p className="text-sm font-semibold">{n.title}</p>
              <p className="text-xs text-stone-400">{n.body}</p>
            </div>
          ))}
        </div>
        <button data-testid="notifications-dismiss" onClick={dismiss} className="text-xs text-orange-400 shrink-0">Marcar lida</button>
      </div>
    </section>
  );
}

function Recommendations({ nav }) {  const [rec, setRec] = useState(null);
  useEffect(() => { api.get("/recommendations").then((r) => setRec(r.data)).catch(() => setRec(false)); }, []);
  if (!rec) return null;
  return (
    <section data-testid="recommendations" className="rounded-2xl border border-orange-600/30 bg-stone-900 p-5">
      <p className="text-orange-500 uppercase tracking-widest text-[11px] font-semibold mb-3 flex items-center gap-1.5"><Sparkles className="w-3.5 h-3.5" /> Para você hoje</p>
      {rec.tip && <p className="font-serifq italic text-lg text-stone-300 leading-snug mb-3">{rec.tip}</p>}
      <div className="space-y-2">
        {rec.next_lesson && (
          <button data-testid="rec-lesson" onClick={() => nav(`/app/aula/${rec.next_lesson.id}`)} className="w-full flex items-center gap-3 text-left rounded-xl bg-stone-800/60 border border-stone-800 p-3 active:scale-[0.99] transition-transform">
            <BookOpen className="w-4 h-4 text-orange-500 shrink-0" /><span className="flex-1 text-sm truncate">Próxima aula: {rec.next_lesson.title}</span><ChevronRight className="w-4 h-4 text-stone-500" />
          </button>
        )}
        {rec.mission && (
          <button data-testid="rec-mission" onClick={() => nav("/app/missao")} className="w-full flex items-center gap-3 text-left rounded-xl bg-stone-800/60 border border-stone-800 p-3 active:scale-[0.99] transition-transform">
            <Flame className="w-4 h-4 text-orange-500 shrink-0" /><span className="flex-1 text-sm truncate">Missão: {rec.mission.title}</span><ChevronRight className="w-4 h-4 text-stone-500" />
          </button>
        )}
      </div>
    </section>
  );
}

function Announcements() {
  const [items, setItems] = useState(null);
  useEffect(() => { api.get("/announcements").then((r) => setItems(r.data)).catch(() => setItems([])); }, []);
  if (!items || items.length === 0) return null;
  const pr = { urgent: "border-red-600/40 bg-red-600/10", important: "border-yellow-600/40 bg-yellow-600/10", normal: "border-stone-800 bg-stone-900" };
  return (
    <section data-testid="announcements">
      <h4 className="font-heading font-bold text-sm text-stone-400 mb-2 flex items-center gap-2"><Megaphone className="w-4 h-4 text-orange-500" /> Comunicados</h4>
      <div className="space-y-2">
        {items.slice(0, 4).map((a) => (
          <div key={a.id} data-testid={`announcement-${a.id}`} className={`rounded-xl border p-3.5 ${pr[a.priority] || pr.normal}`}>
            {a.pinned && <span className="text-[10px] text-orange-500">📌 fixado</span>}
            <p className="font-medium text-sm">{a.title}</p>
            <p className="text-xs text-stone-400 mt-0.5">{a.message}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function LiveBadge({ nav }) {
  const [live, setLive] = useState([]);
  useEffect(() => { api.get("/live-broadcasts").then((r) => setLive(r.data)).catch(() => setLive([])); }, []);
  if (!live.length) return null;
  const b = live[0];
  return (
    <button data-testid="dash-live-badge" onClick={() => nav(`/app/ao-vivo/${b.id}`)}
      className="w-full text-left rounded-2xl border border-red-600/50 bg-red-600/15 p-4 flex items-center gap-3 active:scale-[0.99] transition-transform">
      <span className="relative flex h-3 w-3"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75" /><span className="relative inline-flex rounded-full h-3 w-3 bg-red-600" /></span>
      <div className="flex-1 min-w-0">
        <p className="text-red-400 text-xs font-bold uppercase tracking-wide">🔴 Ao vivo agora</p>
        <p className="font-heading font-bold truncate">{b.title}</p>
        <p className="text-stone-400 text-xs truncate">{b.presenter_name}{live.length > 1 ? ` · +${live.length - 1} transmissão(ões)` : ""}</p>
      </div>
      <span className="text-xs font-semibold text-white bg-red-600 rounded-full px-3 py-1.5">Assistir</span>
    </button>
  );
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
          <div className="flex items-center gap-3">
            <button data-testid="header-notifications" onClick={() => nav("/app/notificacoes")} className="relative w-11 h-11 rounded-full bg-stone-900 border border-stone-800 flex items-center justify-center text-stone-400 active:scale-95 transition-transform">
              <Bell className="w-5 h-5" />
              {d.notifications?.length > 0 && <span className="absolute top-2 right-2.5 w-2 h-2 rounded-full bg-orange-500" />}
            </button>
            <button data-testid="header-search" onClick={() => nav("/app/busca")} className="w-11 h-11 rounded-full bg-stone-900 border border-stone-800 flex items-center justify-center text-stone-400 active:scale-95 transition-transform">
              <Search className="w-5 h-5" />
            </button>
            <div className="w-11 h-11 rounded-full bg-stone-800 border border-stone-700 flex items-center justify-center font-heading font-bold text-orange-500">
              {d.user.name[0]}
            </div>
          </div>
        </header>

        {/* Ao vivo agora */}
        <LiveBadge nav={nav} />

        {/* Notificações não lidas */}
        {d.notifications?.length > 0 && (
          <NotificationsBanner items={d.notifications} />
        )}

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

        {/* Etapa oficial x progresso formativo (conclusão NÃO promove) */}
        {d.formation && (
          <section data-testid="dash-formation-status" className="rounded-2xl border border-stone-800 bg-stone-900 p-5">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[10px] text-stone-500 uppercase tracking-widest">Minha etapa</p>
                <p className="font-heading font-bold text-sm mt-1">{d.stage?.name}</p>
              </div>
              <div>
                <p className="text-[10px] text-stone-500 uppercase tracking-widest">Progresso formativo</p>
                <p className="font-heading font-bold text-sm mt-1 text-orange-500">{d.formation.percent}%</p>
              </div>
            </div>
            <div className="mt-3 pt-3 border-t border-stone-800">
              <p className="text-[10px] text-stone-500 uppercase tracking-widest">Status</p>
              <p className="text-sm mt-1">{d.formation.concluded ? <span className="text-orange-400 font-semibold">Formação concluída</span> : "Em formação"}</p>
              {d.formation.concluded && <p className="text-stone-400 text-xs mt-2">Próximo passo: aguardando decisão da liderança.</p>}
            </div>
          </section>
        )}

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

        {/* Recomendações IA */}
        <Recommendations nav={nav} />

        {/* Comunicados */}
        <Announcements />

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
