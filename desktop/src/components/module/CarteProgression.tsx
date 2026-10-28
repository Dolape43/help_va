import { useEffect, useRef, useState } from "react";
import { X } from "@phosphor-icons/react";
import { lignesProgression, type Progression } from "../../engine/affichage";
import { fr } from "../../fr";
import { Bouton } from "../ui";

/** 75 -> « 1 min 15 s » ; arrondi=true (une estimation) -> « 2 min », « moins d'une minute », « 1 h 20 ». */
function duree(s: number, arrondi = false): string {
  s = Math.max(0, Math.round(s));
  if (arrondi) {
    if (s < 60) return "moins d'une minute";
    const min = Math.round(s / 60);
    return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")}`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h) return `${h} h ${String(m).padStart(2, "0")}`;
  return m ? `${m} min ${String(s % 60).padStart(2, "0")} s` : `${s} s`;
}

const heure = (ms: number) => new Date(ms).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }).replace(":", "h");

/**
 * Temps écoulé et temps restant estimé, d'après la vitesse moyenne depuis le début :
 * reste = écoulé × (1 − fraction) / fraction. Pas d'estimation trop tôt (moins de 3 % ou de
 * 4 s : elle serait fausse), puis lissée pour ne pas sauter de 2 à 9 min d'une seconde à l'autre.
 * Le départ = l'apparition de la carte (elle apparaît au lancement de l'opération).
 */
function useTempsRestant(fraction: number, arret: boolean): { ecoule: number; reste: number | null } {
  const debut = useRef(Date.now());
  const frac = useRef(fraction);
  frac.current = fraction;
  const [etat, setEtat] = useState<{ ecoule: number; reste: number | null }>({ ecoule: 0, reste: null });
  // Recalculé UNE fois par seconde (et non à chaque nouvelle du moteur) : le lissage reste régulier.
  useEffect(() => {
    if (arret) return;
    const id = window.setInterval(() => {
      const ecoule = (Date.now() - debut.current) / 1000;
      const f = frac.current;
      setEtat((avant) => {
        if (f >= 1) return { ecoule, reste: 0 };
        if (f < 0.03 || ecoule < 4) return { ecoule, reste: null };
        const brut = (ecoule * (1 - f)) / f;
        // 80 % de l'estimation précédente (qui a « vieilli » d'une seconde) + 20 % de la nouvelle.
        const reste = avant.reste === null ? brut : 0.8 * Math.max(0, avant.reste - 1) + 0.2 * brut;
        return { ecoule, reste };
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [arret]);
  return etat;
}

/**
 * Progression NON bloquante, à la place du bouton « Lancer » (pour les 4 modules).
 *
 * Pourquoi pas une fenêtre par-dessus tout l'écran : elle cachait le Journal, qui sert justement
 * à suivre le travail. Et l'ancienne app ne verrouille pas la fenêtre non plus (app_ctk.py :
 * « PAS de grab_set ici »). Les boutons d'import sont désactivés pendant ce temps.
 *
 * Même contenu que la fenêtre « Veuillez patienter » de l'ancienne app :
 *   ligne 1 : Dossier 2/3 — Modèle A        (ou « Semaine 1/3 — Jour 2 » pour le rangement)
 *   ligne 2 : Vidéo 1/4 · clip_07.mov — 43 %
 *   barre   : progression GLOBALE
 * Les noms arrivent COMPLETS du moteur (`details`) : c'est le CSS (`truncate`) qui les coupe.
 */
export default function CarteProgression({
  progression,
  annulation,
  annuler,
  icone,
  titre,
  enAttente,
  unite,
  texteAnnulation,
  annonceParFichier = false,
}: {
  progression: Progression | null;
  annulation: boolean;
  annuler: () => void;
  /** icône 3D du module */
  icone: string;
  /** « Conversion en cours… » */
  titre: string;
  /** 1re ligne avant la première nouvelle du moteur (« Conversion des vidéos ») */
  enAttente: string;
  /** « vidéos », « images », « médias », « créneaux » (compteur « 4 / 11 vidéos ») */
  unite: string;
  /** ce que fait l'annulation (« HelpVA arrête la vidéo en cours et supprime le fichier incomplet. ») */
  texteAnnulation: string;
  /** annoncer CHAQUE fichier aux lecteurs d'écran (vrai pour le MP4 ; sinon : au plus toutes les 8 s) */
  annonceParFichier?: boolean;
}) {
  const carte = useRef<HTMLElement>(null);
  const boutonAnnuler = useRef<HTMLButtonElement>(null);

  // À l'apparition : on montre la carte et on met le focus sur « Annuler l'opération ».
  // Seulement si le focus n'était nulle part (il était sur « Lancer », qui vient de disparaître) :
  // si l'utilisateur revient sur cet écran par la barre latérale, on ne lui vole pas le focus.
  useEffect(() => {
    carte.current?.scrollIntoView({ block: "nearest" });
    const a = document.activeElement;
    if (!a || a === document.body || a.closest("dialog")) boutonAnnuler.current?.focus();
  }, []);

  const p = progression;
  const pct = p ? Math.round(p.fraction * 100) : 0;
  const restant = useTempsRestant(p?.fraction ?? 0, annulation);
  const [l1, l2] = p ? lignesProgression(p) : ["", ""];
  const ligne1 = p ? l1 || enAttente : "Préparation…";
  const ligne2 = p ? fr(l2) : "";
  const faites = p ? p.faites : 0;
  const total = p?.total ?? null;

  // Ce qui est lu par les lecteurs d'écran : à chaque nouveau groupe (dossier, jour) et, pour les
  // fichiers, chaque fois (MP4) ou au plus toutes les 8 s (sinon ce serait une annonce par image).
  const [annonce, setAnnonce] = useState("");
  const derniere = useRef({ quand: 0, groupe: "" });
  const element = p?.element;
  const cleElement = element ? `${element.index}/${element.total}|${element.nom ?? ""}` : "";
  useEffect(() => {
    if (!element || annulation) return;
    const maintenant = Date.now();
    const groupe = ligne1;
    if (annonceParFichier || groupe !== derniere.current.groupe || maintenant - derniere.current.quand > 8000) {
      derniere.current = { quand: maintenant, groupe };
      setAnnonce(fr(`${ligne1}. ${element.mot} ${element.index} sur ${element.total} : ${element.nom ?? ""}.`));
    }
    // Seulement quand le fichier change : les autres valeurs sont lues au même moment.
  }, [cleElement, annulation]);

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
            <img src={icone} alt="" className="h-7 w-7 object-contain" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="titre-progression" className={`text-16 font-semibold ${annulation ? "text-danger" : ""}`}>
              {annulation ? "Annulation…" : titre}
            </h2>
            <p className="truncate text-13 text-fg-2" title={annulation ? undefined : ligne1}>
              {annulation ? "Arrêt en cours" : ligne1}
            </p>
          </div>
          <div className="tabular shrink-0 text-right" aria-hidden="true">
            <p className="text-28 font-semibold leading-none tracking-[-0.02em]">
              {pct}
              <span className="ml-0.5 text-16 font-medium text-fg-3">%</span>
            </p>
            <p className="mt-1 text-12 text-fg-3">{total !== null ? `${faites} / ${total} ${unite}` : " "}</p>
          </div>
        </div>
        {/* Temps restant : visible aussi des lecteurs d'écran, mais sans annonce à chaque seconde. */}
        <div className="tabular mt-2 flex items-center justify-between gap-3 text-12 text-fg-2">
          <span>{fr(`Écoulé : ${duree(restant.ecoule)}`)}</span>
          <span className="font-medium text-fg">
            {annulation
              ? " "
              : restant.reste === null
                ? "Estimation du temps restant…"
                : fr(`Reste environ ${duree(restant.reste, true)} · fin vers ${heure(Date.now() + restant.reste * 1000)}`)}
          </span>
        </div>

        <div
          className="mt-2.5 h-2 overflow-hidden rounded-full bg-fg/[0.08]"
          role="progressbar"
          aria-label="Progression globale"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-valuetext={fr(total !== null ? `${pct} %, ${faites} ${unite} sur ${total}` : `${pct} %`)}
        >
          <div
            className={`barre-remplie h-full rounded-full ${annulation ? "opacity-50 grayscale" : ""}`}
            style={{ width: `${Math.max(pct, 2)}%` }}
          />
        </div>

        <div className="mt-2.5 flex items-center gap-4">
          {annulation ? (
            <p className="min-w-0 flex-1 text-12 text-fg-2">{texteAnnulation}</p>
          ) : (
            <p className="tabular min-w-0 flex-1 truncate text-12 text-fg-3" title={ligne2}>
              {ligne2}
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
            <X weight="bold" className="h-3.5 w-3.5" aria-hidden="true" />
            {annulation ? "Annulation…" : "Annuler l'opération"}
            {!annulation && (
              <kbd className="-mr-1 rounded border border-danger/25 px-1 font-sans text-11 font-medium leading-4">Échap</kbd>
            )}
          </Bouton>
        </div>
      </div>

      {/* Pour les lecteurs d'écran : annonce par fichier ou par groupe (jamais à chaque % qui bouge). */}
      <p className="sr-only" aria-live="polite">
        {annulation ? "Annulation en cours." : annonce}
      </p>
    </section>
  );
}
