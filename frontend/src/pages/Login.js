import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { apiError, api } from "../lib/api";
import { Flame, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login, register } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = mode === "login" ? await login(email, password) : await register(name, email, password);
      nav(u.onboarded ? "/app" : "/onboarding");
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail) || "Erro ao entrar");
    } finally { setBusy(false); }
  };

  const forgot = async () => {
    if (!email) return toast.error("Digite seu e-mail primeiro.");
    try { await api.post("/auth/forgot-password", { email }); toast.success("Se o e-mail existir, enviaremos instruções."); }
    catch { toast.error("Não foi possível processar."); }
  };

  return (
    <div className="App relative min-h-screen bg-stone-950 text-stone-50 flex flex-col">
      <div className="noise" />
      <div className="relative z-10 flex-1 flex flex-col justify-center max-w-md mx-auto w-full px-6 py-12 fade-up">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-12 h-12 rounded-2xl bg-orange-600 flex items-center justify-center glow-current">
            <Flame className="w-7 h-7 text-white" strokeWidth={2} />
          </div>
          <div>
            <h1 className="font-heading font-black text-3xl tracking-tight leading-none">CAMINHO</h1>
            <p className="text-stone-500 text-xs mt-0.5">Formação, comunhão e missão.</p>
          </div>
        </div>

        <p className="font-serifq italic text-2xl text-stone-300 mt-8 mb-8 leading-snug">
          "Vinde e vede." <span className="text-stone-500 text-lg">— Jo 1,39</span>
        </p>

        <form onSubmit={submit} className="flex flex-col gap-4">
          {mode === "register" && (
            <input data-testid="register-name-input" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Seu nome" required
              className="min-h-[52px] rounded-xl bg-stone-900 border border-stone-800 px-4 text-stone-50 placeholder-stone-500 focus:border-orange-600/60 outline-none transition-colors" />
          )}
          <input data-testid="login-email-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="E-mail" required
            className="min-h-[52px] rounded-xl bg-stone-900 border border-stone-800 px-4 text-stone-50 placeholder-stone-500 focus:border-orange-600/60 outline-none transition-colors" />
          <input data-testid="login-password-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder="Senha" required
            className="min-h-[52px] rounded-xl bg-stone-900 border border-stone-800 px-4 text-stone-50 placeholder-stone-500 focus:border-orange-600/60 outline-none transition-colors" />

          <button data-testid="login-submit-button" disabled={busy} type="submit"
            className="min-h-[52px] rounded-xl bg-orange-600 hover:bg-orange-500 active:scale-95 transition-all duration-200 font-semibold text-white flex items-center justify-center gap-2 disabled:opacity-60">
            {busy && <Loader2 className="w-5 h-5 animate-spin" />}
            {mode === "login" ? "Entrar na caminhada" : "Começar a caminhada"}
          </button>
        </form>

        <div className="flex items-center justify-between mt-5 text-sm">
          <button data-testid="toggle-mode-button" onClick={() => setMode(mode === "login" ? "register" : "login")}
            className="text-stone-400 hover:text-orange-500 transition-colors">
            {mode === "login" ? "Criar conta" : "Já tenho conta"}
          </button>
          {mode === "login" && (
            <button data-testid="forgot-password-button" onClick={forgot} className="text-stone-500 hover:text-orange-500 transition-colors">
              Recuperar senha
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
