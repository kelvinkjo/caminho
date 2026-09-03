import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { ChatPanel } from "./ChatPanel";
import { OverlayLayer } from "../lib/overlays";
import { connectBroadcaster, listDevices } from "../lib/livekit";
import { ArrowLeft, Loader2, Video, VideoOff, Mic, MicOff, Radio, Square, ShieldAlert, CheckCircle2, XCircle, Users, Wifi, Monitor, MonitorOff, Layout, Type, Tag, Plus, Trash2, Clapperboard } from "lucide-react";
import { toast } from "sonner";

const LAYOUTS = [
  { key: "full", label: "Tela cheia" },
  { key: "pip", label: "PiP (câmera sobre conteúdo)" },
  { key: "side", label: "Lado a lado" },
  { key: "content", label: "Conteúdo + câmera" },
];

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

  // Fase 2 — produção visual
  const [screenOn, setScreenOn] = useState(false);
  const [layout, setLayout] = useState("full");
  const [lowerThird, setLowerThird] = useState({ name: "", role: "", visible: false });
  const [banner, setBanner] = useState({ text: "", visible: false });
  const [scenes, setScenes] = useState([]);
  const [newSceneName, setNewSceneName] = useState("");

  const videoRef = useRef(null);
  const screenRef = useRef(null);
  const streamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const roomRef = useRef(null);
  const rafRef = useRef(null);
  const audioCtxRef = useRef(null);

  const perms = user?.permissions || [];
  const canModerate = user?.role === "mestre" || perms.includes("MODERATE_LIVE");
  const canTakeover = user?.role === "mestre" || perms.includes("TAKE_OVER_LIVE");
  const canScenes = user?.role === "mestre" || perms.includes("MANAGE_SCENES");
  const scene = { layout, lower_third: lowerThird, banner };

  useEffect(() => {
    api.get("/livekit/status").then((r) => setLkConfigured(r.data.configured)).catch(() => {});
    api.get(`/broadcasts/${id}`).then((r) => {
      setB(r.data); setMode(r.data.mode || "simple");
      setScenes(r.data.scenes || []);
      const as = r.data.active_scene; if (as) { setLayout(as.layout || "full"); setLowerThird(as.lower_third || { name: "", role: "", visible: false }); setBanner(as.banner || { text: "", visible: false }); }
    }).catch((e) => setError(apiError(e.response?.data?.detail)));
    return () => stopLocal();
    // eslint-disable-next-line
  }, [id]);

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
    screenStreamRef.current?.getTracks().forEach((t) => t.stop());
    roomRef.current?.disconnect?.();
  };

  const requestDevices = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = s;
      setCamGranted(true); setMicGranted(true);
      if (videoRef.current && videoRef.current.parentNode) {
        videoRef.current.srcObject = s;
        await videoRef.current.play().catch(() => {});
      }
      const { cameras, microphones } = await listDevices();
      setCams(cameras); setMics(microphones);
      setCamId(cameras[0]?.deviceId || ""); setMicId(microphones[0]?.deviceId || "");
      startMeter(s);
      toast.success("Câmera e microfone autorizados.");
    } catch {
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
      if (videoRef.current && videoRef.current.parentNode) videoRef.current.srcObject = s;
      startMeter(s);
    } catch { toast.error("Não foi possível trocar o dispositivo."); }
  };
  // Switch devices only after the selected device IDs change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (camGranted) switchDevice(); }, [camId, micId]);

  const toggleCam = () => { const t = streamRef.current?.getVideoTracks()[0]; if (t) { t.enabled = !camOn; setCamOn(!camOn); } };
  const toggleMic = () => { const t = streamRef.current?.getAudioTracks()[0]; if (t) { t.enabled = !micOn; setMicOn(!micOn); } };

  const toggleScreen = async () => {
    if (screenOn) {
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
      screenStreamRef.current = null; setScreenOn(false);
      if (layout !== "full") applyOverlay({ layout: "full" });
      return;
    }
    try {
      const s = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      screenStreamRef.current = s; setScreenOn(true);
      if (screenRef.current && screenRef.current.parentNode) {
        screenRef.current.srcObject = s;
        screenRef.current.play().catch(() => {});
      }
      s.getVideoTracks()[0].addEventListener("ended", () => { setScreenOn(false); screenStreamRef.current = null; });
      if (layout === "full") applyOverlay({ layout: "content" });
    } catch { toast.error("Compartilhamento de tela cancelado."); }
  };

  // aplica overlay/layout localmente e sincroniza com espectadores
  const applyOverlay = async (patch) => {
    const next = { layout, lower_third: lowerThird, banner, ...patch };
    if (patch.layout !== undefined) setLayout(patch.layout);
    if (patch.lower_third !== undefined) setLowerThird(patch.lower_third);
    if (patch.banner !== undefined) setBanner(patch.banner);
    try { await api.post(`/broadcasts/${id}/active-scene`, { layout: next.layout, lower_third: next.lower_third, banner: next.banner }); }
    catch (e) { if (e.response?.status !== 403) toast.error(apiError(e.response?.data?.detail)); }
  };

  const addScene = async () => {
    const name = (newSceneName || "").trim() || `Cena ${scenes.length + 1}`;
    const next = [...scenes, { name, layout, lower_third: { ...lowerThird }, banner: { ...banner } }];
    setScenes(next); setNewSceneName("");
    try { await api.put(`/broadcasts/${id}/scenes`, { scenes: next }); toast.success("Cena salva."); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const applyScene = (s) => { setScreenOnIfNeeded(s.layout); applyOverlay({ layout: s.layout, lower_third: s.lower_third, banner: s.banner }); toast.success(`Cena "${s.name}" no ar.`); };
  const setScreenOnIfNeeded = () => {};
  const deleteScene = async (i) => {
    const next = scenes.filter((_, idx) => idx !== i);
    setScenes(next);
    try { await api.put(`/broadcasts/${id}/scenes`, { scenes: next }); } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

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
      await applyOverlay({});
      if (lkConfigured) {
        const { data } = await api.post(`/broadcasts/${id}/token`);
        const { room } = await connectBroadcaster({ serverUrl: data.server_url, token: data.token, videoDeviceId: camId, audioDeviceId: micId, onStatus: setConnState });
        roomRef.current = room;
      } else setConnState("no-server");
      setB((p) => ({ ...p, status: "live" })); setElapsed(0);
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
  const camClass = !screenOn || layout === "full"
    ? "w-full h-full object-cover"
    : layout === "content"
      ? "absolute bottom-2 right-2 w-1/3 h-1/3 object-cover rounded-lg border border-stone-700"
      : layout === "pip"
        ? "w-full h-full object-cover"
        : "w-1/2 h-full object-cover";
  const screenClass = screenOn
    ? layout === "content"
      ? "w-full h-full object-contain"
      : layout === "pip"
        ? "absolute bottom-2 right-2 w-1/3 h-1/3 object-contain rounded-lg border border-stone-700 bg-black"
        : layout === "side"
          ? "w-1/2 h-full object-contain bg-black"
          : "hidden"
    : "hidden";
  const compositionClass = screenOn && layout === "side" ? "absolute inset-0 flex" : "absolute inset-0";

  return (
    <Shell>
      <div className="fade-up" data-testid="studio-page">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-3 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center justify-between mb-1">
          <h1 className="font-heading font-black text-2xl tracking-tight flex items-center gap-2">{isLive && <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-red-600 text-white animate-pulse">● AO VIVO</span>} Estúdio</h1>
          <button data-testid="mode-toggle" onClick={() => setMode(mode === "simple" ? "pro" : "simple")} className="text-xs rounded-full px-3 py-1.5 bg-stone-800 border border-stone-700 text-stone-300">{mode === "simple" ? "⭐ Simples" : "🎛️ Profissional"}</button>
        </div>
        <p className="text-stone-500 text-sm mb-4">{b.title}</p>

        {!lkConfigured && <div data-testid="lk-not-configured" className="mb-4 rounded-xl border border-amber-600/40 bg-amber-600/10 p-3 text-amber-300 text-xs">⚠️ Servidor de transmissão (LiveKit) ainda não configurado. Você pode testar câmera/microfone, cenas e overlays; o vídeo será transmitido assim que as credenciais forem informadas.</div>}

        <div className="relative rounded-2xl overflow-hidden border border-stone-800 bg-black mb-3" style={{ aspectRatio: "16/9" }} data-testid="studio-preview">
          <div className={compositionClass}>
            <video ref={videoRef} muted playsInline className={camClass} />
            <video ref={screenRef} muted playsInline className={screenClass} />
          </div>

          <OverlayLayer scene={scene} />
          {!camGranted && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center bg-black">
              <Video className="w-10 h-10 text-stone-500" />
              <p className="text-stone-300 text-sm">O aplicativo precisa acessar sua câmera e microfone para transmitir.</p>
              <button data-testid="request-devices-btn" onClick={requestDevices} className="rounded-xl bg-orange-600 hover:bg-orange-500 text-white px-5 py-3 text-sm font-semibold">Permitir câmera e microfone</button>
            </div>
          )}
          {isLive && <span className="absolute top-3 left-3 text-xs font-bold text-white bg-red-600 rounded-full px-2 py-0.5 flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-white animate-pulse" /> {fmt(elapsed)}</span>}
        </div>

        {camGranted && (
          <>
            <div className="mb-3">
              <p className="text-xs text-stone-500 mb-1 flex items-center gap-1"><Mic className="w-3 h-3" /> Nível do microfone</p>
              <div className="h-3 rounded-full bg-stone-800 overflow-hidden" data-testid="audio-meter"><div className={`h-full transition-all ${audioLevel > 85 ? "bg-red-500" : "bg-green-500"}`} style={{ width: `${audioLevel}%` }} /></div>
              {audioLevel > 85 && <p className="text-[11px] text-red-400 mt-1">⚠️ Áudio muito alto — reduza o ganho do microfone.</p>}
            </div>

            {mode === "pro" && (
              <div className="grid grid-cols-2 gap-2 mb-3">
                <select data-testid="camera-select" value={camId} onChange={(e) => setCamId(e.target.value)} className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">{cams.map((c) => <option key={c.deviceId} value={c.deviceId}>{c.label || "Câmera"}</option>)}</select>
                <select data-testid="mic-select" value={micId} onChange={(e) => setMicId(e.target.value)} className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">{mics.map((m) => <option key={m.deviceId} value={m.deviceId}>{m.label || "Microfone"}</option>)}</select>
              </div>
            )}

            <div className="flex gap-2 mb-3">
              <button data-testid="toggle-cam" onClick={toggleCam} className={`flex-1 min-h-[44px] rounded-lg text-sm font-semibold flex items-center justify-center gap-1.5 ${camOn ? "bg-stone-800 text-stone-200 border border-stone-700" : "bg-red-600/20 text-red-400 border border-red-600/40"}`}>{camOn ? <Video className="w-4 h-4" /> : <VideoOff className="w-4 h-4" />} {camOn ? "Câmera" : "Câmera off"}</button>
              <button data-testid="toggle-mic" onClick={toggleMic} className={`flex-1 min-h-[44px] rounded-lg text-sm font-semibold flex items-center justify-center gap-1.5 ${micOn ? "bg-stone-800 text-stone-200 border border-stone-700" : "bg-red-600/20 text-red-400 border border-red-600/40"}`}>{micOn ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />} {micOn ? "Microfone" : "Mudo"}</button>
              <button data-testid="screen-share-btn" onClick={toggleScreen} className={`flex-1 min-h-[44px] rounded-lg text-sm font-semibold flex items-center justify-center gap-1.5 ${screenOn ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-200 border border-stone-700"}`}>{screenOn ? <MonitorOff className="w-4 h-4" /> : <Monitor className="w-4 h-4" />} Tela</button>
            </div>

            {/* Produção visual (Fase 2) */}
            {(mode === "pro" || canScenes) && (
              <section className="rounded-2xl border border-stone-800 bg-stone-900 p-4 mb-4" data-testid="production-panel">
                <p className="font-heading font-bold text-sm mb-3 flex items-center gap-2"><Clapperboard className="w-4 h-4 text-orange-500" /> Produção</p>

                <p className="text-[11px] text-stone-500 mb-1 flex items-center gap-1"><Layout className="w-3 h-3" /> Layout</p>
                <div className="grid grid-cols-2 gap-1.5 mb-3">
                  {LAYOUTS.map((l) => <button key={l.key} data-testid={`layout-${l.key}`} onClick={() => applyOverlay({ layout: l.key })} className={`text-xs rounded-lg px-2 py-2 ${layout === l.key ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-400 border border-stone-700"}`}>{l.label}</button>)}
                </div>

                <p className="text-[11px] text-stone-500 mb-1 flex items-center gap-1"><Type className="w-3 h-3" /> Identificação (lower-third)</p>
                <div className="flex gap-1.5 mb-1">
                  <input data-testid="lower-third-name" value={lowerThird.name} onChange={(e) => setLowerThird({ ...lowerThird, name: e.target.value })} placeholder="Nome" className="flex-1 bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none" />
                  <input data-testid="lower-third-role" value={lowerThird.role} onChange={(e) => setLowerThird({ ...lowerThird, role: e.target.value })} placeholder="Função" className="flex-1 bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none" />
                </div>
                <button data-testid="lower-third-toggle" onClick={() => applyOverlay({ lower_third: { ...lowerThird, visible: !lowerThird.visible } })} className={`w-full mb-3 min-h-[38px] rounded-lg text-xs font-semibold ${lowerThird.visible ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-300 border border-stone-700"}`}>{lowerThird.visible ? "Ocultar identificação" : "Mostrar identificação"}</button>

                <p className="text-[11px] text-stone-500 mb-1 flex items-center gap-1"><Tag className="w-3 h-3" /> Banner</p>
                <input data-testid="banner-text" value={banner.text} onChange={(e) => setBanner({ ...banner, text: e.target.value })} placeholder="Texto do banner (ex: Ore conosco)" className="w-full mb-1 bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none" />
                <button data-testid="banner-toggle" onClick={() => applyOverlay({ banner: { ...banner, visible: !banner.visible } })} className={`w-full mb-3 min-h-[38px] rounded-lg text-xs font-semibold ${banner.visible ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-300 border border-stone-700"}`}>{banner.visible ? "Ocultar banner" : "Mostrar banner"}</button>

                <div className="flex items-center gap-2 mb-2">
                  <p className="text-[11px] text-stone-500 flex-1">Cenas</p>
                  <input data-testid="scene-name" value={newSceneName} onChange={(e) => setNewSceneName(e.target.value)} placeholder="Nome da cena" className="w-28 bg-stone-800 border border-stone-700 rounded-lg px-2 py-1.5 text-xs text-stone-100 outline-none" />
                  <button data-testid="scene-add" onClick={addScene} className="text-xs text-orange-400 flex items-center gap-1"><Plus className="w-3 h-3" /> Salvar</button>
                </div>
                <div className="space-y-1.5">
                  {scenes.map((s, i) => (
                    <div key={i} data-testid={`scene-${i}`} className="flex items-center gap-2 rounded-lg bg-stone-800 border border-stone-700 px-2 py-1.5">
                      <span className="flex-1 text-xs">{s.name}</span>
                      <button data-testid={`scene-apply-${i}`} onClick={() => applyScene(s)} className="text-[11px] rounded bg-orange-600 text-white px-2 py-1">No ar</button>
                      <button data-testid={`scene-delete-${i}`} onClick={() => deleteScene(i)} className="text-stone-500 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  ))}
                  {scenes.length === 0 && <p className="text-stone-600 text-xs">Nenhuma cena salva. Ajuste layout/overlays e salve como cena.</p>}
                </div>
              </section>
            )}
          </>
        )}

        {!isLive ? (
          <>
            <div className="rounded-2xl border border-stone-800 bg-stone-900 p-4 mb-4" data-testid="checklist">
              <p className="font-heading font-bold text-sm mb-2">Checklist de transmissão</p>
              {checklist.map((c) => <div key={c.key} className="flex items-center gap-2 text-sm py-1">{c.ok ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <XCircle className="w-4 h-4 text-stone-600" />}<span className={c.ok ? "text-stone-200" : "text-stone-500"}>{c.label}</span></div>)}
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
