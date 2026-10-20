import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { CalendarBlank, Check, Minus, Plus, Trash, Warning, WarningCircle } from "@phosphor-icons/react";
import { Bouton, Icone3D } from "../ui";
import { ICONES_3D } from "../../icones3d";
import type { AnalyseCompteRanger, TypePost, VueCompte } from "../../engine/api";
import { erreurNomCompte } from "../../engine/useRanger";
import { fr, pluriel } from "../../fr";

/* ---------- État des dossiers d'un compte (pastille verte / alerte) ---------- */

export type EtatCompte = { ton: "ok" | "attention" | "probleme" | "neutre"; texte: string };

/** Deux chemins désignent le même dossier (casse et « \ » final ignorés, comme Windows). */
const memeDossier = (a: string | null | undefined, b: string | null | undefined) =>
  !!a && !!b && a.replace(/[\\/]+$/, "").toLowerCase() === b.replace(/[\\/]+$/, "").toLowerCase();

/**
 * Où en est un compte : dossiers à choisir, dossier introuvable, médias manquants, ou prêt.
 * L'analyse du moteur ne compte que pour les dossiers qu'elle a VRAIMENT vus (pendant qu'elle se
 * refait après un changement, l'ancienne ne doit pas afficher une alerte périmée).
 */
export function etatCompte(c: VueCompte, actifs: TypePost[], a: AnalyseCompteRanger | null): EtatCompte {
  if (!actifs.length) return { ton: "neutre", texte: "Aucun type à ranger : compte ignoré" };
  const sans = actifs.filter((t) => !c.sources[t]);
  if (sans.length) return { ton: "attention", texte: sans.length === actifs.length && sans.length > 1 ? "Dossiers à choisir" : `${pluriel(sans.length, "dossier")} à choisir` };
  if (a?.calendrier_erreur) return { ton: "probleme", texte: "Calendrier à corriger" };
  const vus = actifs.map((t) => (a && memeDossier(a.types[t]?.dossier, c.sources[t]) ? a.types[t] : null));
  if (vus.some((x) => x && !x.dossier_valide)) return { ton: "probleme", texte: "Dossier introuvable" };
  if (a && actifs.some((t, i) => vus[i] && a.source_dans_sortie.includes(t))) return { ton: "probleme", texte: "Dossier dans la sortie" };
  if (vus.some((x) => x && x.manque > 0)) return { ton: "attention", texte: "Médias manquants" };
  return { ton: "ok", texte: "Dossiers prêts" };
}

/** La petite icône de l'état (décorative : le texte, ou l'aria-label de l'onglet, le dit déjà). */
function IconeEtat({ e, className = "h-3.5 w-3.5" }: { e: EtatCompte; className?: string }) {
  if (e.ton === "ok") return <Check weight="bold" className={`${className} shrink-0 text-success-text`} aria-hidden="true" />;
  if (e.ton === "attention") return <Warning weight="fill" className={`${className} shrink-0 text-warning`} aria-hidden="true" />;
  if (e.ton === "probleme") return <WarningCircle weight="fill" className={`${className} shrink-0 text-danger`} aria-hidden="true" />;
  return null;
}

const COULEUR_ETAT: Record<EtatCompte["ton"], string> = {
  ok: "text-success-text",
  attention: "text-warning",
  probleme: "text-danger",
  neutre: "text-fg-3",
};

/* ---------- « − n + » : le nombre de comptes ---------- */

/**
 * Le nombre de comptes : − / + ou saisie au clavier. La saisie n'est appliquée qu'avec Entrée ou en
 * quittant le champ (taper « 12 » ne doit pas d'abord retirer tous les comptes sauf 1).
 * Flèches haut / bas dans le champ : un de plus / un de moins.
 * − / + et les flèches envoient « un de plus / de moins que le nombre ACTUEL » (une fonction), pas
 * `valeur + 1` : `valeur` ne change qu'à la réponse du moteur, deux clics rapides donneraient sinon
 * deux fois le même nombre.
 */
export function SelecteurNombre({
  valeur,
  min = 1,
  max,
  onChange,
  disabled = false,
  idLibelle,
}: {
  valeur: number;
  min?: number;
  max: number;
  onChange: (n: number | ((actuel: number) => number)) => void;
  disabled?: boolean;
  /** id du texte « Nombre de comptes » (nom du groupe pour les lecteurs d'écran) */
  idLibelle: string;
}) {
  const [brouillon, setBrouillon] = useState(String(valeur));
  useEffect(() => setBrouillon(String(valeur)), [valeur]);

  const valider = () => {
    const n = Number.parseInt(brouillon, 10);
    // On réaffiche la valeur actuelle : la nouvelle arrive avec la réponse du moteur
    // (ou jamais, si une confirmation est refusée).
    setBrouillon(String(valeur));
    if (!Number.isFinite(n)) return;
    const borne = Math.min(Math.max(n, min), max);
    if (borne !== valeur) onChange(borne);
  };

  const touche = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      valider();
    } else if (e.key === "Escape" && brouillon !== String(valeur)) {
      e.preventDefault();
      setBrouillon(String(valeur));
    } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault();
      const pas = e.key === "ArrowUp" ? 1 : -1;
      if (valeur + pas >= min && valeur + pas <= max) onChange((actuel) => actuel + pas);
    }
  };

  // À la borne (1 compte, ou le maximum), « − » / « + » sont aria-disabled et pas disabled : un
  // bouton disabled perd le focus (il part sur la page, et le Tab suivant repart du haut).
  const moinsBloque = valeur <= min;
  const plusBloque = valeur >= max;
  const bouton =
    "grid h-full w-9 place-items-center text-fg-2 transition-colors duration-150 hover:bg-fg/[0.05] hover:text-fg disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-fg-2 aria-disabled:cursor-default aria-disabled:opacity-40 aria-disabled:hover:bg-transparent aria-disabled:hover:text-fg-2";
  return (
    <div
      role="group"
      aria-labelledby={idLibelle}
      className="inline-flex h-9 items-center overflow-hidden rounded-[10px] border border-line-2 bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:bg-white/[0.03]"
    >
      <button
        type="button"
        onClick={() => !moinsBloque && onChange((actuel) => actuel - 1)}
        disabled={disabled}
        aria-disabled={moinsBloque || undefined}
        aria-label="Un compte de moins"
        className={bouton}
      >
        <Minus weight="bold" className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      <input
        id="nombre-comptes"
        value={brouillon}
        onChange={(e) => setBrouillon(e.target.value.replace(/\D/g, "").slice(0, String(max).length))}
        onBlur={valider}
        onKeyDown={touche}
        inputMode="numeric"
        autoComplete="off"
        aria-label={`Nombre de comptes (de ${min} à ${max})`}
        disabled={disabled}
        className="selectable tabular h-full w-12 border-x border-line bg-transparent text-center text-14 font-semibold outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand disabled:opacity-60"
      />
      <button
        type="button"
        onClick={() => !plusBloque && onChange((actuel) => actuel + 1)}
        disabled={disabled}
        aria-disabled={plusBloque || undefined}
        aria-label="Un compte de plus"
        className={bouton}
      >
        <Plus weight="bold" className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

/* ---------- Une ligne de la liste des comptes (étape 1) ---------- */

/**
 * Un compte : son nom (renommable sur place avec le crayon), le résumé de son calendrier, l'état de
 * ses dossiers, « Calendrier » et, s'il y a plusieurs comptes, « Supprimer ».
 * Cliquer la ligne choisit le compte pour l'étape 2 (au clavier : les onglets des comptes, étape 2).
 */
export function LigneCompte({
  c,
  numero,
  choisi,
  plusieurs,
  etat,
  erreurCalendrier,
  autresNoms,
  occupe,
  choisir,
  renommer,
  ouvrirCalendrier,
  supprimer,
}: {
  c: VueCompte;
  /** 1, 2, 3… (position dans la liste) */
  numero: number;
  choisi: boolean;
  plusieurs: boolean;
  etat: EtatCompte;
  erreurCalendrier: string | null;
  /** noms des AUTRES comptes (un nom doit être unique) */
  autresNoms: string[];
  occupe: boolean;
  choisir: () => void;
  renommer: (nom: string) => Promise<boolean>;
  ouvrirCalendrier: () => void;
  supprimer: () => void;
}) {
  const idAide = useId();
  /** le nom en cours de saisie (null = pas en train de renommer) */
  const [edition, setEdition] = useState<string | null>(null);
  const champ = useRef<HTMLInputElement>(null);
  const crayon = useRef<HTMLButtonElement>(null);
  // Entrée / Échap ferment le champ : le « blur » qui suit ne doit pas valider une 2e fois.
  const termine = useRef(false);
  const enEdition = edition !== null;
  const probleme = edition !== null ? erreurNomCompte(edition, autresNoms) : null;

  // Le champ apparaît : focus dedans, nom sélectionné (on tape directement le nouveau).
  useEffect(() => {
    if (!enEdition) return;
    champ.current?.focus();
    champ.current?.select();
  }, [enEdition]);

  const commencer = () => {
    termine.current = false;
    setEdition(c.nom);
    choisir();
  };

  const finir = (garder: boolean, rendreFocus: boolean) => {
    if (termine.current || edition === null) return;
    const nom = edition.trim();
    // Entrée sur un nom refusé : on reste dans le champ (le message dit pourquoi).
    if (garder && rendreFocus && erreurNomCompte(nom, autresNoms)) return;
    termine.current = true;
    setEdition(null);
    if (rendreFocus) requestAnimationFrame(() => crayon.current?.focus());
    if (garder && nom !== c.nom && !erreurNomCompte(nom, autresNoms)) void renommer(nom);
  };

  const touche = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      finir(true, true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      finir(false, true);
    }
  };

  const resume = fr(
    `${pluriel(c.vue.semaines, "semaine")} · ${c.vue.creneaux} créneau${c.vue.creneaux > 1 ? "x" : ""} · ${
      c.vue.personnalise ? "Personnalisé" : "Calendrier d'origine"
    }`,
  );

  return (
    <li
      onClick={choisir}
      aria-current={plusieurs && choisi ? "true" : undefined}
      className={`flex flex-wrap items-center gap-x-3 gap-y-2.5 rounded-xl border p-3 transition-colors duration-150 ${
        plusieurs && choisi ? "border-brand/30 bg-brand-soft" : "border-line bg-surface-2/60 hover:border-line-2"
      }`}
    >
      <span
        aria-hidden="true"
        className={`tabular grid h-9 w-9 shrink-0 place-items-center rounded-[10px] border text-13 font-semibold ${
          plusieurs && choisi ? "border-brand/30 bg-brand-btn text-white" : "border-line bg-surface text-fg-2"
        }`}
      >
        {numero}
      </span>
      <div className="min-w-[160px] flex-1">
        {enEdition ? (
          <div onClick={(e) => e.stopPropagation()}>
            <input
              ref={champ}
              value={edition ?? ""}
              onChange={(e) => setEdition(e.target.value)}
              onKeyDown={touche}
              onBlur={() => finir(true, false)}
              maxLength={40}
              spellCheck={false}
              autoComplete="off"
              aria-label={`Nouveau nom de « ${c.nom} »`}
              aria-invalid={!!probleme || undefined}
              aria-describedby={idAide}
              className="selectable h-8 w-full max-w-[280px] rounded-lg border border-line-2 bg-surface px-2.5 text-14 font-semibold outline-none transition-[border-color,box-shadow] duration-150 focus:border-brand focus:shadow-[0_0_0_3px_var(--brand-soft)] aria-[invalid=true]:border-danger"
            />
            <p id={idAide} className={`mt-1 text-12 ${probleme ? "text-danger" : "text-fg-3"}`}>
              {/* Avec 1 seul compte, le rangement garde l'arborescence d'avant (pas de dossier au nom du compte). */}
              {fr(
                probleme ??
                  `Entrée pour valider, Échap pour annuler. ${
                    plusieurs ? "Ce nom sera celui du dossier du compte." : "Il servira de nom de dossier dès que vous aurez plusieurs comptes."
                  }`,
              )}
            </p>
          </div>
        ) : (
          <div className="flex min-w-0 items-center gap-0.5">
            <p className="truncate text-14 font-semibold" title={c.nom}>
              {c.nom}
              {plusieurs && choisi && <span className="sr-only"> (affiché à l'étape 2)</span>}
            </p>
            <button
              ref={crayon}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                commencer();
              }}
              disabled={occupe}
              aria-label={`Renommer « ${c.nom} »`}
              title="Renommer"
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg transition-colors duration-150 hover:bg-fg/[0.06] disabled:opacity-50"
            >
              <Icone3D src={ICONES_3D.crayon} taille={18} />
            </button>
          </div>
        )}
        <p className="tabular text-12 text-fg-2">{resume}</p>
        <p className={`mt-0.5 flex items-center gap-1.5 text-12 ${COULEUR_ETAT[etat.ton]}`}>
          <IconeEtat e={etat} />
          {fr(etat.texte)}
        </p>
        {erreurCalendrier && (
          <p role="alert" className="mt-1 flex items-start gap-1.5 whitespace-pre-line text-12 text-danger">
            <Warning weight="fill" className="mt-[2px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {fr(erreurCalendrier)}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Bouton
          id={`calendrier-${c.id}`}
          taille="sm"
          onClick={(e) => {
            e.stopPropagation();
            choisir();
            ouvrirCalendrier();
          }}
          disabled={occupe}
          aria-label={`Calendrier de « ${c.nom} »`}
        >
          <CalendarBlank className="h-4 w-4 text-fg-2" aria-hidden="true" />
          Calendrier
        </Bouton>
        {plusieurs && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              supprimer();
            }}
            disabled={occupe}
            aria-label={`Supprimer « ${c.nom} »`}
            title="Supprimer ce compte"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-danger transition-colors duration-150 hover:bg-danger/10 disabled:opacity-50 disabled:hover:bg-transparent"
          >
            <Trash className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>
    </li>
  );
}

/* ---------- Les onglets des comptes (étape 2, à partir de 2 comptes) ---------- */

/**
 * Une pastille par compte (de vrais onglets : flèches gauche / droite, Début / Fin), avec l'état
 * de ses dossiers. Le panneau `panneau-compte` (les onglets des types) suit le compte choisi.
 */
export function OngletsComptes({
  comptes,
  actif,
  etats,
  choisir,
}: {
  comptes: VueCompte[];
  actif: string | null;
  etats: Record<string, EtatCompte>;
  choisir: (id: string) => void;
}) {
  const onglets = useRef<Record<string, HTMLButtonElement | null>>({});
  const fleche = (e: KeyboardEvent, i: number) => {
    const cible =
      e.key === "ArrowRight"
        ? comptes[i + 1]
        : e.key === "ArrowLeft"
          ? comptes[i - 1]
          : e.key === "Home"
            ? comptes[0]
            : e.key === "End"
              ? comptes[comptes.length - 1]
              : null;
    if (!cible) return;
    e.preventDefault();
    choisir(cible.id);
    onglets.current[cible.id]?.focus();
  };

  return (
    <div role="tablist" aria-label="Comptes" className="scroll-fin -mx-1 mt-4 flex max-h-[128px] flex-wrap gap-1.5 overflow-y-auto p-1">
      {comptes.map((c, i) => {
        const choisi = c.id === actif;
        const e = etats[c.id];
        return (
          <button
            key={c.id}
            id={`onglet-compte-${c.id}`}
            ref={(el) => {
              onglets.current[c.id] = el;
            }}
            type="button"
            role="tab"
            aria-selected={choisi}
            aria-controls="panneau-compte"
            tabIndex={choisi ? 0 : -1}
            onClick={() => choisir(c.id)}
            onKeyDown={(ev) => fleche(ev, i)}
            title={e ? `${c.nom} · ${e.texte}` : c.nom}
            className={`flex h-8 max-w-[220px] items-center gap-1.5 rounded-full border px-3 text-13 font-medium transition-colors duration-150 ${
              choisi ? "border-brand/40 bg-brand-soft text-brand-text" : "border-line bg-surface text-fg-2 hover:border-line-2 hover:text-fg"
            }`}
          >
            <span className="truncate">{c.nom}</span>
            {e && <IconeEtat e={e} />}
            {/* L'état, lu avec le nom de l'onglet (l'icône seule ne dit rien aux lecteurs d'écran). */}
            {e && <span className="sr-only">{fr(` : ${e.texte}`)}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** « A », « A et B », « A, B et C ». */
export function enumerer(mots: string[]): string {
  return mots.length < 2 ? (mots[0] ?? "") : `${mots.slice(0, -1).join(", ")} et ${mots[mots.length - 1]}`;
}
