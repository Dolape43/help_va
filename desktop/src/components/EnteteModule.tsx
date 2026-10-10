import type { ReactNode } from "react";
import { ArrowLeft, CaretDown, Check } from "@phosphor-icons/react";
import { Bouton, TitrePage } from "./ui";
import type { ModuleDef } from "../modules";

/**
 * En-tête commun aux écrans de module :
 *   - fil d'Ariane (retour à l'accueil) ;
 *   - une carte avec la grande icône 3D du module, le titre, une phrase, et 3 points clés ;
 *   - « En savoir plus » : l'explication complète, repliée par défaut (la page reste aérée).
 */
export default function EnteteModule({
  mod,
  sousTitre,
  points,
  details,
  retour,
}: {
  mod: ModuleDef;
  sousTitre: string;
  /** 2 ou 3 points clés très courts (« HEIC iPhone lisible »…) */
  points?: string[];
  /** l'explication complète, dans « En savoir plus » */
  details?: ReactNode;
  retour: () => void;
}) {
  return (
    <>
      {/* Fil d'Ariane : le bouton et la page courante ont le même padding (8 px),
          donc le « / » est au milieu, à la même distance des deux mots. */}
      <nav aria-label="Fil d'Ariane" className="flex items-center text-13">
        <Bouton taille="sm" variante="fantome" onClick={retour} className="-ml-2 px-2">
          <ArrowLeft weight="bold" className="h-3.5 w-3.5" />
          Accueil
        </Bouton>
        <span className="px-1 text-fg-3" aria-hidden="true">
          /
        </span>
        <span className="truncate px-2 text-fg-2" aria-current="page">
          {mod.titre}
        </span>
      </nav>

      <header className="relative mt-3 overflow-hidden rounded-[20px] border border-line bg-surface p-5 shadow-card">
        {/* Lueur bleue derrière l'icône : le rappel discret de la marque. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -left-16 -top-20 h-64 w-64 rounded-full bg-[radial-gradient(circle,var(--glow),transparent_68%)]"
        />
        <div className="relative flex items-center gap-5">
          <span className="grid h-[76px] w-[76px] shrink-0 place-items-center rounded-[20px] border border-line bg-[linear-gradient(180deg,var(--surface-2),var(--surface))] shadow-[0_10px_30px_-18px_rgba(29,63,230,0.55)]">
            <img src={mod.icone} alt="" className="h-[58px] w-[58px] object-contain drop-shadow-[0_8px_14px_rgba(9,9,11,0.22)]" />
          </span>
          <div className="min-w-0">
            <TitrePage>{mod.titre}</TitrePage>
            <p className="mt-1 text-14 text-fg-2">{sousTitre}</p>
            {points && points.length > 0 && (
              <ul aria-label="Points clés" className="mt-3 flex flex-wrap gap-1.5">
                {points.map((p) => (
                  <li
                    key={p}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-12 text-fg-2"
                  >
                    <Check weight="bold" className="h-3 w-3 shrink-0 text-success-text" aria-hidden="true" />
                    {p}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        {details && (
          // <details> natif : ouvrable au clavier (Entrée / Espace) et annoncé par les lecteurs d'écran.
          <details className="group relative mt-4 border-t border-line pt-3">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-md text-13 font-medium text-brand-text hover:underline [&::-webkit-details-marker]:hidden">
              En savoir plus
              <CaretDown weight="bold" className="h-3 w-3 transition-transform duration-200 group-open:rotate-180" aria-hidden="true" />
            </summary>
            <div className="mt-2 max-w-[62ch] text-13 leading-relaxed text-fg-2">{details}</div>
          </details>
        )}
      </header>
    </>
  );
}
