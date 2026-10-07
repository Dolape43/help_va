/**
 * affichage.ts — transforme les événements BRUTS du moteur en ce que les écrans affichent.
 *
 * Le moteur envoie des données (texte du journal, fraction, détails). Ici on décide seulement
 * de la PRÉSENTATION : quelle ligne est un titre de dossier, laquelle porte un chemin, etc.
 * Fonctions pures, sans React : faciles à relire et à tester.
 */
import type { ElementProgression, EvLog, EvProgress, GroupeProgression, NiveauLog } from "./protocole";

export type LigneJournal = {
  niveau: NiveauLog | "dossier" | "fichier";
  texte: string;
  /** chemin affiché sur sa propre ligne (lignes de fin « … → C:\…\media (mp4) ») */
  chemin?: string;
};

export type Progression = {
  /** 0 → 1 : progression GLOBALE (toutes les vidéos) */
  fraction: number;
  groupe: GroupeProgression | null;
  element: ElementProgression | null;
  /** texte exact du moteur (secours si `details` est absent) */
  texte: string;
  /** vidéos terminées / total (total connu grâce à « preparer ») */
  faites: number;
  total: number | null;
};

/** Ligne du journal à partir d'un événement « log » (null = ligne vide, ignorée). */
export function ligneDepuisLog(ev: EvLog): LigneJournal | null {
  const t = ev.texte.replace(/\s+$/, "");
  if (!t.trim()) return null; // print("\n✅ …") produit une ligne vide : inutile à l'écran
  // [convert] (1/4) clip_07.mov…  →  ligne « fichier » (mise en forme spéciale)
  if (ev.niveau === "info" && /^\[\w+\] \(\d+\/\d+\) /.test(t)) return { niveau: "fichier", texte: t };
  // Lignes de fin : « ✅ 4 vidéo(s) en .mp4 → C:\…\media (mp4) » : le chemin va sur sa propre ligne.
  if (ev.niveau === "succes" || ev.niveau === "arret") {
    const m = t.match(/^(.*?) → (.+)$/);
    const texte = (m ? m[1] : t).replace(/^✅\s*/, "");
    return { niveau: ev.niveau, texte, chemin: m?.[2] };
  }
  return { niveau: ev.niveau, texte: t };
}

/**
 * Le moteur n'écrit pas de ligne « Dossier 2/3 — Modèle A » dans le journal : elle n'existe que
 * dans la progression. On l'ajoute nous-mêmes quand le dossier change, pour que le journal se lise
 * par dossier (comme dans la maquette).
 */
export function ligneDossier(g: GroupeProgression): LigneJournal {
  return { niveau: "dossier", texte: `${g.mot} ${g.index}/${g.total}${g.nom ? ` — ${g.nom}` : ""}` };
}

export function progressionDepuis(ev: EvProgress, total: number | null): Progression {
  const fraction = ev.fraction ?? 0;
  // Le moteur calcule : fraction = (vidéos faites + pct / 100) / total. On retrouve « faites ».
  const faites = total ? Math.min(Math.floor(fraction * total + 1e-6), total) : 0;
  return {
    fraction,
    groupe: ev.details?.groupe ?? null,
    element: ev.details?.element ?? null,
    texte: ev.texte,
    faites,
    total,
  };
}

/** Les 2 lignes de la carte de progression, au format EXACT de l'ancienne app (noms complets). */
export function lignesProgression(p: Progression): [string, string] {
  const lignes = p.texte.split("\n");
  const g = p.groupe;
  const e = p.element;
  const l1 = g ? `${g.mot} ${g.index}/${g.total}${g.nom ? ` — ${g.nom}` : ""}` : !e && lignes.length > 1 ? lignes[0] : "";
  const l2 = e
    ? `${e.mot} ${e.index}/${e.total}${e.nom ? ` · ${e.nom}` : ""}${e.pct !== null ? ` — ${e.pct} %` : ""}`
    : lignes[lignes.length - 1];
  return [l1, l2];
}
