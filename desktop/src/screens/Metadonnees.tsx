import { useMemo } from "react";
import { FilmStrip } from "@phosphor-icons/react";
import ModuleTraitement, { type ConfigTraitement } from "./ModuleTraitement";
import type { PropsEcranTraitement } from "./ConvertirMp4";
import { Case } from "../components/ui";
import { moduleParCle } from "../modules";
import { fr, pluriel } from "../fr";

const s = (n: number) => (n > 1 ? "s" : "");
const nomDossier = (chemin: string) => chemin.split(/[\\/]/).filter(Boolean).pop() ?? chemin;

/** Changer les métadonnées : mêmes étapes que l'ancienne app (_page_metadonnees). */
export default function Metadonnees({
  renommer,
  setRenommer,
  ...props
}: PropsEcranTraitement & { renommer: boolean; setRenommer: (v: boolean) => void }) {
  const occupe = props.t.occupe;
  const config = useMemo<ConfigTraitement>(
    () => ({
      sousTitre: "Rendez chaque photo et vidéo unique, en 2 étapes simples.",
      info: fr(
        "Chaque média devient unique : nouvelles métadonnées et micro-variations invisibles à l'œil. Les photos iPhone HEIC / HEIF, qui ne s'affichent pas sur Instagram, sont aussi converties en .jpg automatiquement. Importez un dossier même avec des sous-dossiers : la structure est conservée. Vos fichiers originaux ne sont jamais modifiés.",
      ),
      source: {
        titre: "Choisir la source",
        sousTitre: "Un dossier entier, ou des images / vidéos précises.",
        boutonDossier: "Importer un dossier…",
        boutonFichiers: "Importer des images / vidéos…",
        iconeFichiers: FilmStrip,
        vide: "Aucune source pour l'instant : importez un dossier ou des images / vidéos.",
        resume: (src) =>
          src.source.type === "dossier"
            ? `Dossier · ${pluriel(src.nbMedias, "média")}, sous-dossiers compris`
            : `${pluriel(src.nbMedias, "média")} sélectionné${s(src.nbMedias)}`,
        alerte: (src) => (src.remplace ? `Le dossier « ${nomDossier(src.sortie)} » existe déjà : il sera remplacé.` : null),
      },
      options: {
        titre: "Options",
        sousTitre: "Un réglage, c'est tout.",
        contenu: (
          <Case
            coche={renommer}
            onChange={setRenommer}
            disabled={occupe}
            aide="Renumérote proprement les fichiers de sortie (recommandé)."
          >
            Renommer les médias (1, 2, 3…)
          </Case>
        ),
      },
      bouton: "Lancer",
      indication: "Résultat : un dossier « <votre dossier> (métadonnées changées) », même arborescence.",
      progression: {
        titre: "Changement des métadonnées…",
        enAttente: "Préparation des médias",
        unite: "médias",
        texteAnnulation: "HelpVA termine les fichiers en cours, puis s'arrête. Les médias déjà traités sont gardés.",
      },
      resultat: (r) => ({
        titre: r.arrete
          ? fr(`Arrêté : ${pluriel(r.traites, "média")} traité${s(r.traites)}`)
          : r.dossiers > 1
            ? `${pluriel(r.traites, "média")} rendu${s(r.traites)} unique${s(r.traites)} dans ${pluriel(r.dossiers, "dossier")}`
            : `${pluriel(r.traites, "média")} rendu${s(r.traites)} unique${s(r.traites)}`,
        sousTitre: r.arrete
          ? "Les médias déjà traités sont gardés."
          : r.dossiers > 1
            ? fr(`Même arborescence que votre dossier, dans « ${nomDossier(r.sortie)} ».`)
            : fr(`Dans « ${nomDossier(r.sortie)} ».`),
        avertissement: r.echecs.length
          ? {
              texte: fr(
                `${pluriel(r.echecs.length, "fichier")} non traité${s(r.echecs.length)} (illisible ou corrompu) : ${r.echecs.slice(0, 3).join(", ")}${r.echecs.length > 3 ? "…" : ""}`,
              ),
              detail: r.echecs.join("\n"),
            }
          : null,
      }),
      journalVide: "Le détail de chaque média s'affichera ici pendant le traitement.",
    }),
    [renommer, setRenommer, occupe],
  );
  return <ModuleTraitement mod={moduleParCle("metadonnees")} config={config} {...props} />;
}
