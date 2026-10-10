import { useEffect, useRef } from "react";
import { CheckCircle, StopCircle, TerminalWindow, Warning, WarningCircle } from "@phosphor-icons/react";
import { Bouton, Carte } from "../ui";
import type { LigneJournal } from "../../engine/affichage";
import type { EtatTache } from "../../engine/useSuivi";

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
        <CheckCircle weight="fill" className="mt-[3px] h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
        <p className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]">
          {l.texte}
          {l.chemin && <Chemin chemin={l.chemin} />}
        </p>
      </div>
    );
  }
  if (l.niveau === "arret") {
    return (
      <div className="entree mt-1 flex items-start gap-2 text-danger">
        <StopCircle weight="fill" className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
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
        <Icone weight="fill" className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
        <p className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]">{l.texte.replace(/(⚠️|⚠|❌|⏭)\s*/u, "")}</p>
      </div>
    );
  }
  if (l.niveau === "info") {
    return (
      <p className="entree truncate whitespace-pre text-fg-3" title={l.texte}>
        {l.texte}
      </p>
    );
  }
  // « [convert] (1/4) clip_07.mov… » : étiquette et compteur en gris, le nom en clair.
  const m = l.texte.match(/^(\[\w+\]) (\(\d+\/\d+\)) (.*)$/);
  return (
    <p className="entree truncate pl-5" title={l.texte}>
      {m ? (
        <>
          <span className="text-fg-3">{m[1]}</span> <span className="text-fg-3">{m[2]}</span> <span className="text-fg">{m[3]}</span>
        </>
      ) : (
        l.texte
      )}
    </p>
  );
}

/**
 * Le journal de la dernière action du module (détail fichier par fichier).
 * Il défile DANS sa carte (un journal très long n'agrandit pas la page).
 */
export default function Journal({
  etat,
  journal,
  effacer,
  vide,
  className = "",
}: {
  etat: EtatTache;
  journal: LigneJournal[];
  effacer: () => void;
  /** phrase quand le journal est vide (« Le détail de chaque vidéo s'affichera ici… ») */
  vide: string;
  className?: string;
}) {
  const zone = useRef<HTMLDivElement>(null);
  // Le journal descend tout seul vers la dernière ligne (sans faire défiler le reste de la page).
  useEffect(() => {
    const el = zone.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [journal.length]);
  const occupe = etat === "en_cours" || etat === "annulation";

  return (
    <Carte className={`flex min-h-0 flex-col overflow-hidden ${className}`}>
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <TerminalWindow weight="duotone" className="h-4 w-4 text-fg-3" aria-hidden="true" />
        <h2 className="text-13 font-semibold">Journal</h2>
        <Statut etat={etat} />
        <Bouton
          taille="sm"
          variante="fantome"
          className="ml-auto h-7 px-2 text-12"
          onClick={occupe || !journal.length ? undefined : effacer}
          aria-disabled={occupe || !journal.length || undefined}
        >
          Effacer
        </Bouton>
      </div>
      <div className="relative min-h-0 flex-1 bg-surface-2">
        <div
          ref={zone}
          role="log"
          // Pas d'annonce ligne par ligne : la carte de progression annonce déjà chaque fichier.
          aria-live="off"
          aria-label="Journal de l'opération"
          className="scroll-fin selectable absolute inset-0 overflow-y-auto px-4 py-3 font-mono text-12 leading-[1.7]"
        >
          {journal.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center font-sans">
              <span className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-surface text-fg-3">
                <TerminalWindow className="h-5 w-5" aria-hidden="true" />
              </span>
              <p className="text-13 text-fg-2">Rien pour l'instant</p>
              <p className="max-w-[220px] text-12 text-fg-3">{vide}</p>
            </div>
          ) : (
            journal.map((l, i) => <Ligne key={i} l={l} />)
          )}
        </div>
      </div>
    </Carte>
  );
}
