import { useEffect, useRef, type ReactNode } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle,
  FileVideo,
  FolderOpen,
  FolderSimpleStar,
  Info,
  StopCircle,
  TerminalWindow,
  Warning,
  WarningCircle,
} from "@phosphor-icons/react";
import { Bouton, Carte, Surtitre } from "../components/ui";
import EnteteModule from "../components/EnteteModule";
import CarteProgression from "../components/CarteProgression";
import { moduleParCle } from "../modules";
import type { LigneJournal, Progression } from "../engine/affichage";
import type { ResultatConversion } from "../engine/api";
import type { EtatTache, SourceChoisie } from "../App";
import { fr, pluriel } from "../fr";

function Statut({ etat }: { etat: EtatTache }) {
  const s = {
    inactif: { txt: "En attente", cls: "text-fg-3 bg-fg/[0.05]", point: "bg-fg-3" },
    en_cours: { txt: "En cours", cls: "text-brand-text bg-brand-soft", point: "bg-brand point-actif" },
    annulation: { txt: "Annulation…", cls: "text-danger bg-danger/10", point: "bg-danger point-actif" },
    fini: { txt: "Terminé", cls: "text-brand-text bg-brand-soft", point: "bg-brand" },
    arrete: { txt: "Interrompu", cls: "text-fg-2 bg-fg/[0.05]", point: "bg-danger" },
  }[etat];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-12 font-medium ${s.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.point}`} aria-hidden="true" />
      {s.txt}
    </span>
  );
}

/** Chemin sur SA propre ligne, coupé avec « … » si trop long (le chemin complet est dans l'info-bulle). */
function Chemin({ chemin }: { chemin: string }) {
  return (
    <span className="block truncate text-fg-3" title={chemin}>
      → {chemin}
    </span>
  );
}

function Ligne({ l }: { l: LigneJournal }) {
  if (l.niveau === "dossier") {
    return (
      <p className="entree mt-2.5 flex items-center gap-2 text-brand-text first:mt-0">
        <span className="h-px w-3 bg-current opacity-50" aria-hidden="true" />
        {l.texte}
      </p>
    );
  }
  if (l.niveau === "succes") {
    return (
      <div className="entree mt-3 flex items-start gap-2 rounded-lg border border-brand/20 bg-brand-soft px-2.5 py-2 text-fg">
        <CheckCircle weight="fill" className="mt-[3px] h-4 w-4 shrink-0 text-brand" />
        <p className="min-w-0">
          {l.texte}
          {l.chemin && <Chemin chemin={l.chemin} />}
        </p>
      </div>
    );
  }
  if (l.niveau === "arret") {
    return (
      <div className="entree mt-1 flex items-start gap-2 text-danger">
        <StopCircle weight="fill" className="mt-[3px] h-4 w-4 shrink-0" />
        <p className="min-w-0 [overflow-wrap:anywhere]">
          {l.texte.replace(/^.*?⛔\s*/, "")}
          {l.chemin && <Chemin chemin={l.chemin} />}
        </p>
      </div>
    );
  }
  if (l.niveau === "avertissement" || l.niveau === "erreur") {
    const Icone = l.niveau === "erreur" ? WarningCircle : Warning;
    return (
      <div className={`entree flex items-start gap-2 ${l.niveau === "erreur" ? "text-danger" : "text-warning"}`}>
        <Icone weight="fill" className="mt-[3px] h-4 w-4 shrink-0" />
        <p className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]">{l.texte.replace(/(⚠️|⚠|❌|⏭)\s*/u, "")}</p>
      </div>
    );
  }
  if (l.niveau === "info") return <p className="entree truncate whitespace-pre text-fg-3" title={l.texte}>{l.texte}</p>;
  // [convert] (1/4) clip_07.mov…
  const m = l.texte.match(/^(\[convert\]) (\(\d+\/\d+\)) (.*)$/);
  return (
    <p className="entree truncate pl-5">
      {m ? (
        <>
          <span className="text-fg-3">{m[1]}</span> <span className="text-fg-3">{m[2]}</span>{" "}
          <span className="text-fg">{m[3]}</span>
        </>
      ) : (
        l.texte
      )}
    </p>
  );
}

/** Ce qui RESTE à l'écran après la conversion (la notification, elle, disparaît). */
function CarteResultat({ resultat, ouvrirSortie }: { resultat: ResultatConversion; ouvrirSortie: () => void }) {
  const { traites, dossiers, arrete, sortie, echecs } = resultat;
  const s = traites > 1 ? "s" : "";
  const titre = arrete
    ? fr(`Arrêté : ${pluriel(traites, "vidéo")} convertie${s}`)
    : dossiers > 1
      ? `${pluriel(traites, "vidéo")} convertie${s} dans ${pluriel(dossiers, "dossier")}`
      : `${pluriel(traites, "vidéo")} convertie${s}`;
  const sousTitre = arrete
    ? "Le fichier incomplet a été supprimé."
    : dossiers > 1
      ? "Même arborescence que votre dossier."
      : fr("Dans « media (mp4) ».");
  return (
    <div
      id="resultat-mp4"
      role="status"
      className={`entree mt-3 flex flex-wrap items-center gap-x-3.5 gap-y-3 rounded-2xl border p-4 ${
        arrete ? "border-line bg-surface" : "border-brand/25 bg-brand-soft"
      }`}
    >
      {arrete ? (
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-fg/[0.06] text-fg-2">
          <StopCircle weight="fill" className="h-5 w-5" />
        </span>
      ) : (
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-btn text-white shadow-[0_8px_18px_-8px_rgba(76,111,255,0.9)]">
          <Check weight="bold" className="h-5 w-5" />
        </span>
      )}
      <div className="min-w-[180px] flex-1">
        <p className="text-14 font-semibold">{titre}</p>
        <p className="truncate text-13 text-fg-2" title={sortie}>
          {sousTitre}
        </p>
        {echecs.length > 0 && (
          <p className="mt-1 flex items-start gap-1.5 text-13 text-warning" title={echecs.join("\n")}>
            <Warning weight="fill" className="mt-[3px] h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 truncate">
              {fr(`${pluriel(echecs.length, "fichier")} non converti${echecs.length > 1 ? "s" : ""} (vide ou corrompu) : ${echecs.join(", ")}`)}
            </span>
          </p>
        )}
      </div>
      <Bouton taille="sm" onClick={ouvrirSortie}>
        <FolderOpen className="h-4 w-4 text-fg-2" />
        Ouvrir le dossier
      </Bouton>
    </div>
  );
}

/** « Dossier · 12 vidéos » / « 3 vidéos sélectionnées » sous le chemin de la source. */
function resumeSource(s: SourceChoisie) {
  if (s.source.type === "dossier") return `Dossier · ${pluriel(s.nbVideos, "vidéo")}, sous-dossiers compris`;
  return `${pluriel(s.nbVideos, "vidéo")} sélectionnée${s.nbVideos > 1 ? "s" : ""}`;
}

export default function ConvertirMp4({
  bandeau,
  source,
  choisir,
  demo,
  etat,
  progression,
  resultat,
  journal,
  lancer,
  annuler,
  ouvrirSortie,
  effacer,
  retour,
}: {
  /** bandeau « Moteur non connecté » (rien si le moteur est là) */
  bandeau: ReactNode;
  source: SourceChoisie | null;
  choisir: (type: "dossier" | "fichiers") => void;
  /** vrai si le moteur n'est pas connecté (conversion simulée) */
  demo: boolean;
  etat: EtatTache;
  progression: Progression | null;
  resultat: ResultatConversion | null;
  journal: LigneJournal[];
  lancer: () => void;
  annuler: () => void;
  ouvrirSortie: () => void;
  effacer: () => void;
  retour: () => void;
}) {
  const mod = moduleParCle("mp4");
  // Le journal descend tout seul vers la dernière ligne (sans faire défiler le reste de la page).
  const zone = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = zone.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [journal.length]);

  const occupe = etat === "en_cours" || etat === "annulation";

  // Fin de conversion : la carte de progression disparaît. Si le focus était dessus (il retombe
  // alors sur <body>), on le rend au bouton « Convertir » pour ne pas perdre l'utilisateur au clavier.
  const boutonConvertir = useRef<HTMLButtonElement>(null);
  const etaitOccupe = useRef(occupe);
  useEffect(() => {
    if (etaitOccupe.current && !occupe) {
      if (document.activeElement === document.body || !document.activeElement) {
        boutonConvertir.current?.focus({ preventScroll: true });
      }
      // Et on fait apparaître la carte de résultat si elle est sous le bas de la fenêtre.
      document.getElementById("resultat-mp4")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    etaitOccupe.current = occupe;
  }, [occupe]);

  const termine = etat === "fini" || etat === "arrete";

  return (
    // Container queries : sous 840 px de largeur utile, le Journal passe SOUS la colonne principale
    // (sinon il ne reste qu'environ 300 px pour les boutons et le chemin).
    <div className="entree grid min-h-full content-start gap-5 px-6 pb-7 pt-6 @min-[840px]:grid-cols-[minmax(0,1fr)_300px] @min-[840px]:content-stretch @min-[840px]:px-8 @min-[1040px]:grid-cols-[minmax(0,1fr)_340px]">
      {/* Colonne principale */}
      <div className="min-w-0">
        {bandeau}
        <EnteteModule mod={mod} sousTitre="Transforme vos vidéos (.mov, .avi, .mkv…) en .mp4." retour={retour} />

        {/* Ce que fait ce module */}
        <div className="mt-6 flex gap-3 rounded-2xl border border-line p-4">
          <Info weight="duotone" className="mt-0.5 h-5 w-5 shrink-0 text-brand-text" />
          <div>
            <p className="text-14 font-semibold">Ce que fait ce module</p>
            <p className="mt-1 text-13 leading-relaxed text-fg-2">
              {fr(
                "HelpVA crée une version .mp4 de chaque vidéo dans « media (mp4) ». Rapide quand c'est possible (il change juste le conteneur), sinon ré-encodage automatique (H.264/AAC) pour que ça marche à coup sûr. Vos originaux ne sont pas touchés.",
              )}
            </p>
          </div>
        </div>

        {/* Étape 1 */}
        <Carte className="mt-4 p-5">
          <div className="flex items-start gap-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-soft text-13 font-semibold text-brand-text ring-1 ring-brand/20">
              1
            </span>
            <div>
              <h2 className="text-16 font-semibold">Choisir les vidéos</h2>
              <p className="text-13 text-fg-2">Un dossier entier, ou des vidéos précises.</p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Bouton disabled={occupe} onClick={() => choisir("dossier")}>
              <FolderOpen className="h-4 w-4 text-fg-2" />
              Importer un dossier…
            </Bouton>
            <Bouton disabled={occupe} onClick={() => choisir("fichiers")}>
              <FileVideo className="h-4 w-4 text-fg-2" />
              Importer des vidéos…
            </Bouton>
          </div>
          {source ? (
            <div className="mt-3 flex items-center gap-3 rounded-xl border border-brand/20 bg-brand-soft p-3.5">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-surface text-brand-text shadow-[0_0_0_1px_var(--line)]">
                {source.source.type === "dossier" ? (
                  <FolderSimpleStar weight="duotone" className="h-5 w-5" />
                ) : (
                  <FileVideo weight="duotone" className="h-5 w-5" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <Surtitre>Source sélectionnée</Surtitre>
                <p id="source-choisie" className="selectable mt-0.5 truncate text-14 font-medium" title={source.libelleComplet}>
                  {source.libelle}
                </p>
                <p className="text-12 text-fg-3">{resumeSource(source)}</p>
                {source.dejaPresents > 0 && (
                  <p id="deja-presents" className="mt-1 flex items-start gap-1.5 text-12 text-warning">
                    <Warning weight="fill" className="mt-[2px] h-3.5 w-3.5 shrink-0" />
                    <span>
                      {fr(
                        `${pluriel(source.dejaPresents, "vidéo")} déjà dans « media (mp4) » : ${
                          source.dejaPresents > 1 ? "elles seront remplacées" : "elle sera remplacée"
                        }.`,
                      )}
                    </span>
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className="mt-3 rounded-xl border border-dashed border-line-2 p-3.5 text-13 text-fg-3">
              {"Aucune source pour l'instant : importez un dossier ou des vidéos."}
            </p>
          )}
        </Carte>

        {/* Action : bouton, OU progression (non bloquante) pendant la conversion */}
        {occupe ? (
          <CarteProgression progression={progression} annulation={etat === "annulation"} annuler={annuler} />
        ) : (
          <>
            <Bouton
              ref={boutonConvertir}
              id="bouton-convertir"
              variante="primaire"
              taille="lg"
              className="group mt-5 w-full"
              onClick={lancer}
              disabled={!source}
              title={source ? undefined : "Choisissez d'abord des vidéos"}
            >
              Convertir
              <ArrowRight weight="bold" className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Bouton>
            {termine && resultat ? (
              <CarteResultat resultat={resultat} ouvrirSortie={ouvrirSortie} />
            ) : (
              <p className="mt-2.5 text-center text-12 text-fg-3">
                {demo
                  ? fr("Moteur non connecté : la conversion sera SIMULÉE (aucun fichier créé).")
                  : fr("Résultat dans « media (mp4) ». La conversion peut être longue selon les vidéos.")}
              </p>
            )}
          </>
        )}
      </div>

      {/* Journal */}
      <Carte className="flex h-[340px] min-h-0 flex-col overflow-hidden @min-[840px]:h-auto">
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          <TerminalWindow weight="duotone" className="h-4 w-4 text-fg-3" />
          <span className="text-13 font-semibold">Journal</span>
          <Statut etat={etat} />
          <Bouton taille="sm" variante="fantome" className="ml-auto h-7 px-2 text-12" onClick={effacer} disabled={occupe || !journal.length}>
            Effacer
          </Bouton>
        </div>
        {/* Le contenu est en position absolue : un journal très long défile DANS la carte
            au lieu d'agrandir la page. */}
        <div className="relative min-h-0 flex-1 bg-surface-2">
          <div ref={zone} className="scroll-fin selectable absolute inset-0 overflow-y-auto px-4 py-3 font-mono text-12 leading-[1.7]">
            {journal.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center font-sans">
                <span className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-surface text-fg-3">
                  <TerminalWindow className="h-5 w-5" />
                </span>
                <p className="text-13 text-fg-2">Rien pour l'instant</p>
                <p className="max-w-[220px] text-12 text-fg-3">Le détail de chaque vidéo s'affichera ici pendant la conversion.</p>
              </div>
            ) : (
              journal.map((l, i) => <Ligne key={i} l={l} />)
            )}
          </div>
        </div>
      </Carte>
    </div>
  );
}
