import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Megaphone, Radio, Play, Square, Plus } from "lucide-react";
import { toast } from "sonner";

const STAGES = ["Pré-Voc.", "Vocac.", "Disc. 1", "Disc. 2", "Compr.", "Consag."];

export default function FormerPanel() {
  const { user } = useAuth();
  const nav = useNavigate();
  const perms = user?.permissions || [];
  const can = (p) => user?.role === "mestre" || perms.includes(p);

  const [lives, setLives] = useState([]);
  const [ann, setAnn] = useState({ title: "", message: "", stages: [] });
  const [live, setLive] = useState({ title: "", presenter: "", stages: [] });
  const [busy, setBusy] = useState(false);

  const loadLives = () => api.get("/lives").then((r) => setLives([...r.data.live_now, ...r.data.upcoming]));
  useEffect(() => { loadLives(); }, []);

  const toggleStage = (obj, set, s) => set({ ...obj, stages: obj.stages.includes(s) ? obj.stages.filter((x) => x !== s) : [...obj.stages, s] });

  const submitAnn = async () => {
    if (!ann.title.trim() || !ann.message.trim()) return toast.error("Preencha título e mensagem.");
    setBusy(true);
    try { await api.post("/announcements", { ...ann, publish: true }); toast.success("Aviso publicado."); setAnn({ title: "", message: "", stages: [] }); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const submitLive = async () => {
    if (!live.title.trim()) return toast.error("Informe o título da live.");
    setBusy(true);
    try { await api.post("/lives", { ...live, presenter: live.presenter || user.name }); toast.success("Live criada."); setLive({ title: "", presenter: "", stages: [] }); await loadLives(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const startLive = async (id) => { try { await api.post(`/lives/${id}/start`); toast.success("Transmissão iniciada!"); await loadLives(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const endLive = async (id) => { if (!window.confirm("Deseja realmente encerrar esta transmissão?")) return; try { await api.post(`/lives/${id}/end`); toast.success("Transmissão encerrada."); await loadLives(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };

  const StagePicker = ({ obj, set }) => (
    <div className="flex flex-wrap gap-1.5 mb-3">
      {STAGES.map((s, i) => (
        <button key={i} type="button" onClick={() => toggleStage(obj, set, i + 1)} className={`text-xs rounded-full px-2.5 py-1 ${obj.stages.includes(i + 1) ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-400 border border-stone-700"}`}>{s}</button>
      ))}
    </div>
  );

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <h1 className="font-heading font-black text-3xl tracking-tight mb-1">Central do Formador</h1>
        <p className="text-stone-500 text-sm mb-6">Produza conteúdo e ministre lives conforme suas permissões.</p>

        {can("CREATE_ANNOUNCEMENT") && (
          <section className="rounded-2xl border border-stone-800 bg-stone-900 p-5 mb-5">
            <h3 className="font-heading font-bold flex items-center gap-2 mb-3"><Megaphone className="w-5 h-5 text-orange-500" /> Novo aviso</h3>
            <input data-testid="ann-title" value={ann.title} onChange={(e) => setAnn({ ...ann, title: e.target.value })} placeholder="Título" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <textarea data-testid="ann-message" value={ann.message} onChange={(e) => setAnn({ ...ann, message: e.target.value })} rows={2} placeholder="Mensagem" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <p className="text-xs text-stone-500 mb-1">Etapas (vazio = todos):</p>
            <StagePicker obj={ann} set={setAnn} />
            <button data-testid="ann-submit" disabled={busy} onClick={submitAnn} className="w-full min-h-[46px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-2">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Publicar aviso</button>
          </section>
        )}

        {can("CREATE_LIVE") && (
          <section className="rounded-2xl border border-stone-800 bg-stone-900 p-5 mb-5">
            <h3 className="font-heading font-bold flex items-center gap-2 mb-3"><Radio className="w-5 h-5 text-red-500" /> Nova live</h3>
            <input data-testid="live-title" value={live.title} onChange={(e) => setLive({ ...live, title: e.target.value })} placeholder="Título da transmissão" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <input data-testid="live-presenter" value={live.presenter} onChange={(e) => setLive({ ...live, presenter: e.target.value })} placeholder="Apresentador" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <p className="text-xs text-stone-500 mb-1">Etapas autorizadas (vazio = todos):</p>
            <StagePicker obj={live} set={setLive} />
            <button data-testid="live-submit" disabled={busy} onClick={submitLive} className="w-full min-h-[46px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-2">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Criar live</button>
          </section>
        )}

        {(can("START_LIVE") || can("END_LIVE") || can("CREATE_LIVE")) && (
          <section>
            <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Sala de transmissão</h3>
            <div className="space-y-2">
              {lives.map((l) => (
                <div key={l.id} data-testid={`former-live-${l.id}`} className="rounded-xl border border-stone-800 bg-stone-900 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-[10px] font-bold rounded-full px-2 py-0.5 ${l.status === "live" ? "bg-red-600 text-white animate-pulse" : "bg-stone-700 text-stone-300"}`}>{l.status === "live" ? "● AO VIVO" : "OFFLINE"}</span>
                    <p className="font-medium text-sm flex-1">{l.title}</p>
                  </div>
                  <div className="flex gap-2">
                    {l.status !== "live" && can("START_LIVE") && <button data-testid={`start-${l.id}`} onClick={() => startLive(l.id)} className="flex-1 min-h-[42px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-1"><Play className="w-4 h-4" /> Iniciar</button>}
                    {l.status === "live" && can("END_LIVE") && <button data-testid={`end-${l.id}`} onClick={() => endLive(l.id)} className="flex-1 min-h-[42px] rounded-lg border border-red-600/50 text-red-400 text-sm font-semibold flex items-center justify-center gap-1"><Square className="w-4 h-4" /> Encerrar</button>}
                  </div>
                </div>
              ))}
              {lives.length === 0 && <p className="text-stone-500 text-sm">Nenhuma live agendada.</p>}
            </div>
          </section>
        )}
      </div>
    </Shell>
  );
}
