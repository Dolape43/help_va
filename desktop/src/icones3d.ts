/**
 * icones3d.ts — les icônes 3D de l'interface (style « dynamic color » de 3dicons.co, licence CC0,
 * comme les icônes des 4 modules). Réservées aux icônes BIEN VISIBLES (40 px et plus, ou à côté
 * des icônes de modules) : à 14–16 px, une icône 3D devient une tache floue, les petites
 * icônes de boutons restent donc dessinées au trait (Phosphor).
 *
 * Pour en ajouter une : PNG ou WebP à fond transparent dans assets/icons/3d/, puis l'importer ici.
 */
import dossier from "./assets/icons/3d/dossier.webp";
import succes from "./assets/icons/3d/succes.webp";
import cle from "./assets/icons/3d/cle.webp";
import bloque from "./assets/icons/3d/bloque.webp";
import ordinateur from "./assets/icons/3d/ordinateur.webp";
import soleil from "./assets/icons/3d/soleil.webp";
import lune from "./assets/icons/3d/lune.webp";
import parametres from "./assets/icons/3d/parametres.webp";
import ampoule from "./assets/icons/3d/ampoule.webp";
import expire from "./assets/icons/3d/expire.webp";
import licence from "./assets/icons/3d/licence.webp";
import alerte from "./assets/icons/3d/alerte.webp";
import accueil from "./assets/icons/3d/accueil.webp";
import crayon from "./assets/icons/3d/crayon.webp";
import telegram from "./assets/icons/3d/telegram.webp";
import chiffre1 from "./assets/icons/3d/chiffre-1.webp";
import chiffre2 from "./assets/icons/3d/chiffre-2.webp";
import chiffre3 from "./assets/icons/3d/chiffre-3.webp";
import chiffre4 from "./assets/icons/3d/chiffre-4.webp";
import chiffre1Clair from "./assets/icons/3d/chiffre-1-clair.webp";
import chiffre2Clair from "./assets/icons/3d/chiffre-2-clair.webp";
import chiffre3Clair from "./assets/icons/3d/chiffre-3-clair.webp";
import chiffre4Clair from "./assets/icons/3d/chiffre-4-clair.webp";
import calendrier from "./assets/icons/ranger.webp";
import bouclier from "./assets/icons/metadonnees.webp";

export const ICONES_3D = {
  /** dossier de sortie, source choisie, dossiers du Ranger */
  dossier,
  /** fin réussie d'un traitement */
  succes,
  /** activation de la licence */
  cle,
  /** licence résiliée ou suspendue */
  bloque,
  /** licence activée sur un autre PC */
  ordinateur,
  /** thème clair / sombre */
  soleil,
  lune,
  /** lien « Paramètres » de la barre latérale */
  parametres,
  /** carte « Conseil » de l'accueil */
  ampoule,
  /** abonnement expiré / essai terminé */
  expire,
  /** carte « Licence & abonnement » */
  licence,
  /** calendrier de posts (même image que le module Ranger) */
  calendrier,
  /** panneau attention : « Remplacer ? », résiliation, connexion requise, panne */
  alerte,
  /** « Vos originaux ne sont jamais modifiés » (même image que le module Métadonnées) */
  bouclier,
  /** lien « Accueil » de la barre latérale */
  accueil,
  /** boutons « Changer » (dossier de sortie) */
  crayon,
  /** Telegram (contacter le vendeur), même icône que sur le site */
  telegram,
} as const;

/**
 * Les chiffres 3D des étapes (1, 2, 3, 4). Gris foncé en thème clair ; en thème sombre, le foncé
 * disparaîtrait sur le fond : une version « argent » (même relief, plus claire) prend le relais.
 */
export const CHIFFRES_3D: Record<number, { fonce: string; clair: string }> = {
  1: { fonce: chiffre1, clair: chiffre1Clair },
  2: { fonce: chiffre2, clair: chiffre2Clair },
  3: { fonce: chiffre3, clair: chiffre3Clair },
  4: { fonce: chiffre4, clair: chiffre4Clair },
};

export type NomIcone3D = keyof typeof ICONES_3D;
