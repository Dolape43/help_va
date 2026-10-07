/**
 * transport.ts — « le tuyau » entre l'interface et le moteur.
 *
 * Le client (client.ts) ne sait PAS comment les messages voyagent. Il parle à un Transport :
 *   - TransportPontDev  (pontDev.ts)  : navigateur → HTTP/SSE → engine/dev_bridge.py → moteur.
 *                                       Sert pendant le développement, tant que Rust n'est pas installé.
 *   - TransportSidecar  (sidecar.ts)  : app Tauri → plugin shell → helpva-engine.exe (stdin/stdout).
 *                                       C'est la version finale.
 *
 * Pourquoi cette séparation : on peut changer de tuyau sans toucher au client ni aux écrans.
 */
import type { Evenement, Requete } from "./protocole";

export type FinTransport = {
  /** message lisible (« Le moteur s'est arrêté (code 1). ») */
  raison: string;
};

export interface Transport {
  /** Nom affiché à l'utilisateur / dans la console (« pont de dev », « sidecar »). */
  readonly nom: string;

  /**
   * Ouvre le tuyau. `recevoir` est appelé pour CHAQUE événement du moteur (y compris « pret »).
   * `fin` est appelé UNE fois si le tuyau se ferme tout seul (moteur arrêté, pont coupé…).
   * La promesse échoue si le tuyau ne peut pas s'ouvrir du tout (pont absent, sidecar introuvable).
   */
  demarrer(recevoir: (ev: Evenement) => void, fin: (f: FinTransport) => void): Promise<void>;

  /** Envoie une requête. Échoue si le tuyau est fermé. */
  envoyer(req: Requete): Promise<void>;

  /** Ferme proprement (demande au moteur de s'arrêter si c'est nous qui l'avons lancé). */
  arreter(): Promise<void>;
}
