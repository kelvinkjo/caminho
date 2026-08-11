import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Shell } from "../components/Shell";
import { LogOut, Users, ShieldCheck, Flame, ChevronRight, Sparkles, Search, ShieldQuestion, Crown, Award, BookMarked, Clapperboard, Radio } from "lucide-react";

const roleLabel = { mestre: "Login Mestre", admin: "Administrador", formador: "Formador", moderador: "Moderador", membro: "Membro" };

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

          <button data-testid="profile-passaporte" onClick={() => nav("/app/passaporte")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
            <Award className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Passaporte da Jornada</span><ChevronRight className="text-stone-500" />
          </button>

          <button data-testid="profile-midia" onClick={() => nav("/app/midia")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
            <Clapperboard className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Central de Mídia</span><ChevronRight className="text-stone-500" />
          </button>

          <button data-testid="profile-transmissoes" onClick={() => nav("/app/transmissoes")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
            <Radio className="w-5 h-5 text-red-500" /><span className="flex-1 text-left">Central de Transmissão</span><ChevronRight className="text-stone-500" />
          </button>

          <button data-testid="profile-busca" onClick={() => nav("/app/busca")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
            <Search className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Busca Inteligente</span><ChevronRight className="text-stone-500" />
          </button>

          <button data-testid="profile-defesa" onClick={() => nav("/app/defesa")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
            <ShieldQuestion className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Defesa da Fé</span><ChevronRight className="text-stone-500" />
          </button>

          {(user.role === "formador" || user.role === "mestre") && (
            <button data-testid="profile-formador-panel" onClick={() => nav("/app/formador")} className="w-full flex items-center gap-3 rounded-xl border border-orange-600/40 bg-orange-600/10 p-4 active:scale-[0.99] transition-transform">
              <BookMarked className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Central do Formador</span><ChevronRight className="text-stone-500" />
            </button>
          )}

          {(user.role === "formador" || user.role === "admin" || user.role === "mestre") && (
            <button data-testid="profile-people" onClick={() => nav("/app/pessoas")} className="w-full flex items-center gap-3 rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
              <Users className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Minhas Pessoas</span><ChevronRight className="text-stone-500" />
            </button>
          )}

          {user.role === "mestre" && (
            <button data-testid="profile-mestre" onClick={() => nav("/app/mestre")} className="w-full flex items-center gap-3 rounded-xl border border-orange-600/40 bg-orange-600/10 p-4 active:scale-[0.99] transition-transform">
              <Crown className="w-5 h-5 text-orange-500" /><span className="flex-1 text-left">Controle Mestre</span><ChevronRight className="text-stone-500" />
            </button>
          )}

          {(user.role === "admin" || user.role === "mestre") && (
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
