import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Flame, CheckCircle2, Circle, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Missions() {
  const [missions, setMissions] = useState(null);
  const load = () => api.get("/missions").then((r) => setMissions(r.data));
  useEffect(() => { load(); }, []);

  const complete = async (id) => {
    try { await api.post(`/missions/${id}/complete`); toast.success("Missão registrada!"); await load(); }
    catch { toast.error("Erro."); }
  };

  if (!missions) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center gap-2 mb-1"><Flame className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Missões</h1></div>
        <p className="text-stone-500 text-sm mb-6">Celebre a constância e o serviço. Sem pontos, sem competição.</p>
        <div className="space-y-2">
          {missions.map((m) => (
            <button key={m.id} data-testid={`mission-${m.id}`} disabled={m.completed} onClick={() => complete(m.id)}
              className="w-full flex items-center gap-3 text-left rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform disabled:opacity-90">
              {m.completed ? <CheckCircle2 className="w-6 h-6 text-orange-500 shrink-0" /> : <Circle className="w-6 h-6 text-stone-600 shrink-0" />}
              <div className="flex-1"><p className={`${m.completed ? "line-through text-stone-500" : ""}`}>{m.title}</p><p className="text-xs text-orange-500/70">{m.dimension}</p></div>
            </button>
          ))}
        </div>
      </div>
    </Shell>
  );
}
