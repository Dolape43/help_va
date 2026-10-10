/**
 * client.ts — le « standard téléphonique » entre les écrans et le moteur.
 *
 * Rôle :
 *   1. donner un id unique à chaque requête et RANGER sa promesse AVANT d'envoyer
 *      (un événement très rapide ne peut donc jamais arriver « avant » qu'on l'attende) ;
 *   2. distribuer les événements reçus à la bonne requête (progress, log, puis result OU error) ;
 *   3. vérifier la poignée de main « pret » (version du protocole) ;
 *   4. échouer proprement toutes les requêtes en attente si le moteur s'arrête.
 *
 * Il ne connaît pas le transport (pont de dev ou sidecar) : voir transport.ts.
 */
import {
  ErreurMoteur,
  PROTOCOLE,
  type EvLog,
  type EvPret,
  type EvProgress,
  type Evenement,
} from "./protocole";
import type { Transport } from "./transport";

export type Ecouteurs = {
  onProgress?: (ev: EvProgress) => void;
  onLog?: (ev: EvLog) => void;
};

type EnAttente = {
  resoudre: (data: unknown) => void;
  rejeter: (e: ErreurMoteur) => void;
  ecouteurs: Ecouteurs;
  minuteur?: ReturnType<typeof setTimeout>;
  /* Garde-fou des tâches longues (voir verifierTache) */
  surveillance?: ReturnType<typeof setInterval>;
  /** dernier événement reçu pour cette requête (Date.now()) */
  dernierSigne: number;
  /** nombre de vérifications de suite où le moteur ne connaissait plus la tâche */
  absences: number;
  verification: boolean;
};

/** Délai par défaut d'une commande RAPIDE. licence_statut peut durer ~40 s hors-ligne : on laisse de la marge. */
const DELAI_RAPIDE_MS = 60_000;
/**
 * Tâches longues : pas de délai (une conversion peut durer des heures). Mais si on n'a AUCUNE
 * nouvelle pendant ce temps, on demande « etat » au moteur pour vérifier qu'il travaille encore
 * dessus. Sans ça, une réponse perdue (ligne illisible…) laisserait l'écran « En cours » pour toujours.
 */
const SURVEILLANCE_MS = 20_000;
/** Délai pour recevoir « pret » après l'ouverture du tuyau (README du moteur : 20 s conseillées). */
const DELAI_PRET_MS = 20_000;

export class ClientMoteur {
  readonly transport: Transport;
  pret: EvPret | null = null;
  /** Journal « sans propriétaire » (id null ou inconnu) : plantage dur, messages du moteur… */
  onLogLibre: ((ev: EvLog) => void) | null = null;
  /** Appelé une fois si le moteur / le tuyau s'arrête. */
  onDeconnexion: ((raison: string) => void) | null = null;

  private enAttente = new Map<string, EnAttente>();
  // Préfixe aléatoire : le pont de dev diffuse les événements à TOUS les onglets ouverts.
  // Sans lui, deux onglets enverraient chacun « c-1 » et recevraient les réponses de l'autre.
  private prefixe = Math.random().toString(36).slice(2, 7);
  private compteur = 0;
  private attentePret: { ok: (p: EvPret) => void; ko: (e: ErreurMoteur) => void } | null = null;
  private deconnecte = false;

  constructor(transport: Transport) {
    this.transport = transport;
  }

  /** Ouvre le tuyau et attend « pret ». Échoue si le moteur est absent ou incompatible. */
  async connecter(): Promise<EvPret> {
    const pret = new Promise<EvPret>((ok, ko) => (this.attentePret = { ok, ko }));
    await this.transport.demarrer(
      (ev) => this.recevoir(ev),
      (f) => this.perdre(f.raison),
    );
    const delai = new Promise<never>((_, ko) =>
      setTimeout(() => ko(new ErreurMoteur("DELAI_DEPASSE", "Le moteur n'a pas répondu à temps (pas de « pret »).")), DELAI_PRET_MS),
    );
    try {
      return await Promise.race([pret, delai]);
    } catch (e) {
      await this.transport.arreter().catch(() => {});
      throw e;
    }
  }

  /**
   * Envoie une commande. Renvoie son id TOUT DE SUITE (utile pour l'annuler) et une promesse
   * qui se résout avec `data` (événement result) ou échoue avec une ErreurMoteur (événement error).
   *
   * @param delaiMs 0 = pas de limite (tâches longues, fenêtres de choix).
   * @param surveiller true pour une tâche LONGUE du moteur : garde-fou par « etat » (voir SURVEILLANCE_MS).
   */
  requete<T>(
    cmd: string,
    args: Record<string, unknown> = {},
    ecouteurs: Ecouteurs = {},
    delaiMs = DELAI_RAPIDE_MS,
    surveiller = false,
  ) {
    const id = `c-${this.prefixe}-${++this.compteur}`;
    const resultat = new Promise<T>((resoudre, rejeter) => {
      if (this.deconnecte) {
        rejeter(new ErreurMoteur("MOTEUR_ARRETE", "Le moteur est arrêté."));
        return;
      }
      const attente: EnAttente = {
        resoudre: resoudre as (d: unknown) => void,
        rejeter,
        ecouteurs,
        dernierSigne: Date.now(),
        absences: 0,
        verification: false,
      };
      if (delaiMs > 0) {
        attente.minuteur = setTimeout(() => {
          this.terminer(id);
          rejeter(new ErreurMoteur("DELAI_DEPASSE", `Pas de réponse du moteur pour « ${cmd} ».`, { cmd }));
        }, delaiMs);
      }
      if (surveiller) attente.surveillance = setInterval(() => void this.verifierTache(id, cmd), SURVEILLANCE_MS);
      // On RANGE la promesse avant d'envoyer (voir l'en-tête du fichier).
      this.enAttente.set(id, attente);
      this.transport.envoyer({ id, cmd, args }).catch((e: unknown) => {
        this.terminer(id);
        rejeter(e instanceof ErreurMoteur ? e : new ErreurMoteur("MOTEUR_ARRETE", String(e)));
      });
    });
    return { id, resultat };
  }

  /** Raccourci : envoie et attend le résultat. */
  appeler<T>(cmd: string, args: Record<string, unknown> = {}, ecouteurs: Ecouteurs = {}, delaiMs = DELAI_RAPIDE_MS): Promise<T> {
    return this.requete<T>(cmd, args, ecouteurs, delaiMs).resultat;
  }

  /**
   * Garde-fou d'une tâche longue sans nouvelles : le moteur travaille-t-il encore dessus ?
   * Il faut DEUX réponses « non » de suite (à 20 s d'écart) pour abandonner : juste à la fin
   * d'une tâche, le moteur libère la place un instant AVANT d'envoyer le résultat, donc un
   * seul « non » peut être un faux négatif.
   */
  private async verifierTache(id: string, cmd: string) {
    const a = this.enAttente.get(id);
    if (!a || a.verification || Date.now() - a.dernierSigne < SURVEILLANCE_MS) return;
    a.verification = true;
    try {
      const e = await this.appeler<{ tache: { id: string } | null }>("etat", {}, {}, 15_000);
      if (!this.enAttente.has(id)) return; // la tâche a fini entre-temps
      if (e.tache?.id === id) {
        a.absences = 0;
        return;
      }
      a.absences += 1;
      if (a.absences >= 2) {
        this.terminer(id);
        a.rejeter(new ErreurMoteur("TACHE_PERDUE", `Le moteur ne connaît plus cette tâche (« ${cmd} ») : aucune fin reçue.`));
      }
    } catch {
      /* moteur injoignable : perdre() rejette déjà toutes les requêtes */
    } finally {
      a.verification = false;
    }
  }

  /** Annule une tâche longue (idempotent, comme côté moteur). */
  annuler(id: string) {
    return this.appeler<{ etat: string }>("annuler", { cible: id });
  }

  async fermer() {
    // Tâches longues en cours : on demande leur annulation. Avec le pont de dev, le moteur survit
    // à la page (rechargement, onglet fermé) : sans ça, une conversion continuerait sans personne
    // pour la suivre. (Avec le sidecar, « quitter » les annule de toute façon.)
    for (const [id, attente] of this.enAttente) {
      if (attente.surveillance) {
        this.transport.envoyer({ id: `ui-annuler-${id}`, cmd: "annuler", args: { cible: id } }).catch(() => {});
      }
    }
    this.deconnecte = true;
    this.echouerTout("Interface fermée.");
    await this.transport.arreter();
  }

  /* ---------- réception ---------- */

  private recevoir(ev: Evenement) {
    if (ev.type === "pret") {
      this.pret = ev;
      if (ev.protocole !== PROTOCOLE) {
        this.attentePret?.ko(
          new ErreurMoteur(
            "PROTOCOLE_INCOMPATIBLE",
            `Moteur (protocole ${ev.protocole}) et interface (protocole ${PROTOCOLE}) incompatibles : réinstallez HelpVA.`,
          ),
        );
      } else {
        this.attentePret?.ok(ev);
      }
      this.attentePret = null;
      return;
    }
    if (ev.type === "moteur_arrete") {
      this.perdre(`Le moteur s'est arrêté (code ${ev.code ?? "?"}).`);
      return;
    }

    const attente = ev.id ? this.enAttente.get(ev.id) : undefined;
    if (!attente) {
      // Événement d'une autre session (autre onglet sur le pont) ou sans id.
      if (ev.type === "log" && (ev.id === null || ev.id.startsWith("ui-"))) this.onLogLibre?.(ev);
      else if (ev.type === "error" && ev.id === null) console.warn("[moteur] erreur sans requête :", ev.code, ev.message);
      return;
    }
    attente.dernierSigne = Date.now(); // signe de vie (garde-fou des tâches longues)
    switch (ev.type) {
      case "progress":
        attente.ecouteurs.onProgress?.(ev);
        break;
      case "log":
        attente.ecouteurs.onLog?.(ev);
        break;
      case "result":
        this.terminer(ev.id!);
        attente.resoudre(ev.data);
        break;
      case "error":
        this.terminer(ev.id!);
        attente.rejeter(new ErreurMoteur(ev.code, ev.message, ev.details));
        break;
    }
  }

  private terminer(id: string) {
    const a = this.enAttente.get(id);
    if (a?.minuteur) clearTimeout(a.minuteur);
    if (a?.surveillance) clearInterval(a.surveillance);
    this.enAttente.delete(id);
  }

  private echouerTout(raison: string) {
    for (const [id, a] of this.enAttente) {
      this.terminer(id);
      a.rejeter(new ErreurMoteur("MOTEUR_ARRETE", raison));
    }
  }

  private perdre(raison: string) {
    if (this.deconnecte) return;
    this.deconnecte = true;
    this.attentePret?.ko(new ErreurMoteur("MOTEUR_ARRETE", raison));
    this.attentePret = null;
    this.echouerTout(raison);
    this.onDeconnexion?.(raison);
  }
}
