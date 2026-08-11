import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { Radio, Loader2, Plus, Video, Users, Clock } from "lucide-react";
import { toast } from "sonner";

const STAGES = ["Pré-Voc.", "Vocac.", "Disc. 1", "Disc. 2", "Compr.", "Consag."];

export default function BroadcastCenter() {
  const { user } = useAuth();
  const nav = useNavigate();
  const perms = user?.permissions || [];
  const canCreate = user?.role === "mestre" || perms.includes("CREATE_LIVE");
  const canOperate = (b) => user?.role === "mestre" || b.owner_id === user?.id || b.presenter_id === user?.id || perms.includes("START_LIVE");

  const [items, setItems] = useState(null);
  const [form, setForm] = useState({ title: "", description: "", stages: [], mode: "simple" });
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/broadcasts").then((r) => setItems(r.data)).catch((e) => { toast.error(apiError(e.response?.data?.detail)); setItems([]); });
  useEffect(() => { load(); }, []);

  const toggleStage = (s) => setForm({ ...form, stages: form.stages.includes(s) ? form.stages.filter((x) => x !== s) : [...form.stages, s] });

  const submit = async () => {
    if (!form.title.trim()) return toast.error("Informe o título.");
    setBusy(true);
    try {
      const { data } = await api.post("/broadcasts", form);
      toast.success("Transmissão criada.");
      setForm({ title: "", description: "", stages: [], mode: "simple" }); setShowForm(false);
      nav(`/app/estudio/${data.id}`);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const open = (b) => {
    if (b.status === "live") {
      if (canOperate(b)) nav(`/app/estudio/${b.id}`);
      else nav(`/app/ao-vivo/${b.id}`);
    } else if (canOperate(b)) nav(`/app/estudio/${b.id}`);
    else toast.info("A transmissão ainda não está ao vivo.");
  };

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2"><Radio className="w-6 h-6 text-red-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Central de Transmissão</h1></div>
          {canCreate && (
            <button data-testid="broadcast-new-btn" onClick={() => setShowForm(!showForm)} className="flex items-center gap-1 text-sm rounded-full bg-orange-600 hover:bg-orange-500 text-white px-3 py-2 font-semibold transition-colors"><Plus className="w-4 h-4" /> Nova</button>
          )}
        </div>
        <p className="text-stone-500 text-sm mb-5">Transmita ao vivo direto do app (câmera e microfone).</p>

        {showForm && canCreate && (
          <section className="rounded-2xl border border-stone-800 bg-stone-900 p-5 mb-6">
            <input data-testid="broadcast-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Título da transmissão" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <textarea data-testid="broadcast-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} placeholder="Descrição" className="w-full mb-2 bg-stone-800 border border-stone-700 rounded-lg px-3 py-3 text-stone-100 placeholder-stone-500 outline-none focus:border-orange-600/60" />
            <p className="text-xs text-stone-500 mb-1">Etapas autorizadas (vazio = todos):</p>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {STAGES.map((s, i) => <button key={i} type="button" data-testid={`broadcast-stage-${i + 1}`} onClick={() => toggleStage(i + 1)} className={`text-xs rounded-full px-2.5 py-1 ${form.stages.includes(i + 1) ? "bg-orange-600 text-white" : "bg-stone-800 text-stone-400 border border-stone-700"}`}>{s}</button>)}
            </div>
            <button data-testid="broadcast-create-submit" disabled={busy} onClick={submit} className="w-full min-h-[46px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-60">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Criar e abrir estúdio</button>
          </section>
        )}

        {items === null && <div className="flex justify-center py-16"><Loader2 className="animate-spin text-orange-600" /></div>}
        {items && items.length === 0 && <p className="text-stone-500 text-sm text-center py-10" data-testid="broadcast-empty">Nenhuma transmissão no momento.</p>}

        <div className="space-y-3">
          {items && items.map((b) => (
            <button key={b.id} data-testid={`broadcast-${b.id}`} onClick={() => open(b)} className="w-full text-left rounded-2xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] font-bold rounded-full px-2 py-0.5 ${b.status === "live" ? "bg-red-600 text-white animate-pulse" : b.status === "ended" ? "bg-stone-800 text-stone-400" : "bg-stone-700 text-stone-300"}`}>{b.status === "live" ? "● AO VIVO" : b.status === "ended" ? "ENCERRADA" : "AGUARDANDO"}</span>
                <p className="font-heading font-bold flex-1">{b.title}</p>
              </div>
              {b.description && <p className="text-stone-400 text-sm">{b.description}</p>}
              <p className="text-stone-500 text-xs mt-2 flex items-center gap-3">
                <span className="flex items-center gap-1"><Video className="w-3 h-3" /> {b.presenter_name}</span>
                {b.status === "ended" && b.duration_min != null && <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {b.duration_min} min</span>}
                {b.viewers_peak > 0 && <span className="flex items-center gap-1"><Users className="w-3 h-3" /> pico {b.viewers_peak}</span>}
              </p>
            </button>
          ))}
        </div>
      </div>
    </Shell>
  );
}
