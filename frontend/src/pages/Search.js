import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Search as SearchIcon, Loader2, Sparkles, BookOpen, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function Search() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  const run = async (e) => {
    e.preventDefault();
    if (q.trim().length < 2) return toast.error("Digite ao menos 2 caracteres.");
    setBusy(true); setRes(null);
    try {
      const { data } = await api.get("/search", { params: { q } });
      setRes(data);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><SearchIcon className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Busca Inteligente</h1></div>
        <p className="text-stone-500 text-sm mb-5">Busque por tema na formação e receba uma resposta doutrinal.</p>

        <form onSubmit={run} className="flex gap-2 mb-6">
          <input data-testid="search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ex.: adoração, Eucaristia, vocação..."
            className="flex-1 min-h-[48px] rounded-xl bg-stone-900 border border-stone-800 px-4 text-stone-50 placeholder-stone-500 focus:border-orange-600/60 outline-none transition-colors" />
          <button data-testid="search-submit" type="submit" disabled={busy} className="min-w-[48px] rounded-xl bg-orange-600 hover:bg-orange-500 flex items-center justify-center text-white active:scale-95 transition-all disabled:opacity-60">
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <SearchIcon className="w-5 h-5" />}
          </button>
        </form>

        {res && (
          <div className="space-y-6">
            {res.answer && (
              <div data-testid="search-answer" className="rounded-2xl border border-orange-600/40 bg-orange-600/10 p-5">
                <p className="text-[11px] uppercase tracking-widest text-orange-500 mb-2 flex items-center gap-1"><Sparkles className="w-3.5 h-3.5" /> Resposta doutrinal</p>
                <p className="text-stone-200 text-sm leading-relaxed whitespace-pre-line">{res.answer}</p>
              </div>
            )}

            {res.lessons?.length > 0 && (
              <div>
                <h3 className="font-heading font-bold text-sm text-stone-400 mb-2 flex items-center gap-2"><BookOpen className="w-4 h-4 text-orange-500" /> Aulas</h3>
                <div className="space-y-2">
                  {res.lessons.map((l) => (
                    <button key={l.id} data-testid={`search-lesson-${l.id}`} onClick={() => nav(`/app/aula/${l.id}`)} className="w-full text-left rounded-xl border border-stone-800 bg-stone-900 p-3.5 active:scale-[0.99] transition-transform">
                      <p className="text-xs text-stone-500">{l.module_title} · {l.dimension}</p>
                      <p className="font-medium text-sm">{l.title}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {res.apologetics?.length > 0 && (
              <div>
                <h3 className="font-heading font-bold text-sm text-stone-400 mb-2 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-orange-500" /> Defesa da Fé</h3>
                <div className="space-y-2">
                  {res.apologetics.map((a) => (
                    <button key={a.id} data-testid={`search-apol-${a.id}`} onClick={() => nav("/app/defesa")} className="w-full text-left rounded-xl border border-stone-800 bg-stone-900 p-3.5 active:scale-[0.99] transition-transform">
                      <p className="text-xs text-orange-500">{a.category}</p>
                      <p className="font-medium text-sm">{a.question}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {!res.answer && !res.lessons?.length && !res.apologetics?.length && (
              <p className="text-stone-500 text-sm text-center py-6">Nenhum resultado encontrado.</p>
            )}
          </div>
        )}
      </div>
    </Shell>
  );
}
