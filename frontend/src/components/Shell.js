import { BottomNav } from "./BottomNav";

export function Shell({ children }) {
  return (
    <div className="App relative min-h-screen bg-stone-950 text-stone-50">
      <div className="noise" />
      <div className="relative z-10 max-w-lg mx-auto pb-28 px-5 pt-6">{children}</div>
      <BottomNav />
    </div>
  );
}
