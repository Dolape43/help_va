import { useEffect, useRef, type ReactNode } from "react";
import { ArrowRight, Warning } from "@phosphor-icons/react";
import { Bouton, Icone3D, LienDossier, Rouage, Surtitre, joindre } from "../components/ui";
import { ICONES_3D } from "../icones3d";
import EnteteModule from "../components/EnteteModule";
import Dialogue from "../components/Dialogue";
import CarteProgression from "../components/module/CarteProgression";
import CarteResultat from "../components/module/CarteResultat";
import Journal from "../components/module/Journal";
import { Etape } from "../components/module/Etape";
import type { ModuleDef } from "../modules";
import type { ResultatTraitement } from "../engine/api";
import type { SourceChoisie, Traitement } from "../engine/useTraitement";
import { fr, pluriel } from "../fr";

/** Ce qui change d'un module de traitement à l'autre (MP4, images, métadonnées). */
export type ConfigTraitement = {
  sousTitre: string;
  /** 2 ou 3 points clés très courts, sous le titre (facultatif) */
  points?: string[];
  /** l'explication complète (« En savoir plus ») */
  info: ReactNode;
  /** ce qu'on traite, au singulier (« vidéo », « image », « média ») et son genre */
  mot: string;
  feminin: boolean;
  source: {
    titre: string;
    sousTitre: string;
    boutonDossier: string;
    boutonFichiers: string;
    /** phrase sous « choisir des fichiers » (« Seulement les vidéos que vous choisissez ») */
    aideFichiers: string;
    /** « Dossier · 12 vidéos, sous-dossiers compris » */
    resume: (s: SourceChoisie) => string;
    /** avertissement sous la source (fichiers qui seront remplacés…) */
    alerte?: (s: SourceChoisie) => string | null;
  };
  /** étape 2 (format, renommage…) ; absente pour le MP4 */
  options?: { titre: string; sousTitre: string; contenu: ReactNode };
  /** « Convertir », « Lancer » */
  bouton: string;
  /** nom du dossier de résultat, quand on le connaît avant de choisir la source (« media (mp4) ») */
  dossierResultat?: string;
  progression: { titre: string; enAttente: string; unite: string; texteAnnulation: string; annonceParFichier?: boolean };
  resultat: (r: ResultatTraitement) => {
    titre: string;
    sousTitre: string;
    avertissement?: { texte: string; detail?: string } | null;
  };
  journalVide: string;
};


/** Une grande tuile de choix de source (« Importer un dossier… »), à la place de deux petits boutons. */
function TuileChoix({
  image,
  titre,
  aide,
  onClick,
  disabled,
}: {
  image: string;
  titre: string;
  aide: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="tuile-choix group flex items-center gap-3.5 rounded-2xl border border-dashed border-line-2 bg-surface-2/60 p-4 text-left transition-[border-color,background-color,transform] duration-200 hover:-translate-y-px hover:border-brand/45 hover:bg-brand-soft disabled:pointer-events-none disabled:opacity-55"
    >
      <Icone3D src={image} taille={46} className="transition-transform duration-300 group-hover:scale-105" />
      <span className="min-w-0">
        <span className="block text-14 font-semibold">{titre}</span>
        <span className="block text-12 text-fg-3">{aide}</span>
      </span>
    </button>
  );
}

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
  sortie,
}: {
  mod: ModuleDef;
  config: ConfigTraitement;
  t: Traitement;
  /** une autre action tourne déjà (le moteur n'en fait qu'une à la fois) : son nom */
  occupeAilleurs: string | null;
  bandeau: ReactNode;
  retour: () => void;
  ouvrirDossier: (chemin: string) => void;
  /** le dossier de sortie général (null pendant le chargement) */
  sortie: string | null;
}) {
  const occupe = t.occupe;
  const bloque = occupe || !!occupeAilleurs;
  const termine = t.etat === "fini" || t.etat === "arrete";
  const idResultat = `resultat-${mod.cle}`;
  /** où arrivera le résultat : connu exactement une fois la source choisie, sinon déduit du réglage */
  const cheminResultat = t.source?.sortie ?? (sortie ? (config.dossierResultat ? joindre(sortie, config.dossierResultat) : sortie) : null);

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
  const pret = s ? `${pluriel(s.nbMedias, config.mot)} prêt${config.feminin ? "e" : ""}${s.nbMedias > 1 ? "s" : ""}` : null;
  const etapeOptions = config.options ? 2 : null;

  return (
    // Container queries : sous 840 px de largeur utile, le Journal passe SOUS la colonne principale.
    <div className="entree grid min-h-full content-start gap-5 px-6 pb-7 pt-6 @min-[840px]:grid-cols-[minmax(0,1fr)_300px] @min-[840px]:content-stretch @min-[840px]:px-8 @min-[1040px]:grid-cols-[minmax(0,1fr)_340px]">
      <div className="@container min-w-0">
        {bandeau}
        <EnteteModule mod={mod} sousTitre={config.sousTitre} points={config.points} details={config.info} retour={retour} />

        <div className="mt-2">
          {/* Étape 1 : la source */}
          <Etape numero={1} titre={config.source.titre} sousTitre={config.source.sousTitre} fait={!!s} dernier={!config.options}>
            {s ? (
              <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-brand/20 bg-brand-soft p-3.5">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-[12px] bg-surface shadow-[0_0_0_1px_var(--line)]">
                  <Icone3D src={s.source.type === "dossier" ? ICONES_3D.dossier : mod.icone} taille={34} />
                </span>
                <div className="min-w-[160px] flex-1">
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
                {/* Changer d'avis : les deux choix restent à portée, en petit. */}
                <div className="flex shrink-0 flex-wrap gap-1.5">
                  <Bouton taille="sm" disabled={occupe || t.verification} onClick={() => t.choisir("dossier")}>
                    Autre dossier…
                  </Bouton>
                  <Bouton taille="sm" disabled={occupe || t.verification} onClick={() => t.choisir("fichiers")}>
                    Autres fichiers…
                  </Bouton>
                </div>
              </div>
            ) : (
              <div className="mt-4 grid grid-cols-1 gap-3 @min-[540px]:grid-cols-2">
                <TuileChoix
                  image={ICONES_3D.dossier}
                  titre={config.source.boutonDossier}
                  aide="Tout le dossier, sous-dossiers compris"
                  onClick={() => t.choisir("dossier")}
                  disabled={occupe || t.verification}
                />
                <TuileChoix
                  image={mod.icone}
                  titre={config.source.boutonFichiers}
                  aide={config.source.aideFichiers}
                  onClick={() => t.choisir("fichiers")}
                  disabled={occupe || t.verification}
                />
              </div>
            )}
          </Etape>

          {/* Étape 2 : options */}
          {config.options && etapeOptions && (
            <Etape numero={etapeOptions} titre={config.options.titre} sousTitre={config.options.sousTitre} fait={!!s} dernier>
              <div className="mt-4">{config.options.contenu}</div>
            </Etape>
          )}
        </div>

        <p className="sr-only" aria-live="polite">
          {s ? fr(`Source sélectionnée : ${config.source.resume(s)}.${alerte ? ` ${alerte}` : ""}`) : ""}
        </p>

        {/* Lancement : un récapitulatif (quoi, où) et le bouton, OU la progression pendant le traitement */}
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
            <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 pl-5 shadow-card @min-[600px]:flex-row @min-[600px]:items-center @min-[600px]:gap-5">
              <div className="min-w-0 flex-1">
                <p className="text-14 font-semibold">{occupeAilleurs ? "Une autre action est en cours" : (pret ?? "Choisissez une source pour commencer")}</p>
                {occupeAilleurs ? (
                  <p className="text-12 text-fg-3">{fr(`Patientez : « ${occupeAilleurs} » doit d'abord se terminer.`)}</p>
                ) : (
                  cheminResultat && <LienDossier chemin={cheminResultat} ouvrir={() => ouvrirDossier(cheminResultat)} />
                )}
              </div>
              <Bouton
                ref={boutonLancer}
                variante="primaire"
                taille="lg"
                className="group w-full @min-[600px]:w-auto @min-[600px]:min-w-[210px]"
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
            </div>
            {termine && t.resultat && (
              <CarteResultat
                id={idResultat}
                arrete={t.resultat.arrete}
                {...config.resultat(t.resultat)}
                sortie={t.resultat.sortie}
                ouvrirSortie={() => t.resultat && ouvrirDossier(t.resultat.sortie)}
              />
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
