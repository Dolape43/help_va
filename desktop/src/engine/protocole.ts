/**
 * protocole.ts — le format des messages échangés avec le moteur Python (engine/helpva_engine.py).
 *
 * Référence complète : engine/README.md, section « Le protocole ».
 * En bref : UNE ligne JSON par message, dans les deux sens.
 *   interface → moteur : {"id":"c-3","cmd":"conversion_mp4","args":{...}}
 *   moteur → interface : {"id":"c-3","type":"progress"|"log"|"result"|"error", ...}
 *
 * Ce fichier ne contient QUE des types et de petites fonctions pures : aucune dépendance
 * à React, ni à Tauri, ni au navigateur. Il est donc facile à relire et à tester.
 */

/** Version du protocole que CETTE interface comprend (le moteur l'annonce dans « pret »). */
export const PROTOCOLE = 1;

/* ---------- Interface → moteur ---------- */

export type Requete = {
  /** Créé par l'interface (c-1, c-2…) et unique pour la session. */
  id: string;
  cmd: string;
  args: Record<string, unknown>;
};

/* ---------- Moteur → interface ---------- */

/** « Dossier 2/3 — Modèle A » : le groupe (null s'il n'y a qu'un seul dossier). */
export type GroupeProgression = { mot: string; index: number; total: number; nom: string | null };
/** « Vidéo 1/4 · clip_07.mov — 43 % » : l'élément en cours. */
export type ElementProgression = { mot: string; index: number; total: number; nom: string | null; pct: number | null };
/** Ranger avec plusieurs comptes : le compte en cours (rang parmi les comptes rangés, nom COMPLET). */
export type CompteProgression = { index: number; total: number; id: string; nom: string };

export type EvPret = {
  id: null;
  type: "pret";
  nom: string;
  version: string;
  protocole: number;
  pid: number;
  python: string;
  frozen: boolean;
};

export type EvProgress = {
  id: string | null;
  type: "progress";
  /** de 0 à 1, ou null si le moteur ne sait pas */
  fraction: number | null;
  /** le texte EXACT de l'ancienne app (2 lignes séparées par \n) */
  texte: string;
  details: { groupe: GroupeProgression | null; element: ElementProgression; compte?: CompteProgression | null } | null;
};

export type NiveauLog = "info" | "succes" | "arret" | "avertissement" | "erreur";

export type EvLog = {
  id: string | null;
  type: "log";
  flux: "stdout" | "stderr";
  niveau: NiveauLog;
  texte: string;
};

export type EvResult = { id: string | null; type: "result"; data: unknown };

export type EvError = {
  id: string | null;
  type: "error";
  code: string;
  message: string;
  details: unknown;
};

/** Envoyé par le pont de dev quand le processus moteur s'est arrêté. */
export type EvMoteurArrete = { id: null; type: "moteur_arrete"; code: number | null };

export type Evenement = EvPret | EvProgress | EvLog | EvResult | EvError | EvMoteurArrete;

/**
 * Erreur renvoyée par le moteur (événement « error ») ou détectée côté interface.
 * `code` permet à l'écran de réagir sans lire le message (ex. « SOURCE_VIDE »).
 *
 * Codes ajoutés côté interface : MOTEUR_ARRETE, DELAI_DEPASSE, PROTOCOLE_INCOMPATIBLE,
 * NON_AUTORISE (jeton du pont refusé), NON_CONNECTE (aucun moteur joignable),
 * TACHE_PERDUE (tâche longue que le moteur ne connaît plus, sans fin reçue).
 */
export class ErreurMoteur extends Error {
  code: string;
  details: unknown;
  constructor(code: string, message: string, details: unknown = null) {
    super(message);
    this.name = "ErreurMoteur";
    this.code = code;
    this.details = details;
  }
}

/** Vérifie (sans faire confiance) qu'un objet reçu ressemble à un événement. */
export function estEvenement(x: unknown): x is Evenement {
  if (typeof x !== "object" || x === null) return false;
  const o = x as Record<string, unknown>;
  return typeof o.type === "string" && (o.id === null || typeof o.id === "string" || o.id === undefined);
}

/**
 * Découpe un flux de texte en lignes JSON.
 *
 * Pourquoi c'est utile : selon le transport, on reçoit soit une ligne entière par morceau
 * (plugin shell de Tauri), soit des morceaux arbitraires. On garde donc un « reste » et on
 * n'analyse que les lignes complètes. Si un morceau arrive SANS « \n » final mais forme déjà
 * un JSON complet (cas du plugin shell qui retire parfois le retour à la ligne), on l'accepte.
 */
export class DecoupeurLignes {
  private reste = "";

  constructor(private readonly recevoir: (obj: unknown) => void, private readonly illisible: (ligne: string) => void) {}

  pousser(morceau: string) {
    this.reste += morceau;
    const lignes = this.reste.split("\n");
    this.reste = lignes.pop() ?? "";
    for (const l of lignes) this.analyser(l);
    // Morceau sans « \n » : on tente quand même (un objet JSON incomplet ne se lit pas,
    // donc aucun risque de couper un message en deux).
    if (this.reste.trim().startsWith("{")) {
      try {
        const obj = JSON.parse(this.reste);
        this.reste = "";
        this.recevoir(obj);
      } catch {
        /* incomplet : on attend la suite */
      }
    }
  }

  private analyser(ligne: string) {
    const l = ligne.replace(/\r$/, "").trim();
    if (!l) return;
    try {
      this.recevoir(JSON.parse(l));
    } catch {
      this.illisible(l);
    }
  }
}
