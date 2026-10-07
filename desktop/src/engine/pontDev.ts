/**
 * pontDev.ts — transport de DÉVELOPPEMENT : le navigateur parle au vrai moteur Python
 * via engine/dev_bridge.py (HTTP + SSE), sans Rust ni Tauri.
 *
 *   React ──POST /cmd──────────▶ dev_bridge.py ──stdin──▶ helpva_engine.py
 *         ◀──GET /events (SSE)── dev_bridge.py ◀─stdout── helpva_engine.py
 *
 * Le jeton secret du pont :
 *   Le pont écrit un jeton dans engine/.dev_token à CHAQUE démarrage. On ne le met PAS dans le code
 *   ni dans une variable VITE_… (il serait figé au lancement de Vite et faux dès qu'on relance le pont).
 *   À la place, vite.config.ts ajoute une petite route de dev, /__helpva/jeton, qui relit le fichier
 *   à chaque demande. Cette route n'existe QUE dans `npm run dev` (jamais dans l'app livrée) et refuse
 *   les demandes venant d'un autre site.
 */
import { ErreurMoteur, estEvenement, type Evenement, type Requete } from "./protocole";
import type { FinTransport, Transport } from "./transport";

/** Adresse du pont (modifiable avec VITE_HELPVA_PONT dans desktop/.env.local). */
export const ADRESSE_PONT: string = import.meta.env.VITE_HELPVA_PONT || "http://127.0.0.1:8765";

/** Lit le jeton du pont via la route de dev de Vite. */
async function lireJeton(): Promise<string> {
  let rep: Response;
  try {
    rep = await fetch("/__helpva/jeton", { cache: "no-store" });
  } catch {
    throw new ErreurMoteur("NON_CONNECTE", "Serveur Vite injoignable.");
  }
  if (rep.status === 404) throw new ErreurMoteur("NON_CONNECTE", "Pont de dev non lancé (engine/.dev_token absent).");
  if (!rep.ok) throw new ErreurMoteur("NON_AUTORISE", `Jeton du pont illisible (HTTP ${rep.status}).`);
  const jeton = (await rep.text()).trim();
  if (!jeton) throw new ErreurMoteur("NON_CONNECTE", "Jeton du pont vide.");
  return jeton;
}

export class TransportPontDev implements Transport {
  readonly nom = "pont de dev";
  private jeton = "";
  private flux: EventSource | null = null;
  private ferme = false;

  async demarrer(recevoir: (ev: Evenement) => void, fin: (f: FinTransport) => void): Promise<void> {
    this.jeton = await lireJeton();

    // 1) Le pont répond-il, et accepte-t-il notre jeton ?
    let sante: Response;
    try {
      sante = await fetch(`${ADRESSE_PONT}/health`, { headers: { "X-HelpVA-Token": this.jeton }, cache: "no-store" });
    } catch {
      throw new ErreurMoteur("NON_CONNECTE", `Pont de dev injoignable sur ${ADRESSE_PONT}.`);
    }
    if (sante.status === 401 || sante.status === 403) throw new ErreurMoteur("NON_AUTORISE", "Le pont refuse le jeton ou l'origine.");
    if (!sante.ok) throw new ErreurMoteur("NON_CONNECTE", `Pont de dev : HTTP ${sante.status}.`);
    const etat = (await sante.json()) as { moteur_vivant?: boolean };
    if (!etat.moteur_vivant) throw new ErreurMoteur("MOTEUR_ARRETE", "Le pont tourne mais son moteur est arrêté : relancez le pont.");

    // 2) Le flux d'événements (SSE). EventSource ne sait pas envoyer d'en-tête : jeton dans l'URL.
    //    Le pont rejoue « pret » à chaque nouvelle connexion : le client le recevra donc toujours.
    await new Promise<void>((ouvert, echec) => {
      const es = new EventSource(`${ADRESSE_PONT}/events?token=${encodeURIComponent(this.jeton)}`);
      this.flux = es;
      let estOuvert = false;
      es.onopen = () => {
        estOuvert = true;
        ouvert();
      };
      es.onmessage = (m) => {
        let obj: unknown;
        try {
          obj = JSON.parse(m.data);
        } catch {
          console.warn("[pont] ligne illisible", m.data);
          return;
        }
        if (estEvenement(obj)) recevoir(obj);
      };
      // Toute coupure = fin du transport. On ne laisse PAS EventSource se reconnecter tout seul :
      // si le pont a été relancé, le jeton a changé. connexion.ts relance proprement (nouveau jeton).
      es.onerror = () => {
        es.close();
        if (this.ferme) return;
        this.ferme = true;
        if (!estOuvert) echec(new ErreurMoteur("NON_CONNECTE", "Flux d'événements du pont refusé."));
        else fin({ raison: "Connexion au pont de dev perdue." });
      };
    });
  }

  async envoyer(req: Requete): Promise<void> {
    if (this.ferme) throw new ErreurMoteur("MOTEUR_ARRETE", "Pont de dev déconnecté.");
    let rep: Response;
    try {
      rep = await fetch(`${ADRESSE_PONT}/cmd`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-HelpVA-Token": this.jeton },
        body: JSON.stringify(req),
      });
    } catch {
      throw new ErreurMoteur("MOTEUR_ARRETE", "Pont de dev injoignable.");
    }
    if (rep.status !== 202) {
      let corps: { code?: string; message?: string } = {};
      try {
        corps = await rep.json();
      } catch {
        /* corps vide */
      }
      throw new ErreurMoteur(corps.code || "MOTEUR_ARRETE", corps.message || `Pont de dev : HTTP ${rep.status}.`);
    }
  }

  async arreter(): Promise<void> {
    // On ferme seulement NOTRE connexion : le pont (et son moteur) appartient au terminal
    // du développeur, c'est lui qui l'arrête avec Ctrl+C.
    this.ferme = true;
    this.flux?.close();
    this.flux = null;
  }
}
