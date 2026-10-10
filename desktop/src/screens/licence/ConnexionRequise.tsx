import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Info, WifiSlash } from "@phosphor-icons/react";
import { Bouton, Rouage } from "../../components/ui";
import { CartePortail, EntetePortail } from "./Portail";
import type { StatutLicence } from "../../engine/api";

/** Nouvel essai automatique toutes les 20 s (comme app_ctk.py > _ecran_internet). */
const DELAI_S = 20;

/**
 * Hors-ligne depuis plus de 3 jours : HelpVA doit revoir le serveur avant de continuer.
 * Au démarrage du PC, internet met parfois quelques secondes : on réessaie tout seul,
 * avec un décompte visible, sans que l'utilisateur ait à cliquer.
 */
export default function ConnexionRequise({
  verifier,
  enCours,
}: {
  verifier: () => Promise<StatutLicence | null>;
  /** une vérification est en cours (la nôtre, ou celle du démarrage) */
  enCours: boolean;
}) {
  const [reste, setReste] = useState(DELAI_S);

  const essayer = useCallback(() => {
    setReste(DELAI_S);
    void verifier();
  }, [verifier]);

  // Décompte, mis en pause pendant une vérification. À zéro : nouvel essai, puis on recommence.
  useEffect(() => {
    if (enCours) return;
    if (reste <= 0) {
      essayer();
      return;
    }
    const id = setTimeout(() => setReste((r) => r - 1), 1000);
    return () => clearTimeout(id);
  }, [reste, enCours, essayer]);

  return (
    <CartePortail>
      <EntetePortail
        icone={<WifiSlash weight="duotone" className="h-6 w-6" />}
        ton="warning"
        titre="Connexion internet requise"
        texte="Veuillez vous connecter à internet, puis réessayez."
      />

      <p className="mt-6 flex gap-2.5 rounded-xl border border-line bg-surface-2 px-4 py-3 text-13 leading-relaxed text-fg-2">
        <Info weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-brand-text" aria-hidden="true" />
        <span>
          HelpVA confirme votre licence en ligne au moins une fois tous les 3 jours. Vos fichiers et vos réglages
          sont conservés.
        </span>
      </p>

      <Bouton
        variante="primaire"
        taille="lg"
        className="mt-6 w-full"
        onClick={() => !enCours && essayer()}
        aria-disabled={enCours || undefined}
        autoFocus
      >
        {enCours ? (
          <>
            <Rouage />
            Vérification…
          </>
        ) : (
          <>
            <ArrowClockwise weight="bold" className="h-4 w-4" aria-hidden="true" />
            Réessayer
          </>
        )}
      </Bouton>
      {/* Décompte : pas d'annonce aux lecteurs d'écran (une par seconde serait insupportable). */}
      <p className="tabular mt-3 text-center text-12 text-fg-3" aria-live="off">
        {enCours ? "Vérification de la connexion…" : `Nouvel essai automatique dans ${reste} s`}
      </p>
    </CartePortail>
  );
}
