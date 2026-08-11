import { useEffect, useRef, useState } from "react";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Loader2, Trash2, Star, Ban, MicOff } from "lucide-react";
import { toast } from "sonner";

// Painel de chat com moderação. Reusado no estúdio e no espectador.
export function ChatPanel({ bid, canModerate }) {
  const { user } = useAuth();
  const [msgs, setMsgs] = useState([]);
  const [enabled, setEnabled] = useState(true);
  const [text, setText] = useState("");
  const boxRef = useRef(null);

  const load = async () => {
    try { const { data } = await api.get(`/broadcasts/${bid}/chat`); setMsgs(data.messages); setEnabled(data.chat_enabled); }
    catch { /* silencioso no polling */ }
  };
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); /* eslint-disable-next-line */ }, [bid]);
  useEffect(() => { if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight; }, [msgs]);

  const send = async () => {
    if (!text.trim()) return;
    const t = text.trim(); setText("");
    try { await api.post(`/broadcasts/${bid}/chat`, { text: t }); await load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const del = async (id) => { try { await api.delete(`/broadcasts/${bid}/chat/${id}`); await load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const hl = async (id) => { try { await api.post(`/broadcasts/${bid}/chat/${id}/highlight`); await load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const mod = async (action, uid) => { try { await api.post(`/broadcasts/${bid}/moderate`, { action, user_id: uid }); toast.success("Ação aplicada."); await load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const toggleChat = async () => { try { const { data } = await api.post(`/broadcasts/${bid}/moderate`, { action: "toggle_chat" }); setEnabled(data.chat_enabled); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };

  return (
    <div className="rounded-2xl border border-stone-800 bg-stone-900 flex flex-col" data-testid="chat-panel" style={{ height: 380 }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-stone-800">
        <span className="font-heading font-bold text-sm">💬 Chat ao vivo</span>
        {canModerate && <button data-testid="chat-toggle" onClick={toggleChat} className={`text-[11px] rounded-full px-2 py-0.5 ${enabled ? "text-green-400 border border-green-600/40" : "text-red-400 border border-red-600/40"}`}>{enabled ? "Ativo" : "Desativado"}</button>}
      </div>
      <div ref={boxRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {msgs.length === 0 && <p className="text-stone-600 text-xs">Seja o primeiro a comentar.</p>}
        {msgs.map((m) => (
          <div key={m.id} data-testid={`chat-msg-${m.id}`} className={`text-sm ${m.highlighted ? "bg-orange-600/15 border border-orange-600/40 rounded-lg px-2 py-1" : ""}`}>
            <span className="font-semibold text-orange-400">{m.name}:</span> <span className="text-stone-200">{m.text}</span>
            {canModerate && (
              <span className="ml-2 inline-flex gap-1.5 align-middle">
                <button title="Destacar" onClick={() => hl(m.id)} className="text-stone-500 hover:text-orange-400"><Star className="w-3.5 h-3.5" /></button>
                <button title="Apagar" onClick={() => del(m.id)} className="text-stone-500 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                <button title="Silenciar" onClick={() => mod("mute", m.user_id)} className="text-stone-500 hover:text-yellow-400"><MicOff className="w-3.5 h-3.5" /></button>
                <button title="Bloquear" onClick={() => mod("block", m.user_id)} className="text-stone-500 hover:text-red-500"><Ban className="w-3.5 h-3.5" /></button>
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="p-3 border-t border-stone-800 flex gap-2">
        <input data-testid="chat-input" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder={enabled ? "Mensagem..." : "Chat desativado"} disabled={!enabled} className="flex-1 bg-stone-800 border border-stone-700 rounded-lg px-3 py-2 text-sm text-stone-100 outline-none focus:border-orange-600/60 disabled:opacity-50" />
        <button data-testid="chat-send" onClick={send} disabled={!enabled} className="px-4 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold disabled:opacity-50">Enviar</button>
      </div>
    </div>
  );
}
