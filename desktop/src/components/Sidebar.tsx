import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { GearSix, House, Moon, Sun } from "@phosphor-icons/react";
import logo from "../assets/logo.png";
import { MODULES, type CleModule } from "../modules";
import type { Page, Theme } from "../App";
import { versionApp } from "../plateforme";
import type { EtatConnexion } from "../engine/useMoteur";
import { initiales } from "../licence";

function Lien({
  actif,
  onClick,
  icone,
  badge,
  children,
}: {
  actif: boolean;
  onClick: () => void;
  icone: ReactNode;
  badge?: ReactNode;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={actif ? "page" : undefined}
      // Lien actif : on change la couleur et le fond, PAS la graisse (un texte plus gras est plus large
      // et « Changer les métadonnées » ne tiendrait plus).
      className={`group flex h-9 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left text-14 transition-[background-color,color,box-shadow] duration-150 ${
        actif
          ? "bg-surface text-fg shadow-[0_0_0_1px_var(--line),0_1px_2px_rgba(0,0,0,0.06)]"
          : "text-fg-2 hover:bg-fg/[0.05] hover:text-fg"
      }`}
    >
      {icone}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {badge}
    </button>
  );
}

export default function Sidebar({
  page,
  aller,
  theme,
  setTheme,
  pctMp4,
  nom,
  formule,
  licenceOk,
  connexion,
  transport,
  raison,
}: {
  page: Page;
  aller: (p: Page) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** pourcentage de la conversion en cours (null si rien ne tourne) */
  pctMp4: number | null;
  /** nom du détenteur de la licence (null = inconnu) */
  nom: string | null;
  formule: string;
  /** null = vérification en cours */
  licenceOk: boolean | null;
  connexion: EtatConnexion;
  /** « pont de dev », « sidecar »… */
  transport: string;
  raison: string | null;
}) {
  const [version, setVersion] = useState(__APP_VERSION__);
  useEffect(() => {
    versionApp().then(setVersion);
  }, []);

  // Sélecteur de thème = un groupe radio : UN seul arrêt de Tab (sur le choix actif),
  // puis les flèches changent de choix (comportement standard attendu au clavier).
  const radios = useRef<Record<Theme, HTMLButtonElement | null>>({ light: null, dark: null });
  const flecheTheme = (e: KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const autre: Theme = theme === "light" ? "dark" : "light";
    setTheme(autre);
    radios.current[autre]?.focus();
  };

  const moduleActif: CleModule | null = typeof page === "object" ? page.module : null;
  const ico = (actif: boolean) => `h-[18px] w-[18px] ${actif ? "text-brand-text" : "text-fg-3 group-hover:text-fg-2"}`;

  return (
    <aside className="flex w-[248px] shrink-0 flex-col px-3 pb-3 pt-4">
      {/* Marque */}
      <div className="flex items-center gap-2.5 px-2.5 pb-5">
        <img src={logo} alt="" className="h-7 w-7 drop-shadow-[0_4px_10px_rgba(76,111,255,0.35)]" />
        <span className="text-16 font-semibold tracking-[-0.02em]">HelpVA</span>
      </div>

      {/* Navigation */}
      <nav aria-label="Navigation principale" className="flex flex-col gap-0.5">
        <Lien
          actif={page === "accueil"}
          onClick={() => aller("accueil")}
          icone={<House weight={page === "accueil" ? "fill" : "regular"} className={ico(page === "accueil")} />}
        >
          Accueil
        </Lien>
        <Lien
          actif={page === "parametres"}
          onClick={() => aller("parametres")}
          icone={<GearSix weight={page === "parametres" ? "fill" : "regular"} className={ico(page === "parametres")} />}
        >
          Paramètres
        </Lien>
      </nav>

      <p className="mb-1.5 mt-6 px-2.5 text-11 font-medium uppercase tracking-[0.12em] text-fg-3">Modules</p>
      <nav aria-label="Modules" className="flex flex-col gap-0.5">
        {MODULES.map((m) => (
          <Lien
            key={m.cle}
            actif={moduleActif === m.cle}
            onClick={() => aller({ module: m.cle })}
            icone={<img src={m.icone} alt="" className="h-[18px] w-[18px] object-contain" />}
            badge={
              m.cle === "mp4" && pctMp4 !== null ? (
                <span className="tabular flex shrink-0 items-center gap-1 rounded-full bg-brand-soft px-1.5 py-px text-11 font-medium text-brand-text">
                  <span className="point-actif h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                  {pctMp4}&nbsp;%
                </span>
              ) : undefined
            }
          >
            {m.titre}
          </Lien>
        ))}
      </nav>

      <div className="flex-1" />

      {/* Carte utilisateur */}
      <button
        type="button"
        onClick={() => aller("parametres")}
        className="flex items-center gap-3 rounded-xl border border-line bg-surface/70 p-2.5 text-left shadow-card transition-colors duration-150 hover:border-line-2 dark:bg-white/[0.03]"
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[linear-gradient(140deg,var(--brand-2),var(--brand)_45%,var(--brand-deep))] text-12 font-semibold text-white shadow-[0_0_0_2px_var(--surface)]">
          {initiales(nom)}
        </span>
        <span className="min-w-0">
          <span id="sidebar-nom" className="block truncate text-13 font-medium">
            {nom ?? "HelpVA"}
          </span>
          <span className="flex items-center gap-1.5 text-12 text-fg-3">
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${licenceOk === null ? "bg-fg-3" : licenceOk ? "bg-success" : "bg-danger"}`}
              aria-hidden="true"
            />
            <span id="sidebar-formule" className="truncate">
              {formule}
            </span>
          </span>
        </span>
      </button>

      {/* Version, état du moteur, badge « Aperçu » (dev seulement), thème */}
      <div className="mt-3 flex items-center justify-between px-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="tabular text-12 text-fg-3">v{version}</span>
          <span
            id="etat-moteur"
            data-etat={connexion}
            title={
              connexion === "connecte"
                ? `Moteur Python connecté (${transport})`
                : connexion === "connexion"
                  ? "Connexion au moteur…"
                  : `Moteur non connecté : ${raison ?? "inconnu"}`
            }
            className="flex items-center gap-1 text-11 text-fg-3"
          >
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${
                connexion === "connecte" ? "bg-success" : connexion === "connexion" ? "point-actif bg-fg-3" : "bg-danger"
              }`}
            />
            {connexion === "connecte" ? "Moteur" : connexion === "connexion" ? "…" : import.meta.env.DEV ? "Démo" : "Arrêté"}
          </span>
          {import.meta.env.DEV && (
            <span
              title="Version de développement (npm run dev)"
              className="rounded-md border border-brand/20 bg-brand-soft px-1.5 py-0.5 text-11 font-medium text-brand-text"
            >
              Aperçu
            </span>
          )}
        </div>
        <div
          role="radiogroup"
          aria-label="Thème"
          className="relative flex rounded-lg border border-line bg-fg/[0.04] p-0.5"
        >
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
              onKeyDown={flecheTheme}
              aria-label={t === "light" ? "Thème clair" : "Thème sombre"}
              onClick={() => setTheme(t)}
              className={`relative z-10 grid h-6 w-6 place-items-center rounded-md transition-colors duration-150 ${
                theme === t ? "text-fg" : "text-fg-3 hover:text-fg-2"
              }`}
            >
              {t === "light" ? <Sun weight="bold" className="h-3.5 w-3.5" /> : <Moon weight="bold" className="h-3.5 w-3.5" />}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
