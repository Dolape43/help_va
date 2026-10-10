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
import calendrier from "./assets/icons/ranger.webp";

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
} as const;

export type NomIcone3D = keyof typeof ICONES_3D;
