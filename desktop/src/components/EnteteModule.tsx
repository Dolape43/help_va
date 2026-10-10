import { ArrowLeft } from "@phosphor-icons/react";
import { Bouton, TitrePage } from "./ui";
import type { ModuleDef } from "../modules";

/** En-tête commun aux écrans de module : fil d'Ariane + icône 3D + titre + phrase d'explication. */
export default function EnteteModule({
  mod,
  sousTitre,
  retour,
}: {
  mod: ModuleDef;
  sousTitre: string;
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

      <header className="mt-4 flex items-center gap-4">
        <img src={mod.icone} alt="" className="h-14 w-14 shrink-0 object-contain" />
        <div className="min-w-0">
          <TitrePage>{mod.titre}</TitrePage>
          <p className="mt-0.5 text-14 text-fg-2">{sousTitre}</p>
        </div>
      </header>
    </>
  );
}
