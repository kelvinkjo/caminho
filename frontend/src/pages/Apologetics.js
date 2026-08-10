import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, ShieldCheck, Loader2, ChevronDown } from "lucide-react";

function Field({ label, value }) {
  if (!value) return null;
  return (
    <div className="border-t border-stone-800 pt-3">
      <p className="text-[11px] uppercase tracking-widest text-orange-500 mb-1">{label}</p>
      <p className="text-stone-300 text-sm leading-relaxed whitespace-pre-line">{value}</p>
    </div>
  );
}

export default function Apologetics() {
  const [data, setData] = useState(null);
  const [cat, setCat] = useState(null);
  const [open, setOpen] = useState(null);
  const nav = useNavigate();

  const load = (c) => api.get("/apologetics", { params: c ? { category: c } : {} }).then((r) => setData(r.data));
  useEffect(() => { load(); }, []);

  const pick = (c) => { setCat(c); setOpen(null); load(c); };

  if (!data) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><ShieldCheck className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Defesa da Fé</h1></div>
        <p className="text-stone-500 text-sm mb-5">Apologética católica com fontes: Bíblia, Tradição, Catecismo e Magistério.</p>

        <div className="flex gap-2 overflow-x-auto pb-2 mb-5 -mx-1 px-1">
          <button data-testid="apol-cat-all" onClick={() => pick(null)} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium ${!cat ? "bg-orange-600 text-white" : "bg-stone-900 border border-stone-800 text-stone-400"}`}>Todas</button>
          {data.categories.map((c) => (
            <button key={c} data-testid={`apol-cat-${c}`} onClick={() => pick(c)} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium ${cat === c ? "bg-orange-600 text-white" : "bg-stone-900 border border-stone-800 text-stone-400"}`}>{c}</button>
          ))}
        </div>

        <div className="space-y-3">
          {data.items.map((a) => (
            <div key={a.id} data-testid={`apol-${a.id}`} className="rounded-2xl border border-stone-800 bg-stone-900 overflow-hidden">
              <button onClick={() => setOpen(open === a.id ? null : a.id)} className="w-full flex items-start gap-3 text-left p-4">
                <div className="flex-1">
                  <p className="text-[11px] uppercase tracking-wide text-orange-500">{a.category}</p>
                  <h3 className="font-heading font-bold leading-tight">{a.question}</h3>
                  <p className="text-stone-300 text-sm mt-1">{a.answer}</p>
                </div>
                <ChevronDown className={`w-5 h-5 text-stone-500 shrink-0 transition-transform ${open === a.id ? "rotate-180" : ""}`} />
              </button>
              {open === a.id && (
                <div className="px-4 pb-4 space-y-3">
                  <Field label="Explicação" value={a.explanation} />
                  <Field label="Bíblia" value={a.bible} />
                  <Field label="Tradição" value={a.tradition} />
                  <Field label="Catecismo" value={a.catechism} />
                  <Field label="Magistério" value={a.magisterium} />
                  <Field label="Material complementar" value={a.extra} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}
