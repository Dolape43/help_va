import { ArrowClockwise, WarningOctagon } from "@phosphor-icons/react";
import { Bouton, Rouage } from "../../components/ui";
import { CartePortail, EntetePortail } from "./Portail";
import { fr } from "../../fr";

/**
 * La licence n'a pas pu être vérifiée du tout (le moteur n'a pas démarré, erreur interne…).
 * On ne laisse pas entrer, mais on dit pourquoi et on propose de réessayer.
 */
export default function Panne({
  erreur,
  reessayer,
  enCours,
}: {
  erreur: string;
  reessayer: () => void;
  enCours: boolean;
}) {
  return (
    <CartePortail>
      <EntetePortail
        icone={<WarningOctagon weight="duotone" className="h-6 w-6" />}
        ton="danger"
        titre="HelpVA n'a pas pu vérifier votre licence"
        texte={<span className="selectable">{fr(erreur)}</span>}
      />
      <Bouton
        variante="primaire"
        taille="lg"
        className="mt-7 w-full"
        onClick={() => !enCours && reessayer()}
        aria-disabled={enCours || undefined}
        autoFocus
      >
        {enCours ? (
          <>
            <Rouage />
            Nouvelle tentative…
          </>
        ) : (
          <>
            <ArrowClockwise weight="bold" className="h-4 w-4" aria-hidden="true" />
            Réessayer
          </>
        )}
      </Bouton>
      <p className="mt-3 text-center text-12 text-fg-3">Si le problème continue, réinstallez HelpVA.</p>
    </CartePortail>
  );
}
