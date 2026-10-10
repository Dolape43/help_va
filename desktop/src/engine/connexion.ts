/**
 * connexion.ts — choisit le bon transport et se connecte au moteur.
 *
 *   Dans l'app Tauri          → sidecar (helpva-engine.exe). En dev, si l'exe manque, on essaie le pont.
 *   Dans le navigateur (dev)  → pont de dev (engine/dev_bridge.py, lancé par « npm run dev:moteur »).
 *   Rien ne répond            → moteur INDISPONIBLE : chaque action dit clairement que le moteur
 *                               n'a pas démarré (jamais de faux résultats). Bandeau bien visible.
 */
import { DANS_TAURI } from "../plateforme";
import { MoteurReel, type Moteur } from "./api";
import { ClientMoteur } from "./client";
import { ErreurMoteur } from "./protocole";
import { MoteurIndisponible } from "./indisponible";
import type { Transport } from "./transport";

export type Connexion = { moteur: Moteur; raison: string | null };

async function essayer(transport: Transport): Promise<Moteur> {
  const client = new ClientMoteur(transport);
  await client.connecter();
  return new MoteurReel(client);
}

export async function connecterMoteur(): Promise<Connexion> {
  const raisons: string[] = [];
  const noter = (e: unknown) => raisons.push(e instanceof ErreurMoteur ? e.message : String(e));

  if (DANS_TAURI) {
    // Import « à la demande » : le code du plugin shell n'est chargé que dans Tauri.
    const { TransportSidecar } = await import("./sidecar");
    try {
      return { moteur: await essayer(new TransportSidecar()), raison: null };
    } catch (e) {
      noter(e);
    }
  }
  // Le pont de dev n'existe QUE pendant le développement : `import.meta.env.DEV` vaut false
  // dans l'app livrée, et ce code disparaît alors du build.
  if (import.meta.env.DEV) {
    const { TransportPontDev } = await import("./pontDev");
    try {
      return { moteur: await essayer(new TransportPontDev()), raison: null };
    } catch (e) {
      noter(e);
    }
  }
  const raison = raisons.join(" · ") || "Aucun moteur disponible.";
  return { moteur: new MoteurIndisponible(raison), raison };
}
