import type { ComponentProps, ReactNode } from "react";

/** Petit titre en majuscules (« DOSSIER DE SORTIE », « SOURCE SÉLECTIONNÉE »…). */
export function Surtitre({ children, accent = false }: { children: ReactNode; accent?: boolean }) {
  return (
    <p className={`text-11 font-semibold uppercase tracking-[0.12em] ${accent ? "text-brand-text" : "text-fg-3"}`}>
      {children}
    </p>
  );
}

/** LE titre de page : même taille et même graisse sur tous les écrans. */
export function TitrePage({ children }: { children: ReactNode }) {
  return <h1 className="text-28 font-semibold leading-tight">{children}</h1>;
}

/** Carte : fond, fine bordure, ombre douce. */
export function Carte({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-line bg-surface shadow-card ${className}`}>{children}</div>;
}

/** danger = action à risque discrète (fond rouge pâle) ; alerte = LA confirmation d'une action grave (rouge plein). */
type Variante = "primaire" | "secondaire" | "fantome" | "danger" | "alerte";
type Taille = "sm" | "md" | "lg";

/**
 * Bouton : retour visuel au survol (150 ms) et au clic (léger enfoncement).
 * `aria-disabled` (au lieu de `disabled`) garde le focus clavier sur le bouton tout en le grisant :
 * utile quand un bouton change d'état pendant qu'on est dessus (« Annuler » → « Annulation… »).
 */
export function Bouton({
  variante = "secondaire",
  taille = "md",
  className = "",
  children,
  ...props
}: ComponentProps<"button"> & { variante?: Variante; taille?: Taille }) {
  const base =
    "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap font-medium transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-out active:scale-[0.98] disabled:opacity-60 disabled:active:scale-100 aria-disabled:cursor-default aria-disabled:opacity-60 aria-disabled:active:scale-100";
  const tailles = {
    sm: "h-8 rounded-lg px-3 text-13",
    md: "h-9 rounded-[10px] px-3.5 text-14",
    lg: "h-12 rounded-xl px-5 text-16",
  }[taille];
  const variantes = {
    // Fond #3a5cff (et non #4c6fff) : le texte blanc atteint 5:1, le niveau AA.
    primaire:
      "bg-brand-btn text-white shadow-[0_1px_0_rgba(255,255,255,0.18)_inset,0_10px_30px_-12px_rgba(76,111,255,0.75)] hover:bg-brand-deep",
    secondaire:
      "border border-line-2 bg-surface text-fg shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:border-fg-3/40 hover:bg-surface-2 dark:bg-white/[0.03] dark:hover:bg-white/[0.07]",
    fantome: "text-fg-2 hover:bg-fg/[0.05] hover:text-fg",
    danger: "bg-danger/10 text-danger hover:bg-danger/15",
    alerte: "bg-danger-btn text-white shadow-[0_1px_0_rgba(255,255,255,0.15)_inset] hover:bg-danger-btn-hover",
  }[variante];
  return (
    <button type="button" className={`${base} ${tailles} ${variantes} ${className}`} {...props}>
      {children}
    </button>
  );
}

export type Ton = "brand" | "warning" | "danger" | "success" | "neutre";

const TONS: Record<Ton, string> = {
  brand: "border-brand/15 bg-brand-soft text-brand-text",
  warning: "border-warning/20 bg-warning/10 text-warning",
  danger: "border-danger/20 bg-danger/10 text-danger",
  success: "border-success/20 bg-success/10 text-success",
  neutre: "border-line bg-surface-2 text-fg-3",
};

/** Pastille carrée qui porte une icône (Phosphor). Le ton dit la nature du message (accent, alerte…). */
export function PastilleIcone({
  children,
  taille = 40,
  ton = "brand",
  className = "",
}: {
  children: ReactNode;
  taille?: number;
  ton?: Ton;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-xl border ${TONS[ton]} ${className}`}
      style={{ width: taille, height: taille }}
    >
      {children}
    </span>
  );
}

/** Petit cercle qui tourne (chargement). Décoratif : le texte à côté dit ce qui se passe. */
export function Rouage({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={`tourne shrink-0 ${className}`}>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Case à cocher (vraie <input type="checkbox">, cachée mais présente : clavier, lecteur d'écran et
 * clic sur le texte marchent comme une case native). Le carré dessiné suit la valeur `coche`.
 */
export function Case({
  coche,
  onChange,
  children,
  aide,
  disabled = false,
  className = "",
}: {
  coche: boolean;
  onChange: (valeur: boolean) => void;
  children: ReactNode;
  /** petite phrase d'explication sous le libellé */
  aide?: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <label className={`flex items-start gap-3 ${disabled ? "cursor-default opacity-50" : "cursor-pointer"} ${className}`}>
      <input
        type="checkbox"
        className="peer sr-only"
        checked={coche}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span
        aria-hidden="true"
        className={`mt-[1px] grid h-[18px] w-[18px] shrink-0 place-items-center rounded-[5px] border transition-colors duration-150 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand ${
          coche ? "border-brand-btn bg-brand-btn text-white" : "border-line-2 bg-surface"
        }`}
      >
        {coche && (
          <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none">
            <path d="M2.5 6.2 5 8.5l4.5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>
      <span className="min-w-0">
        <span className="block text-14">{children}</span>
        {aide && <span className="mt-0.5 block text-12 text-fg-3">{aide}</span>}
      </span>
    </label>
  );
}

/**
 * Choix exclusif en « segments » (JPG | PNG…). Ce sont de vrais boutons radio : les flèches
 * du clavier passent d'un choix à l'autre, et Tab n'entre qu'une fois dans le groupe.
 */
export function Segments<T extends string>({
  nom,
  libelle,
  valeur,
  choix,
  onChange,
  disabled = false,
}: {
  /** nom du groupe radio (unique dans la page) */
  nom: string;
  /** libellé pour les lecteurs d'écran (« Format de sortie ») */
  libelle: string;
  valeur: T;
  choix: { valeur: T; libelle: ReactNode }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="inline-flex rounded-[10px] border border-line bg-fg/[0.04] p-0.5" disabled={disabled}>
      <legend className="sr-only">{libelle}</legend>
      {choix.map((c) => (
        <label key={c.valeur} className={disabled ? "cursor-default" : "cursor-pointer"}>
          <input
            type="radio"
            name={nom}
            value={c.valeur}
            checked={valeur === c.valeur}
            onChange={() => onChange(c.valeur)}
            className="peer sr-only"
          />
          <span className="flex h-8 min-w-16 items-center justify-center rounded-lg px-3.5 text-13 font-medium text-fg-2 transition-[background-color,color,box-shadow] duration-150 peer-checked:bg-surface peer-checked:text-fg peer-checked:shadow-[0_0_0_1px_var(--line),0_1px_2px_rgba(0,0,0,0.08)] peer-focus-visible:outline-2 peer-focus-visible:outline-offset-1 peer-focus-visible:outline-brand peer-disabled:opacity-60">
            {c.libelle}
          </span>
        </label>
      ))}
    </fieldset>
  );
}

/**
 * Une icône 3D (image à fond transparent, voir icones3d.ts), avec une ombre douce qui la pose
 * sur la page. Décorative : le texte à côté dit déjà ce qu'elle représente.
 */
export function Icone3D({ src, taille = 40, className = "" }: { src: string; taille?: number; className?: string }) {
  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      width={taille}
      height={taille}
      draggable={false}
      className={`shrink-0 select-none object-contain drop-shadow-[0_6px_12px_rgba(9,9,11,0.16)] dark:drop-shadow-[0_8px_16px_rgba(0,0,0,0.55)] ${className}`}
      style={{ width: taille, height: taille }}
    />
  );
}

/** Une icône 3D dans une tuile arrondie, comme les icônes des cartes de modules de l'accueil. */
export function Tuile3D({ src, taille = 48 }: { src: string; taille?: number }) {
  return (
    <span
      aria-hidden="true"
      className="grid shrink-0 place-items-center rounded-[14px] border border-line bg-[linear-gradient(180deg,var(--surface-2),var(--surface))]"
      style={{ width: taille, height: taille }}
    >
      <Icone3D src={src} taille={Math.round(taille * 0.74)} />
    </span>
  );
}

/** Le chiffre 3D d'une étape (1 à 4), foncé en thème clair et argenté en thème sombre. */
export function Chiffre3D({ n, taille = 44, fonce, clair }: { n: number; taille?: number; fonce: string; clair: string }) {
  return (
    <span aria-hidden="true" className="relative inline-grid shrink-0 place-items-center" style={{ width: taille, height: taille }} data-chiffre={n}>
      <Icone3D src={fonce} taille={taille} className="dark:hidden" />
      <Icone3D src={clair} taille={taille} className="hidden dark:block" />
    </span>
  );
}
