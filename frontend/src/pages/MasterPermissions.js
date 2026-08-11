import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { ArrowLeft, Loader2, Lock, Save } from "lucide-react";
import { toast } from "sonner";

const GROUPS = {
  Cursos: ["CREATE_COURSE", "EDIT_COURSE", "DELETE_COURSE", "PUBLISH_COURSE"],
  Módulos: ["CREATE_MODULE", "EDIT_MODULE", "DELETE_MODULE"],
  Aulas: ["CREATE_LESSON", "EDIT_LESSON", "DELETE_LESSON", "PUBLISH_LESSON"],
  Mídias: ["UPLOAD_VIDEO", "UPLOAD_AUDIO", "UPLOAD_DOCUMENT"],
  Avisos: ["CREATE_ANNOUNCEMENT", "EDIT_ANNOUNCEMENT", "DELETE_ANNOUNCEMENT", "PUBLISH_ANNOUNCEMENT"],
  Lives: ["CREATE_LIVE", "EDIT_LIVE", "START_LIVE", "END_LIVE", "MODERATE_LIVE"],
  Outros: ["VIEW_ANALYTICS", "MANAGE_CONTENT_ACCESS", "EDIT_ALL_CONTENT"],
};

export default function MasterPermissions() {
  const [list, setList] = useState(null);
  const [sel, setSel] = useState(null);
  const [perms, setPerms] = useState([]);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  const load = () => api.get("/master/formadores-permissions").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);

  const open = (f) => { setSel(f); setPerms(f.permissions || []); };
  const toggle = (p) => setPerms(perms.includes(p) ? perms.filter((x) => x !== p) : [...perms, p]);
  const save = async () => {
    setBusy(true);
    try { await api.put(`/master/formadores/${sel.id}/permissions`, { permissions: perms }); toast.success("Permissões salvas."); await load(); setSel(null); }
    catch { toast.error("Erro ao salvar."); }
    finally { setBusy(false); }
  };

  if (!list) return <Shell><div className="flex justify-center py-20"><Loader2 className="animate-spin text-orange-600" /></div></Shell>;

  return (
    <Shell>
      <div className="fade-up">
        <button data-testid="back-button" onClick={() => nav(-1)} className="flex items-center gap-1 text-stone-400 mb-4 text-sm"><ArrowLeft className="w-4 h-4" /> Voltar</button>
        <div className="flex items-center gap-2 mb-1"><Lock className="w-6 h-6 text-orange-500" /><h1 className="font-heading font-black text-3xl tracking-tight">Permissões</h1></div>
        <p className="text-stone-500 text-sm mb-6">Conceda a cada formador exatamente o que pode fazer. A etapa dos membros permanece exclusiva do Login Mestre.</p>

        <div className="space-y-2">
          {list.map((f) => (
            <button key={f.id} data-testid={`perm-formador-${f.id}`} onClick={() => open(f)} className="w-full text-left rounded-xl border border-stone-800 bg-stone-900 p-4 active:scale-[0.99] transition-transform">
              <p className="font-medium">{f.name}</p>
              <p className="text-xs text-stone-500">{f.permissions.length} permissões concedidas</p>
            </button>
          ))}
          {list.length === 0 && <p className="text-stone-500 text-sm">Nenhum formador cadastrado ainda.</p>}
        </div>
      </div>

      {sel && (
        <div className="fixed inset-0 z-[60] bg-black/70 flex items-end sm:items-center justify-center p-4 overflow-y-auto" onClick={() => setSel(null)}>
          <div className="w-full max-w-md rounded-2xl border border-stone-800 bg-stone-900 p-5 my-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-heading font-black text-xl mb-4">{sel.name}</h3>
            <div className="space-y-4 max-h-[55vh] overflow-y-auto pr-1">
              {Object.entries(GROUPS).map(([g, ps]) => (
                <div key={g}>
                  <p className="text-[11px] uppercase tracking-widest text-orange-500 mb-2">{g}</p>
                  <div className="space-y-1.5">
                    {ps.map((p) => (
                      <label key={p} data-testid={`perm-${p}`} className="flex items-center gap-3 text-sm cursor-pointer">
                        <input type="checkbox" checked={perms.includes(p)} onChange={() => toggle(p)} className="w-4 h-4 accent-orange-600" />
                        <span className={perms.includes(p) ? "text-stone-200" : "text-stone-500"}>{p}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setSel(null)} className="flex-1 min-h-[46px] rounded-lg border border-stone-700 text-stone-300 text-sm">Cancelar</button>
              <button data-testid="perm-save" disabled={busy} onClick={save} className="flex-1 min-h-[46px] rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold flex items-center justify-center gap-2">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Salvar</button>
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
