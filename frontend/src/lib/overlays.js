// Overlays visuais (lower-third e banner) renderizados sobre o vídeo — estúdio e espectador.
export function OverlayLayer({ scene }) {
  if (!scene) return null;
  const lt = scene.lower_third || {};
  const bn = scene.banner || {};
  return (
    <>
      {lt.visible && lt.name && (
        <div data-testid="overlay-lower-third" className="absolute left-4 bottom-10 bg-black/75 backdrop-blur px-4 py-2 rounded-r-lg border-l-4 border-orange-600 max-w-[70%]">
          <p className="font-heading font-bold text-white leading-tight">{lt.name}</p>
          {lt.role && <p className="text-orange-300 text-xs">{lt.role}</p>}
        </div>
      )}
      {bn.visible && bn.text && (
        <div data-testid="overlay-banner" className="absolute left-0 right-0 bottom-0 bg-orange-600/90 py-1.5 text-center">
          <p className="text-white text-sm font-semibold px-3 truncate">{bn.text}</p>
        </div>
      )}
    </>
  );
}
