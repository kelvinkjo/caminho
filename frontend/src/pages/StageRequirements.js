import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, SlidersHorizontal, BookOpen, Radio } from "lucide-react";
import { toast } from "sonner";

function Toggle({ on, onClick, testid }) {
  return (
    <button data-testid={testid} onClick={onClick} className={`w-11 h-6 rounded-full transition-colors relative ${on ? "bg-orange-600" : "bg-stone-700"}`}>
      <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}

export default function StageRequirements() {
  const [rows, setRows] = useState(null);
  const nav = useNavigate();

  const load = () => api.get("/master/stage-requirements").then((r) => setRows(r.data));
  useEffect(() => { load(); }, []);

  const update = async (order, patch) => {
    const row = rows.find((r) => r.order === order);
    const body = { require_lessons: row.require_lessons, require_mandatory_lives: row.require_mandatory_lives, ...patch };
    setRows(rows.map((r) => (r.order === order ? { ...r, ...body } : r)));
    try { await api.put(`/master/stage-requirements/${order}`, body); toast.success("Requisito atualizado."); }
    catch { toast.error("Erro ao salvar."); load(); }
  };

  if (!rows) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><SlidersHorizontal className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Requisitos por Etapa</h1></div>
        <p className="text-stone-500 text-sm mb-6">Defina o que conta como "formação concluída" em cada etapa. Isso não altera a etapa — apenas o cálculo da conclusão.</p>

        <div className="space-y-3">
          {rows.map((r) => (
            <div key={r.order} data-testid={`req-stage-${r.order}`} className="rounded-2xl border border-stone-800 bg-stone-900 p-4">
              <p className="font-heading font-bold mb-3">{r.name}</p>
              <div className="flex items-center gap-3 mb-3">
                <BookOpen className="w-4 h-4 text-orange-500" />
                <span className="flex-1 text-sm text-stone-300">Exigir 100% das aulas</span>
                <Toggle testid={`req-lessons-${r.order}`} on={r.require_lessons} onClick={() => update(r.order, { require_lessons: !r.require_lessons })} />
              </div>
              <div className="flex items-center gap-3">
                <Radio className="w-4 h-4 text-orange-500" />
                <span className="flex-1 text-sm text-stone-300">Exigir presença nas lives obrigatórias</span>
                <Toggle testid={`req-lives-${r.order}`} on={r.require_mandatory_lives} onClick={() => update(r.order, { require_mandatory_lives: !r.require_mandatory_lives })} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}
