import { useState } from "react";
import { X } from "@phosphor-icons/react";
import type { StatutLicence } from "../engine/api";
import { ICONES_3D } from "../icones3d";
import { lienVendeur, rappelFin } from "../licence";
import { Bouton, Icone3D } from "./ui";
import { fr } from "../fr";

/**
 * Les rappels de licence, en bas à droite, qui ne BLOQUENT jamais l'app :
 *  - fin d'abonnement (ou d'essai) demain / aujourd'hui, avec « Renouveler » (Telegram) ;
 *  - « Hors-ligne — reconnexion en cours… » quand le serveur n'a pas pu confirmer la licence
 *    (toléré 6 heures ; l'app revérifie toute seule toutes les 5 minutes).
 * Comme dans l'ancienne app (_montrer_rappel_fin, _montrer_bandeau_horsligne).
 */
export default function RappelsLicence({
  statut,
  ouvrirLien,
}: {
  statut: StatutLicence | null;
  ouvrirLien: (url: string) => void;
}) {
  // Rappel fermé : on ne le remontre qu'au changement de jour (sa clé contient les jours restants).
  const [ferme, setFerme] = useState<string | null>(null);
  const rappel = rappelFin(statut);
  const horsLigne = !!statut?.ok && !!statut.hors_ligne;

  return (
    <>
      {rappel && ferme !== rappel.cle && (
        <div
          role="status"
          className="toast pointer-events-auto relative w-[360px] overflow-hidden rounded-2xl border border-warning/30 bg-surface shadow-pop"
        >
          <div className="flex gap-3 p-4 pr-10">
            <Icone3D src={ICONES_3D.calendrier} taille={32} />
            <div className="min-w-0">
              <p className="text-14 font-semibold">{fr(rappel.titre)}</p>
              <p className="mt-0.5 text-13 leading-snug text-fg-2">{fr(rappel.texte)}</p>
              <Bouton taille="sm" variante="primaire" className="mt-3" onClick={() => ouvrirLien(lienVendeur(rappel.message))}>
                {rappel.action}
              </Bouton>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setFerme(rappel.cle)}
            aria-label="Fermer le rappel"
            className="absolute right-2.5 top-2.5 grid h-7 w-7 place-items-center rounded-lg text-fg-3 transition-colors duration-150 hover:bg-fg/[0.06] hover:text-fg"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      {horsLigne && (
        <p
          role="status"
          id="bandeau-hors-ligne"
          title="Le serveur n'a pas pu confirmer votre licence. HelpVA continue de fonctionner et réessaie toutes les 5 minutes."
          className="toast pointer-events-auto flex items-center gap-2 rounded-full border border-warning/30 bg-surface px-3.5 py-2 text-13 font-medium shadow-pop"
        >
          <span className="point-actif h-2 w-2 shrink-0 rounded-full bg-warning" aria-hidden="true" />
          {fr("Hors-ligne — reconnexion en cours…")}
        </p>
      )}
    </>
  );
}
