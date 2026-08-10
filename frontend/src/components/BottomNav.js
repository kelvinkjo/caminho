import { NavLink } from "react-router-dom";
import { Home, Route, BookOpen, Radio, User } from "lucide-react";

const items = [
  { to: "/app", icon: Home, label: "Início", testid: "nav-inicio", end: true },
  { to: "/app/jornada", icon: Route, label: "Jornada", testid: "nav-jornada" },
  { to: "/app/formacao", icon: BookOpen, label: "Formação", testid: "nav-formacao" },
  { to: "/app/lives", icon: Radio, label: "Lives", testid: "nav-lives" },
  { to: "/app/perfil", icon: User, label: "Perfil", testid: "nav-perfil" },
];

export function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 backdrop-blur-xl bg-stone-950/80 border-t border-stone-800">
      <div className="max-w-lg mx-auto flex items-stretch justify-around px-2 py-2">
        {items.map(({ to, icon: Icon, label, testid, end }) => (
          <NavLink key={to} to={to} end={end} data-testid={testid}
            className={({ isActive }) =>
              `flex flex-col items-center gap-1 px-3 py-1.5 min-h-[48px] transition-colors duration-200 ${isActive ? "text-orange-500" : "text-stone-500"}`}>
            <Icon strokeWidth={1.75} className="w-6 h-6" />
            <span className="text-[10px] font-medium">{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
