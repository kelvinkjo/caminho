import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Play, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function LessonPlayer() {
  const { id } = useParams();
  const [l, setL] = useState(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  const load = () => api.get(`/lessons/${id}`).then((r) => setL(r.data));
  useEffect(() => { load(); }, [id]);

  const complete = async () => {
    setBusy(true);
    try { await api.post(`/lessons/${id}/progress`, { completed: true, percent: 100 }); toast.success("Aula concluída!"); await load(); }
    catch { toast.error("Erro ao salvar progresso."); }
    finally { setBusy(false); }
  };

  if (!l) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>

        <div className="aspect-video rounded-2xl border border-stone-800 bg-stone-900 flex items-center justify-center relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(234,88,12,0.12),_transparent_70%)]" />
          <div className="w-16 h-16 rounded-full bg-orange-600 flex items-center justify-center relative z-10"><Play className="w-7 h-7 text-white ml-1" /></div>
        </div>

        <p className="text-[11px] uppercase tracking-widest text-orange-500 mt-5">{l.dimension}</p>
        <h1 className="font-heading font-black text-2xl tracking-tight leading-tight">{l.title}</h1>
        <p className="text-stone-500 text-sm mt-1">{l.module_title} · {l.duration_min} min</p>

        <div className="mt-5 rounded-2xl border border-stone-800 bg-stone-900 p-5">
          <p className="text-stone-300 whitespace-pre-line leading-relaxed">{l.content}</p>
        </div>

        <button data-testid="complete-lesson-button" disabled={busy || l.completed} onClick={complete}
          className={`mt-6 w-full min-h-[52px] rounded-xl font-semibold flex items-center justify-center gap-2 transition-all active:scale-95 ${l.completed ? "bg-stone-800 text-orange-500" : "bg-orange-600 hover:bg-orange-500 text-white"} disabled:opacity-80`}>
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle2 className="w-5 h-5" />}
          {l.completed ? "Aula concluída" : "Marcar como concluída"}
        </button>
      </div>
    </Shell>
  );
}
