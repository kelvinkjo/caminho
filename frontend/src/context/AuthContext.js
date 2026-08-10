import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const token = localStorage.getItem("caminho_token");
    if (!token) { setUser(false); setLoading(false); return; }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      localStorage.removeItem("caminho_token");
      setUser(false);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("caminho_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const register = async (name, email, password) => {
    const { data } = await api.post("/auth/register", { name, email, password });
    localStorage.setItem("caminho_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch {}
    localStorage.removeItem("caminho_token");
    setUser(false);
  };

  const refreshUser = async () => {
    try { const { data } = await api.get("/auth/me"); setUser(data); } catch {}
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}
