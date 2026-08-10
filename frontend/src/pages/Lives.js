import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { Radio, Loader2, CheckCircle2, Lock, PlayCircle } from "lucide-react";
import { toast } from "sonner";

const TABS = [
  { key: "live_now", label: "Ao vivo" },
  { key: "upcoming", label: "Próximas" },
  { key: "recorded", label: "Gravadas" },
];

export default function Lives() {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("live_now");
  const [busy, setBusy] = useState(null);

  const load = () => api.get("/lives").then((r) => setData(r.data));
  useEffect(() => { load(); }, []);

  const confirmPresence = async (l) => {
    setBusy(l.id);
    try {
      const { data: res } = await api.post(`/lives/${l.id}/presence`, { percent: 100 });
      toast.success(res.confirmed ? "Presença confirmada!" : "Presença parcial registrada.");
      await load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  if (!data) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  const list = data[tab] || [];

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center gap-2 mb-5"><Radio className="w-6 h-6 text-red-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Lives</h1></div>

        <div className="flex gap-2 mb-6">
          {TABS.map((t) => (
            <button key={t.key} data-testid={`lives-tab-${t.key}`} onClick={() => setTab(t.key)}
              className={`flex-1 min-h-[42px] rounded-xl text-sm font-medium transition-colors ${tab === t.key ? "bg-orange-600 text-white" : "bg-stone-900 border border-stone-800 text-stone-400"}`}>
              {t.label}{data[t.key]?.length ? ` (${data[t.key].length})` : ""}
            </button>
          ))}
        </div>

        {list.length === 0 && <p className="text-stone-500 text-sm text-center py-8">Nada por aqui ainda.</p>}

        <div className="space-y-3">
          {list.map((l) => (
            <div key={l.id} data-testid={`live-${l.id}`} className="rounded-2xl border border-stone-800 bg-stone-900 overflow-hidden">
              <div className="h-28 bg-[radial-gradient(ellipse_at_center,_rgba(220,38,38,0.22),_transparent_70%)] flex items-center justify-center relative">
                {tab === "live_now" ? <span className="absolute top-3 left-3 text-[10px] font-bold text-white bg-red-600 rounded-full px-2 py-0.5 animate-pulse">● AO VIVO</span> : null}
                {l.required && <span className="absolute top-3 right-3 text-[10px] font-bold text-yellow-400 border border-yellow-500/50 bg-yellow-500/10 rounded-full px-2 py-0.5">OBRIGATÓRIA</span>}
                {tab === "recorded" ? <PlayCircle className="w-10 h-10 text-stone-300" /> : <Radio className="w-9 h-9 text-red-500" />}
              </div>
              <div className="p-4">
                <h4 className="font-heading font-bold">{l.title}</h4>
                <p className="text-stone-400 text-sm mt-1">{l.description}</p>
                <p className="text-stone-500 text-xs mt-2">{l.former} · {new Date(l.date).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</p>

                {l.presence_confirmed ? (
                  <div className="mt-3 flex items-center gap-2 text-orange-500 text-sm"><CheckCircle2 className="w-4 h-4" /> Presença confirmada ({l.presence_percent}%)</div>
                ) : (
                  <button data-testid={`presence-${l.id}`} disabled={busy === l.id} onClick={() => confirmPresence(l)}
                    className="mt-3 w-full min-h-[44px] rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-2 transition-colors active:scale-95 disabled:opacity-60">
                    {busy === l.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                    {tab === "recorded" ? "Assistir e registrar presença" : "Entrar e confirmar presença"}
                  </button>
                )}
                <p className="text-stone-600 text-[11px] mt-2 flex items-center gap-1"><Lock className="w-3 h-3" /> Presença mínima exigida: {l.min_presence}%</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}
