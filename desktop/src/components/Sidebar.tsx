import { useEffect, useState, type ReactNode } from "react";
import { ICONES_3D } from "../icones3d";
import SelecteurTheme from "./SelecteurTheme";
import BoutonSupport from "./BoutonSupport";
import logo from "../assets/logo.png";
import type { Activite, Page, Theme } from "../App";
import { versionApp } from "../plateforme";
import type { EtatConnexion } from "../engine/useMoteur";
import type { EssaiGratuit } from "../engine/api";
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
      className={`group flex h-10 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left text-14 transition-[background-color,color,box-shadow] duration-150 ${
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
  activite,
  nom,
  formule,
  licenceOk,
  horsLigne,
  essai,
  saisirCode,
  connexion,
  transport,
  raison,
}: {
  page: Page;
  aller: (p: Page) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** module qui travaille et son pourcentage (null si rien ne tourne) */
  activite: Activite;
  /** nom du détenteur de la licence (null = inconnu) */
  nom: string | null;
  formule: string;
  /** null = vérification en cours */
  licenceOk: boolean | null;
  /** licence valide, mais le serveur n'a pas pu la confirmer (toléré 6 heures) */
  horsLigne: boolean;
  /** offre gratuite en cours (null sinon) */
  essai: EssaiGratuit | null;
  /** ouvre l'écran du code d'activation */
  saisirCode: () => void;
  connexion: EtatConnexion;
  /** « pont de dev », « sidecar »… */
  transport: string;
  raison: string | null;
}) {
  const [version, setVersion] = useState(__APP_VERSION__);
  useEffect(() => {
    versionApp().then(setVersion);
  }, []);

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
          // Les modules s'ouvrent depuis l'Accueil : sur la page d'un module, « Accueil » reste actif.
          actif={page === "accueil" || typeof page === "object"}
          onClick={() => aller("accueil")}
          icone={<img src={ICONES_3D.accueil} alt="" className="h-6 w-6 object-contain" />}
          badge={
            activite ? (
              <span className="tabular flex shrink-0 items-center gap-1 rounded-full bg-brand-soft px-1.5 py-px text-11 font-medium text-brand-text">
                <span className="point-actif h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                {activite.pct}&nbsp;%
              </span>
            ) : undefined
          }
        >
          Accueil
        </Lien>
        <Lien
          actif={page === "parametres"}
          onClick={() => aller("parametres")}
          icone={<img src={ICONES_3D.parametres} alt="" className="h-6 w-6 object-contain" />}
        >
          Paramètres
        </Lien>
      </nav>


      <div className="flex-1" />

      {/* Offre gratuite : médias restants + « J'ai déjà une licence » */}
      {essai && (
        <div className="mb-2 rounded-xl border border-line bg-brand-soft/60 p-3">
          <p className="text-13 font-medium text-fg">Essai gratuit</p>
          <p className="tabular mt-0.5 text-12 text-fg-2">
            {essai.restant} sur {essai.quota} médias restants
          </p>
          <div
            className="mt-2 h-1.5 overflow-hidden rounded-full bg-fg/10"
            role="progressbar"
            aria-label="Médias gratuits restants"
            aria-valuemin={0}
            aria-valuemax={essai.quota}
            aria-valuenow={essai.restant}
          >
            <div
              className="h-full rounded-full bg-brand transition-[width] duration-300"
              style={{ width: `${essai.quota ? (100 * essai.restant) / essai.quota : 0}%` }}
            />
          </div>
          <button
            type="button"
            onClick={saisirCode}
            className="mt-2 text-12 font-medium text-brand-text hover:underline"
          >
            J'ai déjà une licence
          </button>
        </div>
      )}

      {/* Support : toujours là, en cas de blocage ou de problème */}
      <div className="mb-2">
        <BoutonSupport />
      </div>

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
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                licenceOk === null ? "bg-fg-3" : !licenceOk ? "bg-danger" : horsLigne ? "bg-warning" : "bg-success"
              }`}
              aria-hidden="true"
            />
            {/* Hors-ligne : point orange + info-bulle ici ; le texte « Hors-ligne » est en bas à droite. */}
            <span
              id="sidebar-formule"
              className="truncate"
              title={horsLigne ? "Hors-ligne : HelpVA réessaie de confirmer votre licence toutes les 5 minutes." : undefined}
            >
              {formule}
            </span>
          </span>
        </span>
      </button>

      {/* Version et thème. L'état du moteur n'apparaît QUE s'il y a un problème : quand tout va
          bien, ce détail technique ne dit rien à l'utilisateur. */}
      <div className="mt-3 flex items-center justify-between px-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="tabular text-12 text-fg-3" title={connexion === "connecte" ? `Connecté (${transport})` : undefined}>
            v{version}
          </span>
          {connexion === "non_connecte" && (
            <span title={`Moteur non connecté : ${raison ?? "inconnu"}`} className="flex items-center gap-1 text-11 text-danger">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-danger" />
              Arrêté
            </span>
          )}
        </div>
        <SelecteurTheme theme={theme} setTheme={setTheme} />
      </div>
    </aside>
  );
}
