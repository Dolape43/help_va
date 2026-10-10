import type { ReactNode } from "react";
import { FolderOpen, StopCircle, Warning } from "@phosphor-icons/react";
import { Bouton, Icone3D } from "../ui";
import { ICONES_3D } from "../../icones3d";

/**
 * Ce qui RESTE à l'écran après le traitement (la notification, elle, disparaît) :
 * le bilan en une phrase, d'éventuels fichiers en échec, et « Ouvrir le dossier ».
 */
export default function CarteResultat({
  id,
  arrete,
  titre,
  sousTitre,
  avertissement,
  details,
  sortie,
  ouvrirSortie,
}: {
  id: string;
  arrete: boolean;
  titre: string;
  sousTitre: string;
  /** fichiers illisibles, créneaux incomplets… (en orange, détail dans l'info-bulle) */
  avertissement?: { texte: string; detail?: string } | null;
  /** lignes supplémentaires (récapitulatif du rangement) */
  details?: ReactNode;
  sortie: string;
  ouvrirSortie: () => void;
}) {
  return (
    <div
      id={id}
      role="status"
      className={`entree mt-3 flex flex-wrap items-center gap-x-3.5 gap-y-3 rounded-2xl border p-4 ${
        arrete ? "border-line bg-surface" : "border-brand/25 bg-brand-soft"
      }`}
    >
      {arrete ? (
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-fg/[0.06] text-fg-2">
          <StopCircle weight="fill" className="h-5 w-5" aria-hidden="true" />
        </span>
      ) : (
        <Icone3D src={ICONES_3D.succes} taille={44} />
      )}
      <div className="min-w-[180px] flex-1">
        <p className="text-14 font-semibold">{titre}</p>
        <p className="truncate text-13 text-fg-2" title={sortie}>
          {sousTitre}
        </p>
        {avertissement && (
          <p className="mt-1 flex items-start gap-1.5 text-13 text-warning" title={avertissement.detail}>
            <Warning weight="fill" className="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="min-w-0">{avertissement.texte}</span>
          </p>
        )}
        {details}
      </div>
      <Bouton taille="sm" onClick={ouvrirSortie}>
        <FolderOpen className="h-4 w-4 text-fg-2" aria-hidden="true" />
        Ouvrir le dossier
      </Bouton>
    </div>
  );
}
