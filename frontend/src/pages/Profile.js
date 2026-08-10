import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { LogOut, Users, ShieldCheck, Flame, ChevronRight, Sparkles } from "lucide-react";

const roleLabel = { admin: "Administrador", formador: "Formador", moderador: "Moderador", membro: "Membro" };

export default function Profile() {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  return (
    <Shell>
      <div className="fade-up">
        <div className="flex items-center gap-4 mb-8">
          <div className="w-16 h-16 rounded-full bg-orange-600 flex items-center justify-center font-heading font-black text-2xl text-white">{user.name[0]}</div>
          <div>
            <h1 className="font-heading font-black text-2xl tracking-tight">{user.name}</h1>
            <p className="text-stone-500 text-sm">{user.email}</p>
            <span className="inline-block mt-1 text-[11px] text-orange-500 border border-orange-600/40 rounded-full px-2 py-0.5">{roleLabel[user.role]}</span>
          </div>
        </div>

        <div className="space-y-2">
          <button data-testid="profile-missao" onClick={() => nav("/app/missao")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
            <Flame className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Missões da semana</span><ChevronRight className="text-stone-500" />
          </button>

          <button data-testid="profile-assistente" onClick={() => nav("/app/assistente")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
            <Sparkles className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Assistente de Formação</span><ChevronRight className="text-stone-500" />
          </button>

          {(user.role === "formador" || user.role === "admin") && (
            <button data-testid="profile-people" onClick={() => nav("/app/pessoas")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
              <Users className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Minhas Pessoas</span><ChevronRight className="text-stone-500" />
            </button>
          )}

          {user.role === "admin" && (
            <button data-testid="profile-admin" onClick={() => nav("/app/admin")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
              <ShieldCheck className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Administração</span><ChevronRight className="text-stone-500" />
            </button>
          )}

          <button data-testid="logout-button" onClick={logout} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform text-red-400 mt-6">
            <LogOut className="w-5 h-5" /><span className="flex-1 text-left">Sair</span>
          </button>
        </div>
      </div>
    </Shell>
  );
}
