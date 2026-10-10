import type { ReactNode } from "react";
import ModuleTraitement, { type ConfigTraitement } from "./ModuleTraitement";
import { moduleParCle } from "../modules";
import type { Traitement } from "../engine/useTraitement";
import { fr, pluriel } from "../fr";

export type PropsEcranTraitement = {
  t: Traitement;
  occupeAilleurs: string | null;
  bandeau: ReactNode;
  retour: () => void;
  ouvrirDossier: (chemin: string) => void;
};

const s = (n: number) => (n > 1 ? "s" : "");

/** Convertir en MP4 : mêmes textes que l'ancienne app (app_ctk.py > _page_convertir). */
const CONFIG: ConfigTraitement = {
  sousTitre: "Transforme vos vidéos (.mov, .avi, .mkv…) en .mp4.",
  points: ["Rapide quand c'est possible", "Compatible partout (H.264)", "Originaux intacts"],
  mot: "vidéo",
  feminin: true,
  info: fr(
    "HelpVA crée une version .mp4 de chaque vidéo dans « media (mp4) ». Rapide quand c'est possible (il change juste le conteneur), sinon ré-encodage automatique (H.264/AAC) pour que ça marche à coup sûr. Vos originaux ne sont pas touchés.",
  ),
  source: {
    titre: "Choisir les vidéos",
    sousTitre: "Un dossier entier, ou des vidéos précises.",
    boutonDossier: "Importer un dossier…",
    boutonFichiers: "Importer des vidéos…",
    aideFichiers: "Seulement les vidéos que vous choisissez",
    resume: (src) =>
      src.source.type === "dossier"
        ? `Dossier · ${pluriel(src.nbMedias, "vidéo")}, sous-dossiers compris`
        : `${pluriel(src.nbMedias, "vidéo")} sélectionnée${s(src.nbMedias)}`,
    // ffmpeg écrase sans prévenir : on le dit AVANT de lancer.
    alerte: (src) =>
      src.dejaPresents > 0
        ? `${pluriel(src.dejaPresents, "vidéo")} déjà dans « media (mp4) » : ${src.dejaPresents > 1 ? "elles seront remplacées" : "elle sera remplacée"}.`
        : null,
  },
  bouton: "Convertir",
  indication: "Résultat dans « media (mp4) ». La conversion peut être longue selon les vidéos.",
  progression: {
    titre: "Conversion en cours…",
    enAttente: "Conversion des vidéos",
    unite: "vidéos",
    texteAnnulation: "HelpVA arrête la vidéo en cours et supprime le fichier incomplet.",
    annonceParFichier: true,
  },
  resultat: (r) => ({
    titre: r.arrete
      ? fr(`Arrêté : ${pluriel(r.traites, "vidéo")} convertie${s(r.traites)}`)
      : r.dossiers > 1
        ? `${pluriel(r.traites, "vidéo")} convertie${s(r.traites)} dans ${pluriel(r.dossiers, "dossier")}`
        : `${pluriel(r.traites, "vidéo")} convertie${s(r.traites)}`,
    sousTitre: r.arrete
      ? "Le fichier incomplet a été supprimé."
      : r.dossiers > 1
        ? "Même arborescence que votre dossier."
        : fr("Dans « media (mp4) »."),
    avertissement: r.echecs.length
      ? {
          texte: fr(`${pluriel(r.echecs.length, "fichier")} non converti${s(r.echecs.length)} (vide ou corrompu) : ${r.echecs.slice(0, 3).join(", ")}${r.echecs.length > 3 ? "…" : ""}`),
          detail: r.echecs.join("\n"),
        }
      : null,
  }),
  journalVide: "Le détail de chaque vidéo s'affichera ici pendant la conversion.",
};

export default function ConvertirMp4(props: PropsEcranTraitement) {
  return <ModuleTraitement mod={moduleParCle("mp4")} config={CONFIG} {...props} />;
}
