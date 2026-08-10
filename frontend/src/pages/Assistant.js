import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Send, Sparkles, Loader2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

const SUGGESTIONS = [
  "O que é a Eucaristia para a Igreja Católica?",
  "Por que os católicos honram Nossa Senhora?",
  "O que o Catecismo diz sobre a oração?",
  "Qual a diferença entre doutrina e opinião teológica?",
];

export default function Assistant() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const ask = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const { data } = await api.post("/assistant/ask", { question: q, session_id: sessionId });
      setMessages((m) => [...m, { role: "assistant", text: data.answer }]);
    } catch (e) {
      toast.error(apiError(e.response?.data?.detail) || "Erro no assistente");
      setMessages((m) => [...m, { role: "assistant", text: "Desculpe, não consegui responder agora. Tente novamente." }]);
    } finally { setBusy(false); }
  };

  return (
    <Shell>
      <div className="fade-up flex flex-col min-h-[70vh]">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><Sparkles className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Assistente de Formação</h1></div>
        <p className="text-stone-500 text-sm mb-4">Dúvidas sobre Bíblia, Catecismo, doutrina, santos e liturgia.</p>

        <div className="rounded-xl border border-stone-800 bg-stone-900/60 p-3 mb-4 flex gap-2 items-start">
          <ShieldAlert className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
          <p className="text-xs text-stone-400">O assistente apoia sua formação, mas não substitui o sacerdote, confessor, diretor espiritual ou formador.</p>
        </div>

        <div className="flex-1 space-y-3 mb-4">
          {messages.length === 0 && (
            <div className="space-y-2">
              <p className="text-xs text-stone-500">Sugestões:</p>
              {SUGGESTIONS.map((s) => (
                <button key={s} data-testid="suggestion-button" onClick={() => ask(s)}
                  className="w-full text-left text-sm rounded-xl border border-stone-800 bg-stone-900 p-3 text-stone-300 active:scale-[0.99] transition-transform">{s}</button>
              ))}
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} data-testid={`msg-${m.role}`} className={`max-w-[88%] rounded-2xl p-3.5 text-sm leading-relaxed whitespace-pre-line ${m.role === "user" ? "ml-auto bg-orange-600 text-white" : "mr-auto bg-stone-900 border border-stone-800 text-stone-200"}`}>{m.text}</div>
          ))}
          {busy && <div className="mr-auto bg-stone-900 border border-stone-800 rounded-2xl p-3.5"><Loader2 className="w-4 h-4 animate-spin text-orange-500" /></div>}
          <div ref={endRef} />
        </div>

        <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="sticky bottom-24 flex gap-2">
          <input data-testid="assistant-input" value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="Escreva sua pergunta..."
            className="flex-1 min-h-[48px] rounded-xl bg-stone-900 border border-stone-800 px-4 text-stone-50 placeholder-stone-500 focus:border-orange-600/60 outline-none transition-colors" />
          <button data-testid="assistant-send" type="submit" disabled={busy}
            className="min-w-[48px] rounded-xl bg-orange-600 hover:bg-orange-500 flex items-center justify-center text-white active:scale-95 transition-all disabled:opacity-60">
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </Shell>
  );
}
