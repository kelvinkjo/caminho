import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";
import Login from "@/pages/Login";
import Onboarding from "@/pages/Onboarding";
import Dashboard from "@/pages/Dashboard";
import Journey from "@/pages/Journey";
import Formation from "@/pages/Formation";
import StageDetail from "@/pages/StageDetail";
import LessonPlayer from "@/pages/LessonPlayer";
import Missions from "@/pages/Missions";
import MyPeople from "@/pages/MyPeople";
import Profile from "@/pages/Profile";
import Lives from "@/pages/Lives";
import Admin from "@/pages/Admin";
import Assistant from "@/pages/Assistant";
import Apologetics from "@/pages/Apologetics";
import Search from "@/pages/Search";
import MasterControl from "@/pages/MasterControl";
import Passport from "@/pages/Passport";
import Notifications from "@/pages/Notifications";
import PastoralReport from "@/pages/PastoralReport";
import StageRequirements from "@/pages/StageRequirements";
import MasterPermissions from "@/pages/MasterPermissions";
import FormerPanel from "@/pages/FormerPanel";

function Splash() {
  return <div className="min-h-screen bg-stone-950 flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-orange-600" /></div>;
}

function Protected({ children, roles }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading || user === null) return <Splash />;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.onboarded && loc.pathname !== "/onboarding") return <Navigate to="/onboarding" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/app" replace />;
  return children;
}

function Guest({ children }) {
  const { user, loading } = useAuth();
  if (loading || user === null) return <Splash />;
  if (user) return <Navigate to={user.onboarded ? "/app" : "/onboarding"} replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <Toaster position="top-center" theme="dark" richColors />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Guest><Login /></Guest>} />
          <Route path="/onboarding" element={<Protected><Onboarding /></Protected>} />
          <Route path="/app" element={<Protected><Dashboard /></Protected>} />
          <Route path="/app/jornada" element={<Protected><Journey /></Protected>} />
          <Route path="/app/formacao" element={<Protected><Formation /></Protected>} />
          <Route path="/app/formacao/:order" element={<Protected><StageDetail /></Protected>} />
          <Route path="/app/aula/:id" element={<Protected><LessonPlayer /></Protected>} />
          <Route path="/app/missao" element={<Protected><Missions /></Protected>} />
          <Route path="/app/assistente" element={<Protected><Assistant /></Protected>} />
          <Route path="/app/defesa" element={<Protected><Apologetics /></Protected>} />
          <Route path="/app/busca" element={<Protected><Search /></Protected>} />
          <Route path="/app/lives" element={<Protected><Lives /></Protected>} />
          <Route path="/app/pessoas" element={<Protected roles={["formador", "admin", "mestre"]}><MyPeople /></Protected>} />
          <Route path="/app/perfil" element={<Protected><Profile /></Protected>} />
          <Route path="/app/mestre" element={<Protected roles={["mestre"]}><MasterControl /></Protected>} />
          <Route path="/app/mestre/relatorio" element={<Protected roles={["mestre"]}><PastoralReport /></Protected>} />
          <Route path="/app/mestre/requisitos" element={<Protected roles={["mestre"]}><StageRequirements /></Protected>} />
          <Route path="/app/mestre/permissoes" element={<Protected roles={["mestre"]}><MasterPermissions /></Protected>} />
          <Route path="/app/formador" element={<Protected roles={["formador", "mestre"]}><FormerPanel /></Protected>} />
          <Route path="/app/passaporte" element={<Protected><Passport /></Protected>} />
          <Route path="/app/notificacoes" element={<Protected><Notifications /></Protected>} />
          <Route path="/app/admin" element={<Protected roles={["admin", "mestre"]}><Admin /></Protected>} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
