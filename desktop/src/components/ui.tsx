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

type Variante = "primaire" | "secondaire" | "fantome" | "danger";
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
  }[variante];
  return (
    <button type="button" className={`${base} ${tailles} ${variantes} ${className}`} {...props}>
      {children}
    </button>
  );
}

/** Pastille carrée qui porte une icône (Phosphor) dans l'accent. */
export function PastilleIcone({ children, taille = 40 }: { children: ReactNode; taille?: number }) {
  return (
    <span
      className="grid shrink-0 place-items-center rounded-xl border border-brand/15 bg-brand-soft text-brand-text"
      style={{ width: taille, height: taille }}
    >
      {children}
    </span>
  );
}
