import images from "./assets/icons/images.webp";
import video from "./assets/icons/video.webp";
import metadonnees from "./assets/icons/metadonnees.webp";
import ranger from "./assets/icons/ranger.webp";

export type CleModule = "images" | "mp4" | "metadonnees" | "ranger";

export type ModuleDef = { cle: CleModule; titre: string; texte: string; icone: string };

/** Les 4 modules, avec les libellés de la vraie app (app_ctk.py) et les icônes 3D du site. */
export const MODULES: ModuleDef[] = [
  { cle: "images", titre: "Convertir les images", texte: "N'importe quelle image en .jpg ou .png", icone: images },
  { cle: "mp4", titre: "Convertir en MP4", texte: "Transforme .mov, .avi… en .mp4", icone: video },
  { cle: "metadonnees", titre: "Changer les métadonnées", texte: "Uniquifie vos photos et vidéos", icone: metadonnees },
  { cle: "ranger", titre: "Ranger les médias", texte: "Organise vos images et vidéos", icone: ranger },
];

export const moduleParCle = (cle: CleModule) => MODULES.find((m) => m.cle === cle)!;
