import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Bell, CheckCheck } from "lucide-react";

export default function Notifications() {
  const [items, setItems] = useState(null);
  const nav = useNavigate();

  const load = () => api.get("/notifications").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const markRead = async () => { await api.post("/notifications/read"); await load(); };

  if (!items) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2"><Bell className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Notificações</h1></div>
          {items.some((n) => !n.read) && (
            <button data-testid="mark-all-read" onClick={markRead} className="text-xs text-orange-400 flex items-center gap-1"><CheckCheck className="w-4 h-4" /> Marcar lidas</button>
          )}
        </div>

        {items.length === 0 && <p className="text-stone-500 text-sm text-center py-10">Nenhuma notificação por enquanto.</p>}

        <div className="space-y-2">
          {items.map((n) => (
            <div key={n.id} data-testid={`notif-${n.id}`} className={`rounded-2xl border p-4 ${n.read ? "border-stone-800 bg-stone-900/60" : "border-orange-600/40 bg-orange-600/10"}`}>
              <div className="flex items-start gap-3">
                {!n.read && <span className="w-2 h-2 rounded-full bg-orange-500 mt-1.5 shrink-0" />}
                <div className="flex-1">
                  <p className="font-semibold text-sm">{n.title}</p>
                  <p className="text-sm text-stone-400 mt-0.5">{n.body}</p>
                  <p className="text-[11px] text-stone-600 mt-1">{new Date(n.at).toLocaleString("pt-BR")}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}
