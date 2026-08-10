import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Radio, Loader2 } from "lucide-react";

export default function Lives() {
  const [live, setLive] = useState(undefined);
  useEffect(() => { api.get("/dashboard").then((r) => setLive(r.data.next_live || null)); }, []);

  if (live === undefined) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center gap-2 mb-6"><Radio className="w-6 h-6 text-red-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Lives</h1></div>
        <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Próximas</h3>
        {live ? (
          <div className="rounded-2xl border border-stone-800 bg-stone-900 overflow-hidden">
            <div className="h-32 bg-[radial-gradient(ellipse_at_center,_rgba(220,38,38,0.25),_transparent_70%)] flex items-center justify-center"><Radio className="w-10 h-10 text-red-500" /></div>
            <div className="p-5">
              <p className="text-red-500 text-xs font-semibold uppercase tracking-wide">Em breve</p>
              <h4 className="font-heading font-bold text-lg">{live.title}</h4>
              <p className="text-stone-400 text-sm mt-1">{live.description}</p>
              <p className="text-stone-500 text-xs mt-2">{new Date(live.date).toLocaleString("pt-BR", { weekday: "long", day: "2-digit", month: "long", hour: "2-digit", minute: "2-digit" })}</p>
            </div>
          </div>
        ) : <p className="text-stone-500 text-sm">Nenhuma live agendada.</p>}
        <p className="text-stone-600 text-xs mt-8 text-center">Transmissões ao vivo, chat e presença chegam em breve nesta área.</p>
      </div>
    </Shell>
  );
}
