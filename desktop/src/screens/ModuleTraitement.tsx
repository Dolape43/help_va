import { useEffect, useRef, type ReactNode } from "react";
import { ArrowRight, FolderOpen, Warning, type Icon } from "@phosphor-icons/react";
import { Bouton, Icone3D, Rouage, Surtitre } from "../components/ui";
import { ICONES_3D } from "../icones3d";
import EnteteModule from "../components/EnteteModule";
import Dialogue from "../components/Dialogue";
import CarteProgression from "../components/module/CarteProgression";
import CarteResultat from "../components/module/CarteResultat";
import Journal from "../components/module/Journal";
import { BlocInfo, Etape } from "../components/module/Etape";
import type { ModuleDef } from "../modules";
import type { ResultatTraitement } from "../engine/api";
import type { SourceChoisie, Traitement } from "../engine/useTraitement";
import { fr } from "../fr";

/** Ce qui change d'un module de traitement à l'autre (MP4, images, métadonnées). */
export type ConfigTraitement = {
  sousTitre: string;
  info: ReactNode;
  source: {
    titre: string;
    sousTitre: string;
    boutonDossier: string;
    boutonFichiers: string;
    iconeFichiers: Icon;
    /** « Aucune source pour l'instant : importez un dossier ou des vidéos. » */
    vide: string;
    /** « Dossier · 12 vidéos, sous-dossiers compris » */
    resume: (s: SourceChoisie) => string;
    /** avertissement sous la source (fichiers qui seront remplacés…) */
    alerte?: (s: SourceChoisie) => string | null;
  };
  /** étape 2 (format, renommage…) ; absente pour le MP4 */
  options?: { titre: string; sousTitre: string; contenu: ReactNode };
  /** « Convertir », « Lancer » */
  bouton: string;
  /** phrase sous le bouton (« Résultat dans « media (mp4) »… ») */
  indication: string;
  progression: { titre: string; enAttente: string; unite: string; texteAnnulation: string; annonceParFichier?: boolean };
  resultat: (r: ResultatTraitement) => {
    titre: string;
    sousTitre: string;
    avertissement?: { texte: string; detail?: string } | null;
  };
  journalVide: string;
};

/**
 * L'écran d'un module « source → options → lancer » : même mise en page pour les 3 modules,
 * seuls les textes et l'étape d'options changent (voir ConvertirMp4, ConvertirImages, Metadonnees).
 */
export default function ModuleTraitement({
  mod,
  config,
  t,
  occupeAilleurs,
  bandeau,
  retour,
  ouvrirDossier,
}: {
  mod: ModuleDef;
  config: ConfigTraitement;
  t: Traitement;
  /** une autre action tourne déjà (le moteur n'en fait qu'une à la fois) : son nom */
  occupeAilleurs: string | null;
  bandeau: ReactNode;
  retour: () => void;
  ouvrirDossier: (chemin: string) => void;
}) {
  const occupe = t.occupe;
  const bloque = occupe || !!occupeAilleurs;
  const termine = t.etat === "fini" || t.etat === "arrete";
  const idResultat = `resultat-${mod.cle}`;

  // Fin du traitement : la carte de progression disparaît. Si le focus était dessus (il retombe
  // alors sur <body>), on le rend au bouton « Lancer » pour ne pas perdre l'utilisateur au clavier.
  const boutonLancer = useRef<HTMLButtonElement>(null);
  const etaitOccupe = useRef(occupe);
  useEffect(() => {
    if (etaitOccupe.current && !occupe) {
      if (document.activeElement === document.body || !document.activeElement) boutonLancer.current?.focus({ preventScroll: true });
      // Et on fait apparaître la carte de résultat si elle est sous le bas de la fenêtre.
      document.getElementById(idResultat)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    etaitOccupe.current = occupe;
  }, [occupe, idResultat]);

  const s = t.source;
  const alerte = s ? config.source.alerte?.(s) : null;
  const IconeFichiers = config.source.iconeFichiers;

  return (
    // Container queries : sous 840 px de largeur utile, le Journal passe SOUS la colonne principale.
    <div className="entree grid min-h-full content-start gap-5 px-6 pb-7 pt-6 @min-[840px]:grid-cols-[minmax(0,1fr)_300px] @min-[840px]:content-stretch @min-[840px]:px-8 @min-[1040px]:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        {bandeau}
        <EnteteModule mod={mod} sousTitre={config.sousTitre} retour={retour} />
        <BlocInfo>{config.info}</BlocInfo>

        {/* Étape 1 : la source */}
        <Etape numero={1} titre={config.source.titre} sousTitre={config.source.sousTitre}>
          <div className="mt-4 flex flex-wrap gap-2">
            <Bouton disabled={occupe || t.verification} onClick={() => t.choisir("dossier")}>
              <FolderOpen className="h-4 w-4 text-fg-2" aria-hidden="true" />
              {config.source.boutonDossier}
            </Bouton>
            <Bouton disabled={occupe || t.verification} onClick={() => t.choisir("fichiers")}>
              <IconeFichiers className="h-4 w-4 text-fg-2" aria-hidden="true" />
              {config.source.boutonFichiers}
            </Bouton>
          </div>
          {s ? (
            <div className="mt-3 flex items-center gap-3 rounded-xl border border-brand/20 bg-brand-soft p-3.5">
              {/* Un dossier : l'icône 3D du dossier ; des fichiers choisis : l'icône 3D du module. */}
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-[12px] bg-surface shadow-[0_0_0_1px_var(--line)]">
                <Icone3D src={s.source.type === "dossier" ? ICONES_3D.dossier : mod.icone} taille={34} />
              </span>
              <div className="min-w-0 flex-1">
                <Surtitre>Source sélectionnée</Surtitre>
                <p className="source-choisie selectable mt-0.5 truncate text-14 font-medium" title={s.libelleComplet}>
                  {s.libelle}
                </p>
                <p className="text-12 text-fg-3">{config.source.resume(s)}</p>
                {alerte && (
                  <p className="mt-1 flex items-start gap-1.5 text-12 text-warning">
                    <Warning weight="fill" className="mt-[2px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    <span>{fr(alerte)}</span>
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className="mt-3 rounded-xl border border-dashed border-line-2 p-3.5 text-13 text-fg-3">{config.source.vide}</p>
          )}
        </Etape>

        <p className="sr-only" aria-live="polite">
          {s ? fr(`Source sélectionnée : ${config.source.resume(s)}.${alerte ? ` ${alerte}` : ""}`) : ""}
        </p>

        {/* Étape 2 : options */}
        {config.options && (
          <Etape numero={2} titre={config.options.titre} sousTitre={config.options.sousTitre}>
            <div className="mt-4">{config.options.contenu}</div>
          </Etape>
        )}

        {/* Action : bouton, OU progression (non bloquante) pendant le traitement */}
        {occupe ? (
          <CarteProgression
            progression={t.progression}
            annulation={t.etat === "annulation"}
            annuler={t.annuler}
            icone={mod.icone}
            {...config.progression}
          />
        ) : (
          <>
            <Bouton
              ref={boutonLancer}
              variante="primaire"
              taille="lg"
              className="group mt-5 w-full"
              onClick={t.lancer}
              disabled={!s || !!occupeAilleurs}
              aria-busy={t.verification || undefined}
              title={occupeAilleurs ? fr(`Patientez : « ${occupeAilleurs} » est en cours.`) : s ? undefined : "Choisissez d'abord une source"}
            >
              {t.verification ? <Rouage /> : null}
              {config.bouton}
              {!t.verification && (
                <ArrowRight weight="bold" className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
              )}
            </Bouton>
            {termine && t.resultat ? (
              <CarteResultat
                id={idResultat}
                arrete={t.resultat.arrete}
                {...config.resultat(t.resultat)}
                sortie={t.resultat.sortie}
                ouvrirSortie={() => t.resultat && ouvrirDossier(t.resultat.sortie)}
              />
            ) : (
              <p className="mt-2.5 text-center text-12 text-fg-3">
                {occupeAilleurs ? fr(`Une autre action est en cours (« ${occupeAilleurs} ») : patientez.`) : fr(config.indication)}
              </p>
            )}
          </>
        )}
      </div>

      <Journal
        etat={t.etat}
        journal={t.journal}
        effacer={t.effacer}
        vide={config.journalVide}
        className="h-[340px] @min-[840px]:h-auto"
      />

      {/* « Remplacer ? » (l'ancienne messagebox), avec le chemin exact qui sera remplacé. */}
      <Dialogue
        ouvert={!!t.remplacement}
        fermer={t.refuserRemplacement}
        ton="warning"
        icone={<Warning weight="duotone" className="h-6 w-6" />}
        image={ICONES_3D.alerte}
        titre="Remplacer le dossier existant ?"
        actions={
          <>
            <Bouton data-autofocus onClick={t.refuserRemplacement}>
              Annuler
            </Bouton>
            <Bouton variante="primaire" onClick={() => void t.confirmerRemplacement()} disabled={bloque && !occupe}>
              Remplacer et lancer
            </Bouton>
          </>
        }
      >
        <p>
          {t.remplacement?.change
            ? "Le dossier de sortie a changé depuis votre confirmation. Ce dossier existe déjà et sera REMPLACÉ :"
            : "Le dossier existe déjà et sera REMPLACÉ :"}
        </p>
        <p className="selectable mt-2 rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-12 text-fg [overflow-wrap:anywhere]">
          {t.remplacement?.sortie}
        </p>
        <p className="mt-2 text-13">Son contenu actuel sera supprimé. Vos originaux, eux, ne sont jamais touchés.</p>
      </Dialogue>
    </div>
  );
}
