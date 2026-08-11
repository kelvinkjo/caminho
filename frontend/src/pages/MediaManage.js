import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Plus, Trash2, Radio, Video, Link2, Settings } from "lucide-react";
import { toast } from "sonner";

const STAGES = ["Pré-Voc.", "Vocac.", "Disc. 1", "Disc. 2", "Compr.", "Consag."];
const LIVE_STATUSES = [
  { key: "draft", label: "Rascunho" }, { key: "scheduled", label: "Agendada" },
  { key: "waiting", label: "Aguardando transmissão" }, { key: "live", label: "Ao vivo" },
  { key: "ended", label: "Encerrada" }, { key: "unavailable", label: "Indisponível" },
];

export default function MediaManage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const isMaster = user?.role === "mestre";

  const [form, setForm] = useState({ url: "", title: "", description: "", kind: "video", category: "", stages: [], live_status: "scheduled" });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState([]);
  const [providers, setProviders] = useState([]);

  const loadItems = () => api.get("/external-media").then((r) => setItems(r.data));
  const loadProviders = () => api.get("/media/providers").then((r) => setProviders(r.data.providers));
  useEffect(() => { loadItems(); loadProviders(); }, []);

  const toggleStage = (s) => setForm({ ...form, stages: form.stages.includes(s) ? form.stages.filter((x) => x !== s) : [...form.stages, s] });

  const doParse = async () => {
    if (!form.url.trim()) return;
    setPreview(null);
    try { const { data } = await api.post("/media/parse", { url: form.url.trim() }); setPreview(data); toast.success(`Detectado: ${data.provider_name}`); }
    catch (e) { setPreview(null); toast.error(apiError(e.response?.data?.detail)); }
  };

  const submit = async () => {
    if (!form.url.trim() || !form.title.trim()) return toast.error("Informe a URL e o título.");
    setBusy(true);
    try {
      await api.post("/external-media", { ...form, publish: true });
      toast.success("Mídia cadastrada.");
      setForm({ url: "", title: "", description: "", kind: "video", category: "", stages: [], live_status: "scheduled" });
      setPreview(null);
      await loadItems();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!window.confirm("Remover esta mídia?")) return;
    try { await api.delete(`/external-media/${id}`); toast.success("Removida."); await loadItems(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const changeLiveStatus = async (id, status) => {
    try { await api.post(`/external-media/${id}/live-status`, { live_status: status }); toast.success("Status atualizado."); await loadItems(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const toggleProvider = async (key) => {
    const enabled = providers.filter((p) => p.enabled).map((p) => p.key);
    const next = enabled.includes(key) ? enabled.filter((k) => k !== key) : [...enabled, key];
    try { await api.put("/master/media/providers", { enabled: next }); await loadProviders(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <h1 className="font-heading font-black text-3xl tracking-tight mb-1">Gerenciar Mídia Externa</h1>
        <p className="text-stone-500 text-sm mb-6">Cadastre vídeos e lives do YouTube/Vimeo. Apenas o link é armazenado.</p>

        <section className="rounded-2xl border border-stone-800 bg-stone-900 p-5 mb-6">
          <h3 className="font-heading font-bold flex items-center gap-2 mb-3"><Plus className="w-5 h-5 text-orange-500" /> Nova mídia</h3>

          <div className="flex gap-2 mb-3">
            <button type="button" data-testid="kind-video" onClick={() => setForm({ ...form, kind: "video" })} className={`flex-1 min-h-[42px] rounded-lg text-sm font-medium flex items-center justify-center gap-1.5 ${form.kind === "video" ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-400 border border-stone-700"}`}><Video className="w-4 h-4" /> Vídeo</button>
            <button type="button" data-testid="kind-live" onClick={() => setForm({ ...form, kind: "live" })} className={`flex-1 min-h-[42px] rounded-lg text-sm font-medium flex items-center justify-center gap-1.5 ${form.kind === "live" ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-400 border border-stone-700"}`}><Radio className="w-4 h-4" /> Live externa</button>
          </div>

          <div className="flex gap-2 mb-2">
            <input data-testid="media-url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="Cole a URL (YouTube/Vimeo)" className="flex-1 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <button type="button" data-testid="media-parse-btn" onClick={doParse} className="shrink-0 px-3 rounded-lg border border-stone-700 text-stone-300 text-sm flex items-center gap-1"><Link2 className="w-4 h-4" /> Validar</button>
          </div>
          {preview && <p data-testid="media-preview" className="text-xs text-orange-400 mb-2">✓ {preview.provider_name} · ID {preview.external_id} · incorporável: {preview.can_embed ? "sim" : "não"}</p>}

          <input data-testid="media-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Título" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
          <textarea data-testid="media-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} placeholder="Descrição" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
          <input data-testid="media-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Categoria (ex: Formação)" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />

          {form.kind === "live" && (
            <select data-testid="media-live-status" value={form.live_status} onChange={(e) => setForm({ ...form, live_status: e.target.value })} className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 outline-none focus:border-orange-600/60">
              {LIVE_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          )}

          <p className="text-xs text-stone-500 mb-1">Etapas autorizadas (vazio = todos):</p>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {STAGES.map((s, i) => (
              <button key={i} type="button" data-testid={`media-stage-${i + 1}`} onClick={() => toggleStage(i + 1)} className={`text-xs rounded-full px-2.5 py-1 ${form.stages.includes(i + 1) ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-400 border border-stone-700"}`}>{s}</button>
            ))}
          </div>

          <button data-testid="media-submit" disabled={busy} onClick={submit} className="w-full min-h-[46px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-60">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Cadastrar mídia</button>
        </section>

        {isMaster && (
          <section className="rounded-2xl border border-stone-800 bg-stone-900 p-5 mb-6">
            <h3 className="font-heading font-bold flex items-center gap-2 mb-3"><Settings className="w-5 h-5 text-orange-500" /> Provedores</h3>
            <div className="space-y-2">
              {providers.map((p) => (
                <label key={p.key} data-testid={`provider-${p.key}`} className="flex items-center justify-between rounded-lg bg-stone-800 border border-stone-700 px-3 py-3">
                  <span className="text-sm">{p.name}</span>
                  <input type="checkbox" data-testid={`provider-toggle-${p.key}`} checked={p.enabled} onChange={() => toggleProvider(p.key)} className="w-5 h-5 accent-orange-600" />
                </label>
              ))}
            </div>
          </section>
        )}

        <section>
          <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Mídias cadastradas</h3>
          <div className="space-y-2">
            {items.map((m) => (
              <div key={m.id} data-testid={`manage-media-${m.id}`} className="rounded-xl border border-stone-800 bg-stone-900 p-4">
                <div className="flex items-center gap-2">
                  {m.kind === "live" ? <Radio className="w-4 h-4 text-red-500" /> : <Video className="w-4 h-4 text-stone-400" />}
                  <p className="font-medium text-sm flex-1">{m.title}</p>
                  <span className="text-[10px] text-stone-500 uppercase">{m.provider_name}</span>
                  <button data-testid={`delete-media-${m.id}`} onClick={() => remove(m.id)} className="text-red-400"><Trash2 className="w-4 h-4" /></button>
                </div>
                {m.kind === "live" && (
                  <select data-testid={`live-status-${m.id}`} value={m.live_status || "scheduled"} onChange={(e) => changeLiveStatus(m.id, e.target.value)} className="mt-2 w-full bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-xs text-stone-100 outline-none">
                    {LIVE_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                  </select>
                )}
              </div>
            ))}
            {items.length === 0 && <p className="text-stone-500 text-sm">Nenhuma mídia cadastrada.</p>}
          </div>
        </section>
      </div>
    </Shell>
  );
}
