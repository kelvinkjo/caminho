import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { motion, AnimatePresence } from "framer-motion";

const screens = [
  { title: "Bem-vindo à sua caminhada.", sub: "Você não chegou aqui por acaso.", emoji: "" },
  { title: "Uma jornada de formação, comunidade e missão.", sub: "Você não caminha sozinho." },
  { title: "Descubra sua vocação. Forme-se. Sirva. Entregue-se.", sub: "Encontro · Discernimento · Missão · Entrega" },
];

export default function Onboarding() {
  const { user, refreshUser } = useAuth();
  const nav = useNavigate();
  const [i, setI] = useState(0);

  const finish = async () => {
    await api.post("/auth/onboard-complete");
    await refreshUser();
    nav("/app");
  };

  const last = i === screens.length;

  return (
    <div className="App relative min-h-screen bg-stone-950 text-stone-50 flex flex-col overflow-hidden">
      <div className="noise" />
      <div className="absolute inset-0 z-0 bg-[radial-gradient(ellipse_at_top,_rgba(234,88,12,0.18),_transparent_60%)]" />
      <div className="relative z-10 flex-1 flex flex-col justify-between max-w-md mx-auto w-full px-7 py-16">
        <div className="flex gap-2">
          {[...screens, {}].map((_, idx) => (
            <div key={idx} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${idx <= i ? "bg-orange-600" : "bg-stone-800"}`} />
          ))}
        </div>

        <AnimatePresence mode="wait">
          {!last ? (
            <motion.div key={i} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -14 }} transition={{ duration: 0.4 }} className="my-auto">
              <h2 className="font-heading font-black text-4xl leading-tight tracking-tight">{screens[i].title}</h2>
              <p className="font-serifq italic text-2xl text-stone-400 mt-5">{screens[i].sub}</p>
            </motion.div>
          ) : (
            <motion.div key="stage" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="my-auto">
              <p className="text-stone-500 uppercase tracking-widest text-xs mb-3">Sua etapa atual</p>
              <div className="rounded-2xl border border-orange-600/40 bg-orange-600/10 p-7 glow-current">
                <h2 className="font-heading font-black text-3xl">Etapa {user?.current_stage_order}</h2>
                <p className="text-stone-300 mt-2">Sua caminhada começa aqui. Avance com constância e acompanhamento.</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button data-testid="onboarding-next-button"
          onClick={() => (last ? finish() : setI(i + 1))}
          className="min-h-[54px] rounded-xl bg-orange-600 hover:bg-orange-500 active:scale-95 transition-all duration-200 font-semibold text-white">
          {last ? "Entrar no meu Caminho" : "Continuar"}
        </button>
      </div>
    </div>
  );
}
