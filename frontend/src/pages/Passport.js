import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Sparkles, BookOpen, Flame, Tent, Users, Megaphone, Handshake, Crown, Lock } from "lucide-react";

const ICONS = { sparkles: Sparkles, "book-open": BookOpen, flame: Flame, tent: Tent, users: Users, megaphone: Megaphone, handshake: Handshake, crown: Crown };

export default function Passport() {
  const [data, setData] = useState(null);
  const nav = useNavigate();
  useEffect(() => { api.get("/passport").then((r) => setData(r.data)); }, []);

  if (!data) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <h1 className="font-heading font-black text-3xl tracking-tight">Passaporte da Jornada</h1>
        <p className="text-stone-500 text-sm mb-2">Os marcos que celebram a sua caminhada.</p>
        <p className="text-orange-500 text-sm font-semibold mb-6">{data.earned_count} de {data.total} selos conquistados</p>

        <div className="grid grid-cols-2 gap-3">
          {data.items.map((m) => {
            const Icon = ICONS[m.icon] || Sparkles;
            return (
              <div key={m.key} data-testid={`milestone-${m.key}`}
                className={`rounded-2xl border p-4 flex flex-col items-center text-center transition-all ${m.earned ? "border-orange-600/50 bg-orange-600/10" : "border-stone-800 bg-stone-900/60 opacity-70"}`}>
                <div className={`w-14 h-14 rounded-full flex items-center justify-center mb-3 ${m.earned ? "bg-orange-600 text-white glow-current" : "bg-stone-800 text-stone-600"}`}>
                  {m.earned ? <Icon className="w-6 h-6" strokeWidth={1.75} /> : <Lock className="w-5 h-5" />}
                </div>
                <p className="font-heading font-bold text-sm leading-tight">{m.title}</p>
                <p className="text-[11px] text-stone-500 mt-1 leading-snug">{m.description}</p>
                {m.earned && m.awarded_at && <p className="text-[10px] text-orange-500/70 mt-2">{new Date(m.awarded_at).toLocaleDateString("pt-BR")}</p>}
              </div>
            );
          })}
        </div>
      </div>
    </Shell>
  );
}
