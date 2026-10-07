/**
 * indisponible.ts — ce que l'app LIVRÉE utilise quand le moteur Python ne démarre pas.
 *
 * Pourquoi pas la démonstration (simulation.ts) ? Parce qu'un client croirait que ses vidéos
 * ont été converties alors que rien n'a été fait. Ici, chaque action échoue avec un message
 * clair, et le bandeau « Le moteur de HelpVA n'a pas démarré » propose de réessayer.
 * La démonstration reste réservée au développement (voir moteurDeSecours).
 */
import type {
  EcouteursTache, FiltreFichiers, InfoMoteur, Moteur, Preparation, ResultatConversion,
  Source, StatutLicence, TacheEnCours, VueParametres,
} from "./api";
import type { EvLog } from "./protocole";
import { ErreurMoteur } from "./protocole";
import { MoteurSimule } from "./simulation";

export const MESSAGE_INDISPONIBLE =
  "Le moteur de HelpVA n'a pas démarré. Cliquez sur « Réessayer » ; si le problème continue, réinstallez HelpVA.";

export class MoteurIndisponible implements Moteur {
  readonly mode = "indisponible" as const;
  readonly transport = "aucun";

  constructor(private readonly raison: string | null = null) {}

  private erreur(): Promise<never> {
    return Promise.reject(new ErreurMoteur("MOTEUR_INDISPONIBLE", MESSAGE_INDISPONIBLE, { raison: this.raison }));
  }
  info(): Promise<InfoMoteur> { return this.erreur(); }
  licenceStatut(): Promise<StatutLicence> { return this.erreur(); }
  parametresLire(): Promise<VueParametres> { return this.erreur(); }
  parametresEcrire(_valeurs: Record<string, unknown>): Promise<VueParametres> { return this.erreur(); }
  dossierSortie(): Promise<{ chemin: string; defaut: string; personnalise: boolean }> { return this.erreur(); }
  ouvrirDossier(_chemin: string): Promise<void> { return this.erreur(); }
  choisirDossier(_titre?: string): Promise<string | null> { return this.erreur(); }
  choisirFichiers(_titre?: string, _filtre?: FiltreFichiers): Promise<string[]> { return this.erreur(); }
  preparer(_commande: "conversion_mp4", _args: { source: Source }): Promise<Preparation> { return this.erreur(); }
  convertirMp4(_source: Source, _ev: EcouteursTache): TacheEnCours<ResultatConversion> {
    return { resultat: this.erreur(), annuler: async () => {} };
  }
  surLogLibre(_f: ((ev: EvLog) => void) | null): void {}
  surDeconnexion(_f: ((raison: string) => void) | null): void {}
  async fermer(): Promise<void> {}
}

/**
 * Le moteur à utiliser quand le vrai moteur ne répond pas :
 *  - en DÉVELOPPEMENT : la démonstration (pratique pour travailler l'interface sans le pont) ;
 *  - dans l'app LIVRÉE : jamais de faux résultats, seulement des erreurs claires.
 * `import.meta.env.DEV` vaut false au build : la démonstration n'est jamais utilisée en production.
 */
export function moteurDeSecours(raison: string | null = null): Moteur {
  return import.meta.env.DEV ? new MoteurSimule() : new MoteurIndisponible(raison);
}
