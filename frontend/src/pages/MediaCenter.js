import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { Clapperboard, Loader2, Search, Star, History, Radio, PlayCircle, Plus } from "lucide-react";
import { toast } from "sonner";

const LIVE_LABEL = {
  draft: "Rascunho", scheduled: "Agendada", waiting: "Aguardando transmissão",
  live: "Ao vivo", ended: "Encerrada", unavailable: "Indisponível",
};
const LIVE_COLOR = {
  live: "bg-red-600 text-white animate-pulse", scheduled: "bg-stone-700 text-stone-200",
  waiting: "bg-amber-600/20 text-amber-400 border border-amber-600/40",
  ended: "bg-stone-800 text-stone-400", unavailable: "bg-stone-800 text-stone-500",
  draft: "bg-stone-800 text-stone-500",
};

const TABS = [
  { key: "all", label: "Todos" },
  { key: "video", label: "Vídeos" },
  { key: "live", label: "Lives" },
  { key: "favorites", label: "Favoritos" },
  { key: "history", label: "Histórico" },
];

function MediaCard({ m, onOpen }) {
  const isLive = m.kind === "live";
  return (
    <button data-testid={`media-card-${m.id}`} onClick={() => onOpen(m)}
      className="text-left rounded-2xl border border-stone-800 bg-stone-900 overflow-hidden active:scale-[0.99] transition-transform">
      <div className="relative h-32 bg-stone-800 flex items-center justify-center overflow-hidden">
        {m.thumbnail
          ? <img src={m.thumbnail} alt={m.title} className="w-full h-full object-cover" />
          : (isLive ? <Radio className="w-9 h-9 text-red-500" /> : <PlayCircle className="w-10 h-10 text-stone-400" />)}
        <span className="absolute top-2 left-2 text-[10px] font-bold rounded-full px-2 py-0.5 bg-black/70 text-stone-200 uppercase">{m.provider_name}</span>
        {isLive && (
          <span className={`absolute bottom-2 left-2 text-[10px] font-bold rounded-full px-2 py-0.5 ${LIVE_COLOR[m.live_status] || "bg-stone-700 text-stone-300"}`}>
            {LIVE_LABEL[m.live_status] || "Live"}
          </span>
        )}
        {!isLive && <PlayCircle className="absolute w-11 h-11 text-white/90 drop-shadow" />}
      </div>
      <div className="p-4">
        <h4 className="font-heading font-bold leading-tight">{m.title}</h4>
        <p className="text-stone-400 text-sm mt-1 line-clamp-2">{m.description}</p>
        {m.category && <span className="inline-block mt-2 text-[11px] text-orange-500 border border-orange-600/40 rounded-full px-2 py-0.5">{m.category}</span>}
      </div>
    </button>
  );
}

export default function MediaCenter() {
  const { user } = useAuth();
  const nav = useNavigate();
  const canManage = user?.role === "mestre" || (user?.permissions || []).includes("MANAGE_EXTERNAL_MEDIA");

  const [tab, setTab] = useState("all");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState(null);

  const load = async () => {
    setItems(null);
    try {
      if (tab === "favorites") { const { data } = await api.get("/external-media/favorites"); setItems(data); return; }
      if (tab === "history") { const { data } = await api.get("/external-media/history"); setItems(data); return; }
      const params = {};
      if (tab === "video" || tab === "live") params.kind = tab;
      if (query.trim()) params.q = query.trim();
      const { data } = await api.get("/external-media", { params });
      setItems(data);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); setItems([]); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [tab]);

  const open = (m) => nav(`/app/midia/${m.id}`);

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Clapperboard className="w-6 h-6 text-orange-500" />
            <h1 className="font-heading font-black text-3xl tracking-tight">Central de Mídia</h1>
          </div>
          {canManage && (
            <button data-testid="media-manage-btn" onClick={() => nav("/app/midia/gerenciar")}
              className="flex items-center gap-1 text-sm rounded-full bg-orange-600 hover:bg-orange-500 text-white px-3 py-2 font-semibold transition-colors">
              <Plus className="w-4 h-4" /> Cadastrar
            </button>
          )}
        </div>
        <p className="text-stone-500 text-sm mb-5">Vídeos e lives hospedados no YouTube e Vimeo.</p>

        <div className="relative mb-4">
          <Search className="w-4 h-4 text-stone-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input data-testid="media-search" value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Buscar por título, tema..."
            className="w-full bg-stone-900 border border-stone-800 rounded-xl pl-9 pr-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
        </div>

        <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
          {TABS.map((t) => (
            <button key={t.key} data-testid={`media-tab-${t.key}`} onClick={() => setTab(t.key)}
              className={`shrink-0 min-h-[40px] px-4 rounded-xl text-sm font-medium transition-colors flex items-center gap-1.5 ${tab === t.key ? "bg-orange-600 text-white" : "bg-stone-900 border border-stone-800 text-stone-400"}`}>
              {t.key === "favorites" && <Star className="w-3.5 h-3.5" />}
              {t.key === "history" && <History className="w-3.5 h-3.5" />}
              {t.label}
            </button>
          ))}
        </div>

        {items === null && <div className="flex justify-center py-16"><Loader2 className="animate-spin text-orange-600" /></div>}
        {items && items.length === 0 && <p className="text-stone-500 text-sm text-center py-10" data-testid="media-empty">Nada por aqui ainda.</p>}

        <div className="grid grid-cols-1 gap-4">
          {items && items.map((m) => <MediaCard key={m.id} m={m} onOpen={open} />)}
        </div>
      </div>
    </Shell>
  );
}
