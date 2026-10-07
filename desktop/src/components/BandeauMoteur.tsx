import { ArrowClockwise, PlugsConnected } from "@phosphor-icons/react";
import type { EtatConnexion } from "../engine/useMoteur";
import { Bouton } from "./ui";

/**
 * Bandeau « Moteur non connecté » : on ne laisse JAMAIS croire qu'une conversion simulée
 * est réelle. Affiché en haut des écrans tant que le vrai moteur Python n'est pas joignable.
 */
export default function BandeauMoteur({
  connexion,
  raison,
  reconnecter,
}: {
  connexion: EtatConnexion;
  raison: string | null;
  reconnecter: () => void;
}) {
  if (connexion !== "non_connecte") return null;
  return (
    <div
      role="status"
      id="bandeau-moteur"
      className="entree mb-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-danger/25 bg-danger/[0.06] px-4 py-3"
    >
      <PlugsConnected weight="duotone" className="h-5 w-5 shrink-0 text-danger" />
      <div className="min-w-[200px] flex-1">
        <p className="text-14 font-semibold">
          {import.meta.env.DEV ? "Moteur non connecté — mode démonstration" : "Le moteur de HelpVA n'a pas démarré"}
        </p>
        <p className="truncate text-12 text-fg-2" title={raison ?? undefined}>
          {import.meta.env.DEV ? (
            <>
              Lancez le pont : <code className="selectable font-mono">python engine/dev_bridge.py --sans-licence</code>
            </>
          ) : (
            "Cliquez sur « Réessayer ». Si le problème continue, réinstallez HelpVA."
          )}
        </p>
      </div>
      <Bouton taille="sm" onClick={reconnecter}>
        <ArrowClockwise className="h-4 w-4" />
        Réessayer
      </Bouton>
    </div>
  );
}
