import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";
import videoIcone from "../assets/icons/video.webp";
import { lignesProgression, type Progression } from "../engine/affichage";
import { fr } from "../fr";
import { Bouton } from "./ui";

/**
 * Progression NON bloquante, à la place du bouton « Convertir ».
 *
 * Pourquoi pas une fenêtre par-dessus tout l'écran : elle cachait le Journal, qui sert justement
 * à suivre la conversion. Et l'app actuelle ne verrouille pas la fenêtre non plus (app_ctk.py :
 * « PAS de grab_set ici »). Les boutons d'import sont désactivés pendant ce temps (`occupe`).
 *
 * Même contenu que la fenêtre « Veuillez patienter » de l'app :
 *   ligne 1 : Dossier 2/3 — Modèle A
 *   ligne 2 : Vidéo 1/4 · clip_07.mov — 43 %
 *   barre   : progression GLOBALE (toutes les vidéos)
 *
 * Les noms arrivent COMPLETS du moteur (`details`) : c'est le CSS (`truncate`) qui les coupe
 * avec « … » selon la place disponible, au lieu d'une coupure fixe à 24 caractères.
 */
export default function CarteProgression({
  progression,
  annulation,
  annuler,
}: {
  progression: Progression | null;
  annulation: boolean;
  annuler: () => void;
}) {
  const carte = useRef<HTMLElement>(null);
  const boutonAnnuler = useRef<HTMLButtonElement>(null);

  // À l'apparition : on montre la carte et on met le focus sur « Annuler l'opération ».
  // Seulement si le focus n'était nulle part (il était sur « Convertir », qui vient de disparaître) :
  // si l'utilisateur revient sur cet écran par la barre latérale, on ne lui vole pas le focus.
  useEffect(() => {
    carte.current?.scrollIntoView({ block: "nearest" });
    if (document.activeElement === document.body || document.activeElement === null) boutonAnnuler.current?.focus();
  }, []);

  const p = progression;
  const pct = p ? Math.round(p.fraction * 100) : 0;
  const [l1, l2] = p ? lignesProgression(p) : ["", ""];
  const ligneDossier = p ? l1 || "Conversion des vidéos" : "Préparation…";
  const ligneVideo = p ? fr(l2) : "";
  const faites = p ? p.faites : 0;
  const total = p?.total ?? null;

  return (
    <section
      ref={carte}
      aria-labelledby="titre-progression"
      className={`entree mt-4 overflow-hidden rounded-2xl border bg-surface shadow-card ${
        annulation ? "border-danger/30" : "border-brand/30"
      }`}
    >
      <div className="p-4 pl-5">
        <div className="flex items-center gap-4">
          {/* Icône du module dans un anneau qui tourne */}
          <span className="relative grid h-12 w-12 shrink-0 place-items-center">
            <svg viewBox="0 0 48 48" className={`absolute inset-0 ${annulation ? "" : "tourne"}`} aria-hidden="true">
              <circle cx="24" cy="24" r="22" fill="none" stroke="var(--line)" strokeWidth="2" />
              <circle
                cx="24"
                cy="24"
                r="22"
                fill="none"
                stroke={annulation ? "var(--danger)" : "var(--brand)"}
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="34 105"
              />
            </svg>
            <img src={videoIcone} alt="" className="h-7 w-7 object-contain" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="titre-progression" className={`text-16 font-semibold ${annulation ? "text-danger" : ""}`}>
              {annulation ? "Annulation…" : "Conversion en cours…"}
            </h2>
            <p className="truncate text-13 text-fg-2" title={annulation ? undefined : ligneDossier}>
              {annulation ? "Fermeture de ffmpeg" : ligneDossier}
            </p>
          </div>
          <div className="tabular shrink-0 text-right" aria-hidden="true">
            <p className="text-28 font-semibold leading-none tracking-[-0.02em]">
              {pct}
              <span className="ml-0.5 text-16 font-medium text-fg-3">%</span>
            </p>
            <p className="mt-1 text-12 text-fg-3">
              {total !== null ? `${faites} / ${total} vidéos` : " "}
            </p>
          </div>
        </div>

        <div
          className="mt-2.5 h-2 overflow-hidden rounded-full bg-fg/[0.08]"
          role="progressbar"
          aria-label="Progression globale"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-valuetext={fr(total !== null ? `${pct} %, ${faites} vidéos sur ${total}` : `${pct} %`)}
        >
          <div
            className={`barre-remplie h-full rounded-full ${annulation ? "opacity-50 grayscale" : ""}`}
            style={{ width: `${Math.max(pct, 2)}%` }}
          />
        </div>

        <div className="mt-2.5 flex items-center gap-4">
          {annulation ? (
            <p className="min-w-0 flex-1 text-12 text-fg-2">HelpVA arrête la vidéo en cours et supprime le fichier incomplet.</p>
          ) : (
            <p className="tabular min-w-0 flex-1 truncate text-12 text-fg-3" title={ligneVideo}>
              {ligneVideo}
            </p>
          )}
          {/* aria-disabled (et pas disabled) : le focus reste sur le bouton pendant l'annulation. */}
          <Bouton
            ref={boutonAnnuler}
            taille="sm"
            variante="danger"
            className="shrink-0"
            aria-disabled={annulation || undefined}
            aria-keyshortcuts="Escape"
            onClick={annulation ? undefined : annuler}
          >
            <X weight="bold" className="h-3.5 w-3.5" />
            {annulation ? "Annulation…" : "Annuler l'opération"}
            {!annulation && (
              <kbd className="-mr-1 rounded border border-danger/25 px-1 font-sans text-11 font-medium leading-4 opacity-80">Échap</kbd>
            )}
          </Bouton>
        </div>
      </div>

      {/* Pour les lecteurs d'écran : une annonce par NOUVEAU fichier (pas à chaque % qui bouge). */}
      <p className="sr-only" aria-live="polite">
        {annulation
          ? "Annulation en cours."
          : p?.element
            ? fr(`${ligneDossier}. ${p.element.mot} ${p.element.index} sur ${p.element.total} : ${p.element.nom ?? ""}.`)
            : ""}
      </p>
    </section>
  );
}
