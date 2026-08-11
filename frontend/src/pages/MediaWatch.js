import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Star, ExternalLink, Radio, Lock } from "lucide-react";
import { toast } from "sonner";

const LIVE_LABEL = {
  draft: "Rascunho", scheduled: "Agendada", waiting: "Aguardando transmissão",
  live: "Ao vivo", ended: "Encerrada", unavailable: "Indisponível",
};

export default function MediaWatch() {
  const { id } = useParams();
  const nav = useNavigate();
  const [m, setM] = useState(null);
  const [error, setError] = useState(null);
  const [fav, setFav] = useState(false);

  useEffect(() => {
    api.get(`/external-media/${id}`)
      .then((r) => { setM(r.data); setFav(r.data.favorited); })
      .catch((e) => setError(apiError(e.response?.data?.detail)));
  }, [id]);

  const toggleFav = async () => {
    try { const { data } = await api.post(`/external-media/${id}/favorite`); setFav(data.favorited); toast.success(data.favorited ? "Adicionado aos favoritos." : "Removido dos favoritos."); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  if (error) return (
    <Shell><div className="fade-up">
      <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-6 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
      <div className="rounded-2xl border border-stone-800 bg-stone-900 p-8 text-center" data-testid="media-access-error">
        <Lock className="w-8 h-8 text-stone-500 mx-auto mb-3" />
        <p className="text-stone-300">{error}</p>
      </div>
    </div></Shell>
  );

  if (!m) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  const isLive = m.kind === "live";
  const liveBlocked = isLive && ["unavailable", "draft"].includes(m.live_status);

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>

        <div className="rounded-2xl overflow-hidden border border-stone-800 bg-black mb-4" data-testid="media-player">
          {m.can_embed && !liveBlocked ? (
            <div className="relative w-full" style={{ paddingBottom: "56.25%" }}>
              <iframe
                data-testid="media-iframe"
                src={m.embed_url}
                title={m.title}
                className="absolute inset-0 w-full h-full"
                frameBorder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          ) : (
            <div className="p-8 text-center" data-testid="media-fallback">
              <Radio className="w-8 h-8 text-stone-500 mx-auto mb-3" />
              <p className="text-stone-400 text-sm mb-4">{liveBlocked ? `Transmissão ${LIVE_LABEL[m.live_status]?.toLowerCase()}.` : "A incorporação não está disponível para este conteúdo."}</p>
              <a data-testid="media-open-external" href={m.watch_url} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white px-4 py-3 text-sm font-semibold">
                <ExternalLink className="w-4 h-4" /> Abrir na plataforma
              </a>
            </div>
          )}
        </div>

        <div className="flex items-start gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-stone-800 text-stone-300 uppercase">{m.provider_name}</span>
              {isLive && <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-red-600/20 text-red-400 border border-red-600/40">{LIVE_LABEL[m.live_status] || "Live"}</span>}
            </div>
            <h1 className="font-heading font-black text-2xl tracking-tight">{m.title}</h1>
          </div>
          <button data-testid="media-favorite-btn" onClick={toggleFav}
            className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center border transition-colors ${fav ? "bg-orange-600 border-orange-600 text-white" : "border-stone-700 text-stone-400"}`}>
            <Star className="w-5 h-5" fill={fav ? "currentColor" : "none"} />
          </button>
        </div>

        <p className="text-stone-400 text-sm mt-3">{m.description}</p>
        {m.category && <span className="inline-block mt-3 text-[11px] text-orange-500 border border-orange-600/40 rounded-full px-2 py-0.5">{m.category}</span>}

        <a data-testid="media-open-platform-link" href={m.watch_url} target="_blank" rel="noopener noreferrer"
          className="mt-5 flex items-center justify-center gap-2 rounded-xl border border-stone-700 text-stone-300 px-4 py-3 text-sm font-medium">
          <ExternalLink className="w-4 h-4" /> Abrir na plataforma original
        </a>
      </div>
    </Shell>
  );
}
