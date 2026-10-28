/**
 * licence.ts — ce que l'interface affiche à partir du statut de licence renvoyé par le moteur
 * (commande licence_statut = agent/licence.py > verifier()).
 *
 * Les textes reprennent ceux de l'ancienne app (app_ctk.py : _ecran_activation, _ecran_internet,
 * _texte_rappel_fin…), pour que les clients retrouvent les mêmes messages.
 */
import type { StatutLicence } from "./engine/api";
import type { EtatConnexion } from "./engine/useMoteur";

/** Le canal Telegram du vendeur (agent/config.py > TELEGRAM_LICENCE). */
export const LIEN_VENDEUR = "https://t.me/helpvaLicence";

/** Lien Telegram avec un message déjà écrit (comme _contacter_licence dans app_ctk.py). */
export function lienVendeur(message: string): string {
  return `${LIEN_VENDEUR}?text=${encodeURIComponent(message)}`;
}

export const MESSAGES_VENDEUR = {
  code: "Bonjour 👋\nJe souhaite obtenir un code d'activation HelpVA.",
  renouveler: "Bonjour 👋\nJe souhaite renouveler ma licence HelpVA.",
  essai: "Bonjour 👋\nMon essai HelpVA se termine, je souhaite obtenir une licence.",
  suspendu: "Bonjour 👋\nMa licence HelpVA est suspendue. Pouvez-vous m'aider ?",
  support: "Bonjour 👋\nJ'ai besoin d'aide avec HelpVA.",
};

/* ---------- Quel écran montrer ? ---------- */

export type EcranLicence = "verification" | "panne" | "activation" | "connexion" | "bienvenue" | "app";

/**
 * Le « portail » d'entrée de l'app (même ordre que app_ctk.py > _router_licence) :
 *   licence pas encore connue      → « Vérification de votre licence… »
 *   vérification impossible        → « HelpVA n'a pas pu vérifier votre licence » + Réessayer
 *   hors-ligne depuis plus de 6 h  → « Connexion internet requise »
 *   pas de licence, essai restant  → l'application (offre gratuite)
 *   essai fini, licence bloquée    → écran d'activation (titre selon la raison)
 *   tout premier lancement         → « Bienvenue sur HelpVA »
 *   sinon                          → l'application
 */
export function ecranLicence(o: {
  statut: StatutLicence | null;
  erreur: string | null;
  enCours: boolean;
  connexion: EtatConnexion;
  /** null = paramètres pas encore lus */
  premierLancement: boolean | null;
  /** DEV : pont lancé avec --sans-licence → la licence n'est pas exigée (jamais dans l'app livrée) */
  contournee?: boolean;
  /** DEV : faux tant que `info` (qui dit si la licence est contournée) n'est pas arrivée */
  infoPrete?: boolean;
}): EcranLicence {
  if (o.infoPrete === false) return "verification";
  if (!o.statut) return o.erreur && !o.enCours && o.connexion !== "connexion" ? "panne" : "verification";
  if (!o.statut.ok && !o.contournee) return o.statut.raison === "pas_internet" ? "connexion" : "activation";
  if (o.premierLancement === null) return "verification";
  return o.premierLancement ? "bienvenue" : "app";
}

/* ---------- Écran d'activation : titre et texte selon la raison ---------- */

export type Blocage = {
  titre: string;
  texte: string;
  /** couleur de la pastille */
  ton: "brand" | "warning" | "danger";
  /** bouton « Abonnement réactivé ? Réessayer » : seulement si le vendeur peut débloquer sans
   *  nouveau code (licence résiliée ou suspendue côté serveur) */
  reessayer: boolean;
  /** message Telegram prérempli pour « Contacter le vendeur » */
  message: string;
};

export function blocage(raison: string, type: string | null = null): Blocage {
  switch (raison) {
    case "expire":
      // La date de fin est SIGNÉE dans la licence : une revérification ne peut pas la repousser,
      // seul un nouveau code le peut. Donc pas de « Réessayer » ici.
      if (type === "essai") {
        return {
          titre: "Essai gratuit terminé",
          texte: "Votre essai gratuit est terminé. Entrez un code d'activation pour continuer.",
          ton: "warning",
          reessayer: false,
          message: MESSAGES_VENDEUR.essai,
        };
      }
      return {
        titre: "Abonnement expiré",
        texte: "Votre abonnement a expiré. Entrez un nouveau code pour le renouveler.",
        ton: "warning",
        reessayer: false,
        message: MESSAGES_VENDEUR.renouveler,
      };
    case "revoquee":
      return {
        titre: "Licence résiliée",
        texte: "Cette licence a été résiliée. Entrez un nouveau code fourni par le vendeur.",
        ton: "danger",
        reessayer: true,
        message: MESSAGES_VENDEUR.code,
      };
    case "suspendu":
      return {
        titre: "Licence suspendue",
        texte: "Cette licence est suspendue. Contactez le vendeur.",
        ton: "warning",
        reessayer: true,
        message: MESSAGES_VENDEUR.suspendu,
      };
    case "mauvais_pc":
      return {
        titre: "Licence d'un autre PC",
        texte: "Cette licence a été activée sur un autre ordinateur. Entrez un code d'activation pour ce PC.",
        ton: "warning",
        reessayer: false,
        message: MESSAGES_VENDEUR.code,
      };
    case "invalide":
      return {
        titre: "Licence illisible",
        texte: "Le fichier de licence de ce PC est abîmé. Entrez un code d'activation fourni par le vendeur.",
        ton: "danger",
        reessayer: false,
        message: MESSAGES_VENDEUR.code,
      };
    case "essai_fini":
      return {
        titre: "Essai gratuit terminé",
        texte: "Vos médias gratuits sont utilisés. Entrez un code d'activation pour continuer.",
        ton: "warning",
        reessayer: false,
        message: MESSAGES_VENDEUR.essai,
      };
    case "essai_gratuit":
      // « J'ai déjà une licence » pendant l'offre gratuite.
      return {
        titre: "Entrer un code d'activation",
        texte: "Vous avez déjà une licence ? Entrez votre code : elle remplace l'essai gratuit.",
        ton: "brand",
        reessayer: false,
        message: MESSAGES_VENDEUR.code,
      };
    default: // "pas_active" (ou une raison inconnue)
      return {
        titre: "Activer HelpVA",
        texte: "Entrez le code d'activation fourni par le vendeur.",
        ton: "brand",
        reessayer: false,
        message: MESSAGES_VENDEUR.code,
      };
  }
}

/**
 * Code tapé ou collé → forme envoyée au serveur : majuscules, sans espaces.
 * On ne « corrige » rien d'autre : c'est le serveur qui dit si le code existe.
 */
export function normaliserCode(code: string): string {
  // Le tiret ajouté tout seul en fin de groupe (« HELP-ABCD- ») ne part pas au serveur.
  return code.replace(/\s+/g, "").toUpperCase().replace(/-+$/, "");
}

/** Un code fait 16 caractères utiles (HELP + 3 × 4), en groupes de 4 : HELP-XXXX-XXXX-XXXX. */
const UTILES_MAX = 16;
const nonUtile = /[^A-Z0-9]/gi;

/**
 * Mise en forme PENDANT la saisie : majuscules, tirets placés tout seuls tous les 4 caractères,
 * le reste (espaces, tirets tapés à la main, accents…) retiré. Coller « help abcd efgh jkmn »
 * donne donc « HELP-ABCD-EFGH-JKMN ».
 * Le tiret apparaît DÈS le 4e caractère d'un groupe (« HELP » → « HELP- »), sauf à la toute fin
 * du code. (Retour arrière juste après ce tiret efface aussi le caractère d'avant : voir Activation.)
 */
export function formaterCode(saisie: string): string {
  const utiles = saisie.replace(nonUtile, "").toUpperCase().slice(0, UTILES_MAX);
  const groupes = utiles.match(/.{1,4}/g) ?? [];
  const groupeComplet = utiles.length > 0 && utiles.length % 4 === 0 && utiles.length < UTILES_MAX;
  return groupes.join("-") + (groupeComplet ? "-" : "");
}

/** Nombre de caractères utiles (lettres et chiffres) dans un morceau de saisie. */
export const nbUtiles = (texte: string) => texte.replace(nonUtile, "").length;

/**
 * Où remettre le curseur dans le code mis en forme : juste après le même nombre de caractères
 * utiles qu'avant la mise en forme. Sans ça, ajouter un tiret enverrait le curseur à la fin.
 */
export function positionCurseur(codeFormate: string, utilesAvant: number): number {
  if (utilesAvant <= 0) return 0;
  let n = 0;
  for (let i = 0; i < codeFormate.length; i++) {
    if (codeFormate[i] !== "-" && ++n === utilesAvant) return i + 1;
  }
  return codeFormate.length;
}

/* ---------- Rappel de fin d'abonnement (la veille et le jour même) ---------- */

export type RappelFin = { titre: string; texte: string; action: string; message: string; cle: string };

/** Comme _texte_rappel_fin : seulement si l'abonnement (ou l'essai) finit demain ou aujourd'hui. */
export function rappelFin(st: StatutLicence | null): RappelFin | null {
  const j = st?.jours_restants;
  if (!st?.ok || j === null || j === undefined || j < 0 || j > 1) return null;
  if (st.type !== "mois" && st.type !== "an" && st.type !== "essai") return null;
  const quand = j === 1 ? "demain" : "aujourd'hui";
  // Fermé par l'utilisateur : on ne le remontre qu'au changement de jour (même clé que l'ancienne app).
  const cle = `${st.expire_le}|${j}`;
  if (st.type === "essai") {
    return {
      titre: `Votre essai gratuit se termine ${quand}`,
      texte: "Choisissez une offre pour continuer.",
      action: "Choisir une offre",
      message: MESSAGES_VENDEUR.essai,
      cle,
    };
  }
  return {
    titre: `Votre abonnement se termine ${quand}`,
    texte: "Renouvelez-le pour continuer sans interruption.",
    action: "Renouveler",
    message: MESSAGES_VENDEUR.renouveler,
    cle,
  };
}

/* ---------- Libellés ---------- */

const FORMULES: Record<string, string> = {
  vie: "Licence à vie",
  mois: "Abonnement mensuel",
  an: "Abonnement annuel",
  essai: "Essai gratuit",
};

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
        invalide: "Licence illisible",
        revoquee: "Licence résiliée",
        suspendu: "Licence suspendue",
        essai_fini: "Essai gratuit terminé",
      }[l.raison] ?? "Licence non valide"
    );
  }
  if (l.type === "gratuit") return `Essai gratuit · ${restantEssai(l)}`;
  return FORMULES[l.type ?? "vie"] ?? "Licence active";
}

/** « 12 médias restants » (offre gratuite). */
export function restantEssai(l: StatutLicence): string {
  const n = l.essai?.restant ?? 0;
  return n > 1 ? `${n} médias restants` : `${n} média restant`;
}

/** « Licence à vie » · « Abonnement mensuel, jusqu'au 7 novembre 2026 » (écran de bienvenue). */
export function resumeLicence(l: StatutLicence): string {
  const formule = libelleFormule(l);
  const fin = l.type !== "vie" ? dateLongue(l.expire_le) : null;
  return fin ? `${formule}, jusqu'au ${fin}` : formule;
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
