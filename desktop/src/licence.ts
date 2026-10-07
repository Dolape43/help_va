/**
 * licence.ts — textes affichés à partir du statut de licence renvoyé par le moteur
 * (commande licence_statut = agent/licence.py > verifier()).
 */
import type { StatutLicence } from "./engine/api";

/** « Abonnement mensuel », « Licence à vie »… ou l'état si la licence n'est pas valide. */
export function libelleFormule(l: StatutLicence | null): string {
  if (!l) return "Vérification…";
  if (!l.ok) {
    return (
      {
        pas_active: "Licence non activée",
        expire: "Abonnement expiré",
        mauvais_pc: "Licence d'un autre PC",
        pas_internet: "Connexion requise",
        invalide: "Licence invalide",
        revoquee: "Licence révoquée",
        suspendu: "Licence suspendue",
      }[l.raison] ?? "Licence non valide"
    );
  }
  return { vie: "Licence à vie", mois: "Abonnement mensuel", an: "Abonnement annuel" }[l.type ?? "vie"] ?? "Licence active";
}

/** Nom du détenteur (champ « nom » de la licence), s'il existe. */
export function nomLicence(l: StatutLicence | null): string | null {
  const n = l?.nom?.trim();
  return n ? n : null;
}

/** « Agence Démo » → « AD » ; sans nom → « HV ». */
export function initiales(nom: string | null): string {
  if (!nom) return "HV";
  const mots = nom.split(/\s+/).filter(Boolean);
  return ((mots[0]?.[0] ?? "") + (mots[1]?.[0] ?? mots[0]?.[1] ?? "")).toUpperCase();
}

/** "2026-11-07" → « 7 novembre 2026 » */
export function dateLongue(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" }).format(d);
}
