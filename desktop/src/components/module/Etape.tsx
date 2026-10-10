import type { ReactNode } from "react";
import { Check } from "@phosphor-icons/react";
import { Carte, Chiffre3D } from "../ui";
import { CHIFFRES_3D } from "../../icones3d";

/**
 * Une étape numérotée d'un module, présentée comme une frise verticale :
 *
 *   [1]  ┌ Choisir les vidéos ─────────────┐
 *    │   │ …                               │
 *    │   └─────────────────────────────────┘
 *   [2]  ┌ Options ────────────────────────┐
 *
 * Le chiffre 3D sert de repère, un fil relie les étapes, et une petite coche verte apparaît
 * sur le chiffre quand l'étape est faite (source choisie…). On voit d'un coup d'œil où on en est.
 */
export function Etape({
  numero,
  titre,
  sousTitre,
  action,
  fait = false,
  dernier = false,
  children,
}: {
  numero: number;
  titre: string;
  sousTitre?: ReactNode;
  /** bouton à droite du titre (« Modifier le calendrier ») */
  action?: ReactNode;
  /** étape terminée : coche verte sur le chiffre */
  fait?: boolean;
  /** dernière étape : pas de fil vers la suivante */
  dernier?: boolean;
  children?: ReactNode;
}) {
  const chiffre = CHIFFRES_3D[numero] ?? CHIFFRES_3D[1];
  return (
    <section className="relative grid grid-cols-[48px_minmax(0,1fr)] gap-x-4 pt-4">
      {!dernier && (
        // Le fil part sous le chiffre et descend jusqu'au chiffre de l'étape suivante.
        <span
          aria-hidden="true"
          className="absolute bottom-[-26px] left-[23px] top-[86px] w-[2px] rounded-full bg-[linear-gradient(to_bottom,var(--line-2),var(--line))]"
        />
      )}
      <div className="relative flex justify-center pt-4">
        <Chiffre3D n={numero} taille={48} fonce={chiffre.fonce} clair={chiffre.clair} />
        {fait && (
          <span className="entree absolute -right-1 top-3 grid h-5 w-5 place-items-center rounded-full bg-success text-white ring-2 ring-panel">
            <Check weight="bold" className="h-3 w-3" aria-hidden="true" />
          </span>
        )}
      </div>
      <Carte className="min-w-0 p-5">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-16 font-semibold">
              <span className="sr-only">Étape {numero} : </span>
              {titre}
              {fait && <span className="sr-only"> (faite)</span>}
            </h2>
            {sousTitre && <p className="text-13 text-fg-2">{sousTitre}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
        {children}
      </Carte>
    </section>
  );
}
