import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Users, Award, Clock } from "lucide-react";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, ResponsiveContainer, Cell } from "recharts";

export default function Admin() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [formadores, setFormadores] = useState([]);
  const nav = useNavigate();

  const load = async () => {
    const [s, u, f] = await Promise.all([api.get("/admin/stats"), api.get("/admin/users"), api.get("/formadores")]);
    setStats(s.data); setUsers(u.data); setFormadores(f.data);
  };
  useEffect(() => { load(); }, []);

  const patch = async (uid, body) => {
    try { await api.patch(`/admin/users/${uid}`, body); toast.success("Atualizado."); await load(); }
    catch { toast.error("Erro ao atualizar."); }
  };

  if (!stats) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <h1 className="font-heading font-black text-3xl tracking-tight mb-6">Administração</h1>

        <div className="grid grid-cols-3 gap-3 mb-6">
          <Stat icon={Users} label="Membros" value={stats.total_users} />
          <Stat icon={Clock} label="A avaliar" value={stats.pending_approvals} />
          <Stat icon={Award} label="Formadores" value={stats.formadores} />
        </div>

        <div className="rounded-2xl border border-stone-800 bg-stone-900 p-4 mb-8">
          <h3 className="font-heading font-bold text-sm mb-3">Membros por etapa</h3>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={stats.by_stage}>
              <XAxis dataKey="order" tick={{ fill: "#78716c", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                {stats.by_stage.map((_, i) => <Cell key={i} fill="#EA580C" />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <h3 className="font-heading font-bold text-sm text-stone-400 mb-3">Usuários</h3>
        <div className="space-y-3">
          {users.map((u) => (
            <div key={u.id} data-testid={`admin-user-${u.id}`} className="rounded-2xl border border-stone-800 bg-stone-900 p-4">
              <div className="flex justify-between items-start mb-3">
                <div><p className="font-medium">{u.name}</p><p className="text-xs text-stone-500">{u.email}</p></div>
                <span className="text-[10px] text-orange-500 border border-orange-600/40 rounded-full px-2 py-0.5">{u.role}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <select data-testid={`role-select-${u.id}`} value={u.role} onChange={(e) => patch(u.id, { role: e.target.value })}
                  className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-stone-200">
                  {["membro", "formador", "moderador", "admin"].map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <select data-testid={`stage-select-${u.id}`} value={u.current_stage_order} onChange={(e) => patch(u.id, { current_stage_order: Number(e.target.value) })}
                  className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-stone-200">
                  {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>Etapa {n}</option>)}
                </select>
                <select data-testid={`formador-select-${u.id}`} value={u.formador_id || ""} onChange={(e) => patch(u.id, { formador_id: e.target.value })}
                  className="bg-stone-800 border border-stone-700 rounded-lg px-2 py-2 text-stone-200">
                  <option value="">Formador</option>
                  {formadores.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </div>
              <button data-testid={`block-${u.id}`} onClick={() => patch(u.id, { blocked: !u.blocked })}
                className={`mt-2 text-xs ${u.blocked ? "text-green-500" : "text-red-400"}`}>
                {u.blocked ? "Desbloquear" : "Bloquear"}
              </button>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="rounded-2xl border border-stone-800 bg-stone-900 p-4 text-center">
      <Icon className="w-5 h-5 text-orange-500 mx-auto mb-1" />
      <p className="font-heading font-black text-2xl">{value}</p>
      <p className="text-[10px] text-stone-500">{label}</p>
    </div>
  );
}
