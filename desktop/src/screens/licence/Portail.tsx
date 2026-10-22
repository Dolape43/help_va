import { useEffect, useState, type ReactNode } from "react";
import logo from "../../assets/logo.png";
import SelecteurTheme from "../../components/SelecteurTheme";
import { Icone3D, PastilleIcone, type Ton } from "../../components/ui";
import type { Theme } from "../../App";
import { versionApp } from "../../plateforme";
import { ILLUSTRATION_LICENCE } from "../../illustrations";

/**
 * Le « portail » : tout ce qui s'affiche AVANT l'application (vérification de la licence,
 * activation, connexion requise, bienvenue). Plein écran, sans barre latérale : tant que la
 * licence n'est pas réglée, il n'y a rien d'autre à faire.
 *
 * `ecran` sert de clé : changer d'écran rejoue l'animation d'entrée.
 */
export default function Portail({
  ecran,
  theme,
  setTheme,
  marque = true,
  children,
}: {
  ecran: string;
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** logo « HelpVA » en haut à gauche (inutile quand l'écran montre déjà le grand logo) */
  marque?: boolean;
  children: ReactNode;
}) {
  const [version, setVersion] = useState(__APP_VERSION__);
  useEffect(() => {
    versionApp().then(setVersion);
  }, []);

  return (
    <div className="fond-portail relative h-full">
      {/* La zone qui défile occupe TOUTE la fenêtre : l'ombre de la carte n'est pas coupée net
          au-dessus du pied de page. my-auto : centré verticalement s'il y a la place, sinon ça
          défile (justify-center couperait le haut de la carte sur un petit écran). */}
      <main className="scroll-fin absolute inset-0 z-10 flex flex-col overflow-y-auto px-6 pb-14 pt-16">
        <div key={ecran} className="entree my-auto flex w-full justify-center py-4">
          {children}
        </div>
      </main>
      <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex h-16 items-center gap-2.5 px-6">
        {marque && (
          <>
            <img src={logo} alt="" className="h-7 w-7 drop-shadow-[0_4px_10px_rgba(76,111,255,0.35)]" />
            <span className="text-16 font-semibold tracking-[-0.02em]">HelpVA</span>
          </>
        )}
      </header>
      <footer className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex h-14 items-center justify-between px-6">
        <span className="tabular text-12 text-fg-3">HelpVA v{version}</span>
        <div className="pointer-events-auto">
          <SelecteurTheme theme={theme} setTheme={setTheme} />
        </div>
      </footer>
    </div>
  );
}

/** La carte centrale des écrans de licence. */
/**
 * La colonne de gauche des écrans de licence : l'illustration (illustrations.ts), ou à défaut un
 * panneau aux couleurs de HelpVA. Décorative : masquée aux lecteurs d'écran, et cachée quand la
 * fenêtre est trop étroite (le formulaire passe avant).
 */
function PanneauVisuel() {
  if (ILLUSTRATION_LICENCE) {
    return (
      <div aria-hidden="true" className="relative hidden md:block">
        <img src={ILLUSTRATION_LICENCE} alt="" className="absolute inset-0 h-full w-full object-cover" />
      </div>
    );
  }
  return (
    // Fond noir, juste le logo assombri au centre. Rien ne bouge.
    <div aria-hidden="true" className="panneau-portail relative hidden place-items-center overflow-hidden md:grid">
      <img src={logo} alt="" className="relative h-[150px] w-[150px] object-contain opacity-40 brightness-75" />
    </div>
  );
}

/** La carte des écrans de licence : le visuel à gauche, le contenu (formulaire…) à droite. */
export function CartePortail({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`grid w-full max-w-[460px] overflow-hidden rounded-[24px] border border-line bg-surface shadow-pop md:max-w-[920px] md:grid-cols-[minmax(0,1fr)_460px] ${className}`}
    >
      <PanneauVisuel />
      <div className="px-8 py-7">{children}</div>
    </div>
  );
}

/** Icône + titre + phrase, centrés, en haut de la carte. */
export function EntetePortail({
  icone,
  image,
  ton,
  titre,
  texte,
}: {
  icone: ReactNode;
  /** icône 3D (voir icones3d.ts) : remplace la pastille si elle est donnée */
  image?: string;
  ton: Ton;
  titre: string;
  texte: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center text-center">
      {image ? (
        <Icone3D src={image} taille={88} />
      ) : (
        <PastilleIcone taille={52} ton={ton} className="rounded-2xl">
          {icone}
        </PastilleIcone>
      )}
      <h1 className="mt-5 text-20 font-semibold leading-tight">{titre}</h1>
      <p className="mt-2 max-w-[340px] text-14 leading-relaxed text-fg-2">{texte}</p>
    </div>
  );
}
