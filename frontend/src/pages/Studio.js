import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { ChatPanel } from "./ChatPanel";
import { connectBroadcaster, listDevices } from "../lib/livekit";
import { ArrowLeft, Loader2, Video, VideoOff, Mic, MicOff, Radio, Square, ShieldAlert, CheckCircle2, XCircle, Users, Wifi } from "lucide-react";
import { toast } from "sonner";

export default function Studio() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();

  const [b, setB] = useState(null);
  const [error, setError] = useState(null);
  const [lkConfigured, setLkConfigured] = useState(true);
  const [mode, setMode] = useState("simple");

  const [cams, setCams] = useState([]); const [mics, setMics] = useState([]);
  const [camId, setCamId] = useState(""); const [micId, setMicId] = useState("");
  const [camGranted, setCamGranted] = useState(false); const [micGranted, setMicGranted] = useState(false);
  const [camOn, setCamOn] = useState(true); const [micOn, setMicOn] = useState(true);
  const [audioLevel, setAudioLevel] = useState(0);
  const [connState, setConnState] = useState("idle");
  const [stats, setStats] = useState({ viewers: 0, viewers_peak: 0 });
  const [elapsed, setElapsed] = useState(0);
  const [going, setGoing] = useState(false);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const roomRef = useRef(null);
  const rafRef = useRef(null);
  const audioCtxRef = useRef(null);

  const perms = user?.permissions || [];
  const canModerate = user?.role === "mestre" || perms.includes("MODERATE_LIVE");
  const canTakeover = user?.role === "mestre" || perms.includes("TAKE_OVER_LIVE");

  useEffect(() => {
    api.get("/livekit/status").then((r) => setLkConfigured(r.data.configured)).catch(() => {});
    api.get(`/broadcasts/${id}`).then((r) => { setB(r.data); setMode(r.data.mode || "simple"); })
      .catch((e) => setError(apiError(e.response?.data?.detail)));
    return () => stopLocal();
    // eslint-disable-next-line
  }, [id]);

  // polling de stats quando ao vivo
  useEffect(() => {
    if (b?.status !== "live") return;
    const t = setInterval(() => api.get(`/broadcasts/${id}/stats`).then((r) => setStats(r.data)).catch(() => {}), 3000);
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => { clearInterval(t); clearInterval(timer); };
    // eslint-disable-next-line
  }, [b?.status, id]);

  const stopLocal = () => {
    cancelAnimationFrame(rafRef.current);
    try { audioCtxRef.current?.close(); } catch {}
    streamRef.current?.getTracks().forEach((t) => t.stop());
    roomRef.current?.disconnect?.();
  };

  const requestDevices = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = s;
      setCamGranted(true); setMicGranted(true);
      if (videoRef.current) { videoRef.current.srcObject = s; await videoRef.current.play().catch(() => {}); }
      const { cameras, microphones } = await listDevices();
      setCams(cameras); setMics(microphones);
      setCamId(cameras[0]?.deviceId || ""); setMicId(microphones[0]?.deviceId || "");
      startMeter(s);
      toast.success("Câmera e microfone autorizados.");
    } catch (e) {
      setCamGranted(false); setMicGranted(false);
      toast.error("O navegador bloqueou o acesso. Autorize câmera e microfone nas permissões do navegador e tente novamente.");
    }
  };

  const startMeter = (stream) => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser(); analyser.fftSize = 256;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, v) => a + v, 0) / data.length;
        setAudioLevel(Math.min(100, Math.round((avg / 140) * 100)));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {}
  };

  const switchDevice = async () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: camId ? { deviceId: { exact: camId } } : true,
        audio: micId ? { deviceId: { exact: micId } } : true,
      });
      streamRef.current = s;
      if (videoRef.current) videoRef.current.srcObject = s;
      startMeter(s);
    } catch { toast.error("Não foi possível trocar o dispositivo."); }
  };
  useEffect(() => { if (camGranted) switchDevice(); /* eslint-disable-next-line */ }, [camId, micId]);

  const toggleCam = () => { const track = streamRef.current?.getVideoTracks()[0]; if (track) { track.enabled = !camOn; setCamOn(!camOn); } };
  const toggleMic = () => { const track = streamRef.current?.getAudioTracks()[0]; if (track) { track.enabled = !micOn; setMicOn(!micOn); } };

  const checklist = [
    { key: "cam", label: "Câmera", ok: camGranted },
    { key: "mic", label: "Microfone", ok: micGranted },
    { key: "server", label: "Servidor de transmissão", ok: lkConfigured },
    { key: "session", label: "Sessão autenticada", ok: !!user },
  ];
  const allReady = camGranted && micGranted;

  const goLive = async () => {
    setGoing(true);
    try {
      await api.post(`/broadcasts/${id}/start`);
      if (lkConfigured) {
        const { data } = await api.post(`/broadcasts/${id}/token`);
        const { room } = await connectBroadcaster({ serverUrl: data.server_url, token: data.token, videoDeviceId: camId, audioDeviceId: micId, onStatus: setConnState });
        roomRef.current = room;
      } else {
        setConnState("no-server");
      }
      setB((prev) => ({ ...prev, status: "live" }));
      setElapsed(0);
      toast.success(lkConfigured ? "Você está AO VIVO!" : "Transmissão iniciada (streaming pendente de configuração do LiveKit).");
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setGoing(false); }
  };

  const endLive = async () => {
    if (!window.confirm("Tem certeza que deseja encerrar a transmissão?")) return;
    try { await api.post(`/broadcasts/${id}/end`); stopLocal(); toast.success("Transmissão encerrada."); nav("/app/transmissoes"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const takeover = async () => {
    if (!window.confirm("Assumir esta transmissão como Login Mestre?")) return;
    try { await api.post(`/broadcasts/${id}/takeover`); toast.success("Transmissão assumida."); const { data } = await api.get(`/broadcasts/${id}`); setB(data); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const fmt = (s) => `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  if (error) return <Shell><div className="fade-up"><button onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-6 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button><div className="rounded-2xl border border-stone-800 bg-stone-900 p-8 text-center" data-testid="studio-error"><ShieldAlert className="w-8 h-8 text-stone-500 mx-auto mb-3" /><p className="text-stone-300">{error}</p></div></div></Shell>;
  if (!b) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  const isLive = b.status === "live";

  return (
    <Shell>
      <div className="fade-up" data-testid="studio-page">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-3 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center justify-between mb-1">
          <h1 className="font-heading font-black text-2xl tracking-tight flex items-center gap-2">{isLive && <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-red-600 text-white animate-pulse">● AO VIVO</span>} Estúdio</h1>
          <button data-testid="mode-toggle" onClick={() => setMode(mode === "simple" ? "pro" : "simple")} className="text-xs rounded-full px-3 py-1.5 bg-stone-800 border border-stone-700 text-stone-300">{mode === "simple" ? "⭐ Simples" : "🎛️ Profissional"}</button>
        </div>
        <p className="text-stone-500 text-sm mb-4">{b.title}</p>

        {!lkConfigured && <div data-testid="lk-not-configured" className="mb-4 rounded-xl border border-amber-600/40 bg-amber-600/10 p-3 text-amber-300 text-xs">⚠️ Servidor de transmissão (LiveKit) ainda não configurado. Você pode testar câmera/microfone e o painel; o vídeo será transmitido assim que as credenciais forem informadas.</div>}

        <div className="relative rounded-2xl overflow-hidden border border-stone-800 bg-black mb-3" style={{ aspectRatio: "16/9" }} data-testid="studio-preview">
          <video ref={videoRef} muted playsInline className="w-full h-full object-cover" />
          {!camGranted && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
              <Video className="w-10 h-10 text-stone-500" />
              <p className="text-stone-300 text-sm">O aplicativo precisa acessar sua câmera e microfone para transmitir.</p>
              <button data-testid="request-devices-btn" onClick={requestDevices} className="rounded-xl bg-orange-600 hover:bg-orange-500 text-white px-5 py-3 text-sm font-semibold">Permitir câmera e microfone</button>
            </div>
          )}
          {isLive && <span className="absolute top-3 left-3 text-xs font-bold text-white bg-red-600 rounded-full px-2 py-0.5 flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-white animate-pulse" /> {fmt(elapsed)}</span>}
        </div>

        {camGranted && (
          <>
            {/* medidor de áudio */}
            <div className="mb-3">
              <p className="text-xs text-stone-500 mb-1 flex items-center gap-1"><Mic className="w-3 h-3" /> Nível do microfone</p>
              <div className="h-3 rounded-full bg-stone-800 overflow-hidden" data-testid="audio-meter">
                <div className={`h-full transition-all ${audioLevel > 85 ? "bg-red-500" : "bg-green-500"}`} style={{ width: `${audioLevel}%` }} />
              </div>
              {audioLevel > 85 && <p className="text-[11px] text-red-400 mt-1">⚠️ Áudio muito alto — reduza o ganho do microfone.</p>}
            </div>

            {/* seleção de dispositivos (modo pro) */}
            {mode === "pro" && (
              <div className="grid grid-cols-2 gap-2 mb-3">
                <select data-testid="camera-select" value={camId} onChange={(e) => setCamId(e.target.value)} className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">
                  {cams.map((c) => <option key={c.deviceId} value={c.deviceId}>{c.label || "Câmera"}</option>)}
                </select>
                <select data-testid="mic-select" value={micId} onChange={(e) => setMicId(e.target.value)} className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">
                  {mics.map((m) => <option key={m.deviceId} value={m.deviceId}>{m.label || "Microfone"}</option>)}
                </select>
              </div>
            )}

            {/* controles rápidos */}
            <div className="flex gap-2 mb-4">
              <button data-testid="toggle-cam" onClick={toggleCam} className={`flex-1 min-h-[44px] rounded-lg text-sm font-semibold flex items-center justify-center gap-1.5 ${camOn ? "bg-stone-800 text-stone-200 border border-stone-700" : "bg-red-600/20 text-red-400 border border-red-600/40"}`}>{camOn ? <Video className="w-4 h-4" /> : <VideoOff className="w-4 h-4" />} {camOn ? "Câmera" : "Câmera off"}</button>
              <button data-testid="toggle-mic" onClick={toggleMic} className={`flex-1 min-h-[44px] rounded-lg text-sm font-semibold flex items-center justify-center gap-1.5 ${micOn ? "bg-stone-800 text-stone-200 border border-stone-700" : "bg-red-600/20 text-red-400 border border-red-600/40"}`}>{micOn ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />} {micOn ? "Microfone" : "Mudo"}</button>
            </div>
          </>
        )}

        {/* checklist / status ao vivo */}
        {!isLive ? (
          <>
            <div className="rounded-2xl border border-stone-800 bg-stone-900 p-4 mb-4" data-testid="checklist">
              <p className="font-heading font-bold text-sm mb-2">Checklist de transmissão</p>
              {checklist.map((c) => (
                <div key={c.key} className="flex items-center gap-2 text-sm py-1">{c.ok ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <XCircle className="w-4 h-4 text-stone-600" />}<span className={c.ok ? "text-stone-200" : "text-stone-500"}>{c.label}</span></div>
              ))}
            </div>
            <button data-testid="go-live-btn" disabled={!allReady || going} onClick={goLive} className="w-full min-h-[52px] rounded-xl bg-red-600 hover:bg-red-500 text-white font-bold flex items-center justify-center gap-2 disabled:opacity-50">{going ? <Loader2 className="w-5 h-5 animate-spin" /> : <Radio className="w-5 h-5" />} INICIAR TRANSMISSÃO</button>
            {!allReady && <p className="text-stone-500 text-xs text-center mt-2">Autorize câmera e microfone para iniciar.</p>}
          </>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-2 mb-4" data-testid="live-stats">
              <div className="rounded-xl bg-stone-900 border border-stone-800 p-3 text-center"><Users className="w-4 h-4 text-orange-500 mx-auto mb-1" /><p className="font-heading font-bold">{stats.viewers}</p><p className="text-[10px] text-stone-500">assistindo</p></div>
              <div className="rounded-xl bg-stone-900 border border-stone-800 p-3 text-center"><Wifi className="w-4 h-4 text-green-500 mx-auto mb-1" /><p className="font-heading font-bold text-xs">{connState === "connected" ? "Excelente" : connState === "reconnecting" ? "Reconectando" : lkConfigured ? "—" : "Sem servidor"}</p><p className="text-[10px] text-stone-500">conexão</p></div>
              <div className="rounded-xl bg-stone-900 border border-stone-800 p-3 text-center"><Radio className="w-4 h-4 text-red-500 mx-auto mb-1" /><p className="font-heading font-bold">{stats.viewers_peak}</p><p className="text-[10px] text-stone-500">pico</p></div>
            </div>
            {connState === "reconnecting" && <div className="mb-3 rounded-xl border border-amber-600/40 bg-amber-600/10 p-2 text-amber-300 text-xs text-center" data-testid="reconnecting">🟡 Reconectando...</div>}
            {canTakeover && b.presenter_id !== user.id && <button data-testid="takeover-btn" onClick={takeover} className="w-full mb-2 min-h-[46px] rounded-xl border border-yellow-600/50 text-yellow-400 font-semibold flex items-center justify-center gap-2"><ShieldAlert className="w-4 h-4" /> 🚨 Assumir transmissão</button>}
            <button data-testid="end-live-btn" onClick={endLive} className="w-full mb-4 min-h-[48px] rounded-xl border border-red-600/50 text-red-400 font-bold flex items-center justify-center gap-2"><Square className="w-4 h-4" /> Encerrar transmissão</button>
            <ChatPanel bid={id} canModerate={canModerate} />
          </>
        )}
      </div>
    </Shell>
  );
}
