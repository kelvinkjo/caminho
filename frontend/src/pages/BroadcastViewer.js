import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { ChatPanel } from "./ChatPanel";
import { connectViewer } from "../lib/livekit";
import { OverlayLayer } from "../lib/overlays";
import { ArrowLeft, Loader2, Users, Maximize, Radio, Lock } from "lucide-react";

export default function BroadcastViewer() {
  const { id } = useParams();
  const nav = useNavigate();
  const [b, setB] = useState(null);
  const [error, setError] = useState(null);
  const [lkConfigured, setLkConfigured] = useState(true);
  const [connState, setConnState] = useState("connecting");
  const [viewers, setViewers] = useState(0);
  const [activeScene, setActiveScene] = useState(null);
  const videoRef = useRef(null);
  const containerRef = useRef(null);
  const roomRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    api.get("/livekit/status").then((r) => setLkConfigured(r.data.configured)).catch(() => {});
    api.get(`/broadcasts/${id}`).then(async (r) => {
      if (!mounted) return;
      setB(r.data);
      if (r.data.status === "live") {
        try {
          const { data } = await api.post(`/broadcasts/${id}/token`);
          const room = await connectViewer({
            serverUrl: data.server_url, token: data.token,
            onStatus: setConnState,
            onVideo: (track) => { if (videoRef.current) track.attach(videoRef.current); },
          });
          roomRef.current = room;
        } catch (e) {
          if (e.response?.status === 503) setConnState("no-server");
          else setError(apiError(e.response?.data?.detail));
        }
      }
    }).catch((e) => setError(apiError(e.response?.data?.detail)));
    return () => { mounted = false; roomRef.current?.disconnect?.(); };
    // eslint-disable-next-line
  }, [id]);

  // heartbeat de espectador + overlays da cena ativa
  useEffect(() => {
    if (b?.status !== "live") return;
    const beat = () => api.post(`/broadcasts/${id}/heartbeat`).then((r) => { setViewers(r.data.viewers); setActiveScene(r.data.active_scene); }).catch(() => {});
    beat(); const t = setInterval(beat, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [b?.status, id]);

  const fullscreen = () => { const el = containerRef.current; if (el?.requestFullscreen) el.requestFullscreen(); };

  if (error) return <Shell><div className="fade-up"><button onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-6 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button><div className="rounded-2xl border border-stone-800 bg-stone-900 p-8 text-center" data-testid="viewer-error"><Lock className="w-8 h-8 text-stone-500 mx-auto mb-3" /><p className="text-stone-300">{error}</p></div></div></Shell>;
  if (!b) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up" data-testid="viewer-page">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-3 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1">
          {b.status === "live" && <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-red-600 text-white animate-pulse">● AO VIVO</span>}
          <h1 className="font-heading font-black text-2xl tracking-tight flex-1">{b.title}</h1>
        </div>
        <p className="text-stone-500 text-sm mb-4">{b.presenter_name}</p>

        <div ref={containerRef} className="relative rounded-2xl overflow-hidden border border-stone-800 bg-black mb-3" style={{ aspectRatio: "16/9" }} data-testid="viewer-player">
          <video ref={videoRef} autoPlay playsInline className="w-full h-full object-contain" />
          {b.status !== "live" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center p-6"><Radio className="w-10 h-10 text-stone-600" /><p className="text-stone-400 text-sm">{b.status === "ended" ? "Esta transmissão foi encerrada." : "A transmissão ainda não começou."}</p></div>
          )}
          {b.status === "live" && (connState === "no-server" || !lkConfigured) && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center p-6" data-testid="viewer-no-server"><Radio className="w-10 h-10 text-stone-600" /><p className="text-stone-400 text-sm">Transmissão ao vivo — aguardando configuração do servidor de vídeo.</p></div>
          )}
          {b.status === "live" && connState === "connecting" && lkConfigured && <div className="absolute inset-0 flex items-center justify-center"><Loader2 className="animate-spin text-orange-600" /></div>}
          {b.status === "live" && <button data-testid="fullscreen-btn" onClick={fullscreen} className="absolute bottom-3 right-3 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center text-white"><Maximize className="w-4 h-4" /></button>}
          {b.status === "live" && <OverlayLayer scene={activeScene} />}
        </div>

        {b.status === "live" && (
          <>
            <p className="text-stone-400 text-sm mb-4 flex items-center gap-1" data-testid="viewer-count"><Users className="w-4 h-4 text-orange-500" /> {viewers} assistindo</p>
            <ChatPanel bid={id} canModerate={false} />
          </>
        )}
        {b.description && <p className="text-stone-400 text-sm mt-4">{b.description}</p>}
      </div>
    </Shell>
  );
}
