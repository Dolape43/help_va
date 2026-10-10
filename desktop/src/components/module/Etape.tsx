import type { ReactNode } from "react";
import { Info } from "@phosphor-icons/react";
import { Carte } from "../ui";

/**
 * Une étape numérotée d'un module (« 1 · Choisir les vidéos »), dans une carte.
 * Même présentation que l'ancienne app (_entete_etape) : pastille, titre, phrase.
 */
export function Etape({
  numero,
  titre,
  sousTitre,
  action,
  children,
  className = "mt-4",
}: {
  numero: number;
  titre: string;
  sousTitre?: ReactNode;
  /** bouton à droite du titre (« Modifier le calendrier ») */
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <Carte className={`p-5 ${className}`}>
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-soft text-13 font-semibold text-brand-text ring-1 ring-brand/20"
        >
          {numero}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-16 font-semibold">
            <span className="sr-only">Étape {numero} : </span>
            {titre}
          </h2>
          {sousTitre && <p className="text-13 text-fg-2">{sousTitre}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </Carte>
  );
}

/** « Ce que fait ce module » : l'encart d'explication en haut de chaque module. */
export function BlocInfo({ children }: { children: ReactNode }) {
  return (
    <div className="mt-6 flex gap-3 rounded-2xl border border-line p-4">
      <Info weight="duotone" className="mt-0.5 h-5 w-5 shrink-0 text-brand-text" aria-hidden="true" />
      <div>
        <p className="text-14 font-semibold">Ce que fait ce module</p>
        <div className="mt-1 text-13 leading-relaxed text-fg-2">{children}</div>
      </div>
    </div>
  );
}
