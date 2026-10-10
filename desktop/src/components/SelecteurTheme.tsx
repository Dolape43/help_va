import { useRef, type KeyboardEvent } from "react";
import { ICONES_3D } from "../icones3d";
import type { Theme } from "../App";

/**
 * Clair / sombre. C'est un groupe radio : UN seul arrêt de Tab (sur le choix actif),
 * puis les flèches changent de choix (comportement standard attendu au clavier).
 * Utilisé dans la barre latérale et sur les écrans de licence.
 */
export default function SelecteurTheme({ theme, setTheme }: { theme: Theme; setTheme: (t: Theme) => void }) {
  const radios = useRef<Record<Theme, HTMLButtonElement | null>>({ light: null, dark: null });
  const fleche = (e: KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const autre: Theme = theme === "light" ? "dark" : "light";
    setTheme(autre);
    radios.current[autre]?.focus();
  };

  return (
    <div role="radiogroup" aria-label="Thème" className="relative flex rounded-lg border border-line bg-fg/[0.04] p-0.5">
      <span
        aria-hidden="true"
        className={`absolute top-0.5 h-6 w-6 rounded-md bg-surface shadow-[0_0_0_1px_var(--line),0_1px_2px_rgba(0,0,0,0.12)] transition-transform duration-200 ease-out ${
          theme === "dark" ? "translate-x-6" : "translate-x-0"
        }`}
      />
      {(["light", "dark"] as const).map((t) => (
        <button
          key={t}
          type="button"
          role="radio"
          aria-checked={theme === t}
          ref={(el) => {
            radios.current[t] = el;
          }}
          tabIndex={theme === t ? 0 : -1}
          onKeyDown={fleche}
          aria-label={t === "light" ? "Thème clair" : "Thème sombre"}
          onClick={() => setTheme(t)}
          className={`group relative z-10 grid h-6 w-6 place-items-center rounded-md transition-colors duration-150 ${
            theme === t ? "text-fg" : "text-fg-3 hover:text-fg-2"
          }`}
        >
          {/* Le choix inactif est grisé : on voit tout de suite quel thème est en place. */}
          <img
            src={t === "light" ? ICONES_3D.soleil : ICONES_3D.lune}
            alt=""
            draggable={false}
            className={`h-[18px] w-[18px] object-contain transition-[filter,opacity] duration-150 ${
              theme === t ? "" : "opacity-45 grayscale group-hover:opacity-80"
            }`}
          />
        </button>
      ))}
    </div>
  );
}
