import { useMemo } from "react";
import ModuleTraitement, { type ConfigTraitement } from "./ModuleTraitement";
import type { PropsEcranTraitement } from "./ConvertirMp4";
import { Case, Segments } from "../components/ui";
import { moduleParCle } from "../modules";
import { fr, pluriel } from "../fr";

export type FormatImage = "jpg" | "png";

const s = (n: number) => (n > 1 ? "s" : "");
const nomDossier = (chemin: string) => chemin.split(/[\\/]/).filter(Boolean).pop() ?? chemin;

/** Convertir les images (JPG / PNG) : mêmes textes que l'ancienne app (_page_convertir_images). */
export default function ConvertirImages({
  format,
  setFormat,
  renommer,
  setRenommer,
  ...props
}: PropsEcranTraitement & { format: FormatImage; setFormat: (f: FormatImage) => void; renommer: boolean; setRenommer: (v: boolean) => void }) {
  const occupe = props.t.occupe;
  const config = useMemo<ConfigTraitement>(
    () => ({
      sousTitre: "Convertit n'importe quel type d'image en .jpg ou .png.",
      mot: "image",
      feminin: true,
      info: fr(
        "Convertit chaque image au format choisi (.jpg ou .png). Les photos iPhone HEIC / HEIF, qui ne s'affichent pas sur les réseaux sociaux, deviennent lisibles. Les images des sous-dossiers sont aussi converties, toutes dans le même dossier. Vos fichiers originaux ne sont jamais modifiés.",
      ),
      source: {
        titre: "Choisir les images",
        sousTitre: "Un dossier entier, ou des images précises.",
        boutonDossier: "Importer un dossier…",
        boutonFichiers: "Importer des images…",
        aideFichiers: "Seulement les images que vous choisissez",
        resume: (src) =>
          src.source.type === "dossier"
            ? `Dossier · ${pluriel(src.nbMedias, "image")}, sous-dossiers compris (tout dans un seul dossier)`
            : `${pluriel(src.nbMedias, "image")} sélectionnée${s(src.nbMedias)}`,
        alerte: (src) => (src.remplace ? `Le dossier « ${nomDossier(src.sortie)} » existe déjà : il sera remplacé.` : null),
      },
      options: {
        titre: "Format de sortie",
        sousTitre: "Choisissez le format des images, et leur nom.",
        contenu: (
          <>
            <Segments
              nom="format-images"
              libelle="Format de sortie"
              valeur={format}
              onChange={setFormat}
              disabled={occupe}
              choix={[
                { valeur: "jpg", libelle: "JPG" },
                { valeur: "png", libelle: "PNG" },
              ]}
            />
            <p className="mt-2.5 text-12 text-fg-3">
              JPG = plus léger (recommandé pour les réseaux sociaux) · PNG = sans perte, garde la transparence.
            </p>
            <Case
              className="mt-4"
              coche={renommer}
              onChange={setRenommer}
              disabled={occupe}
              aide={`Les images converties s'appellent 1.${format}, 2.${format}, 3.${format}…`}
            >
              Renommer les images (1, 2, 3…)
            </Case>
          </>
        ),
      },
      bouton: "Convertir",
      progression: {
        titre: "Conversion des images…",
        enAttente: `Conversion en .${format}`,
        unite: "images",
        texteAnnulation: "HelpVA termine les images en cours, puis s'arrête. Les images déjà converties sont gardées.",
      },
      resultat: (r) => {
        const fmt = r.format ?? format;
        return {
          titre: r.arrete
            ? fr(`Arrêté : ${pluriel(r.traites, "image")} convertie${s(r.traites)}`)
            : `${pluriel(r.traites, "image")} convertie${s(r.traites)} en .${fmt}`,
          sousTitre: r.arrete ? "Les images déjà converties sont gardées." : fr(`Dans « ${nomDossier(r.sortie)} ».`),
          avertissement: r.echecs.length
            ? {
                texte: fr(
                  `${pluriel(r.echecs.length, "fichier")} non converti${s(r.echecs.length)} (illisible ou corrompu) : ${r.echecs.slice(0, 3).join(", ")}${r.echecs.length > 3 ? "…" : ""}`,
                ),
                detail: r.echecs.join("\n"),
              }
            : null,
        };
      },
      journalVide: "Le détail de chaque image s'affichera ici pendant la conversion.",
    }),
    [format, setFormat, renommer, setRenommer, occupe],
  );
  return <ModuleTraitement mod={moduleParCle("images")} config={config} {...props} />;
}
