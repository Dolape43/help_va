/**
 * indisponible.ts — ce que l'app utilise quand le moteur Python ne répond pas.
 *
 * Pas de « démonstration » qui ferait semblant : un client croirait que ses vidéos ont été
 * converties alors que rien n'a été fait. Ici, chaque action échoue avec un message clair,
 * et le bandeau du moteur propose de réessayer.
 */
import type { Moteur } from "./api";
import type { EvLog } from "./protocole";
import { ErreurMoteur } from "./protocole";

export const MESSAGE_INDISPONIBLE = import.meta.env.DEV
  ? "Moteur Python non connecté. Lancez « npm run dev:moteur » (ou python engine/dev_bridge.py --sans-licence), puis « Réessayer »."
  : "Le moteur de HelpVA n'a pas démarré. Cliquez sur « Réessayer » ; si le problème continue, réinstallez HelpVA.";

export class MoteurIndisponible implements Moteur {
  readonly mode = "indisponible" as const;
  readonly transport = "aucun";

  constructor(private readonly raison: string | null = null) {}

  private erreur(): Promise<never> {
    return Promise.reject(new ErreurMoteur("MOTEUR_INDISPONIBLE", MESSAGE_INDISPONIBLE, { raison: this.raison }));
  }
  private tache() {
    return { resultat: this.erreur(), annuler: async () => {} };
  }

  info() { return this.erreur(); }
  licenceStatut() { return this.erreur(); }
  licenceActiver() { return this.erreur(); }
  licenceResilier() { return this.erreur(); }
  parametresLire() { return this.erreur(); }
  parametresEcrire() { return this.erreur(); }
  dossierSortie() { return this.erreur(); }
  ouvrirDossier() { return this.erreur(); }
  choisirDossier() { return this.erreur(); }
  choisirFichiers() { return this.erreur(); }
  preparer() { return this.erreur(); }
  traiter() { return this.tache(); }
  calendrierLire() { return this.erreur(); }
  calendrierDefaut() { return this.erreur(); }
  calendrierSauver() { return this.erreur(); }
  comptesLire() { return this.erreur(); }
  comptesSauver() { return this.erreur(); }
  rangerAnalyser() { return this.erreur(); }
  rangerLancer() { return this.tache(); }
  surLogLibre(_f: ((ev: EvLog) => void) | null): void {}
  surDeconnexion(_f: ((raison: string) => void) | null): void {}
  async fermer(): Promise<void> {}
}
