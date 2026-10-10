import { useEffect, useId, useRef, type ReactNode } from "react";
import { Icone3D, PastilleIcone, type Ton } from "./ui";

/**
 * Fenêtre de confirmation (modale), construite sur le <dialog> natif du navigateur.
 *
 * Pourquoi le natif : avec showModal(), le navigateur gère seul ce qui est difficile à bien faire
 * à la main — le focus reste DANS la fenêtre (Tab ne s'échappe pas), Échap la ferme, le reste de
 * l'app devient inerte, et à la fermeture le focus revient au bouton qui l'avait ouverte.
 *
 * Le bouton marqué `data-autofocus` reçoit le focus à l'ouverture : mettez-le sur le choix SANS
 * danger (« Annuler »), pour qu'un Entrée réflexe ne déclenche pas l'action grave.
 */
export default function Dialogue({
  ouvert,
  fermer,
  titre,
  icone,
  image,
  ton = "brand",
  occupe = false,
  children,
  actions,
}: {
  ouvert: boolean;
  fermer: () => void;
  titre: string;
  icone: ReactNode;
  /** icône 3D (voir icones3d.ts) : remplace la pastille si elle est donnée */
  image?: string;
  ton?: Ton;
  /** action en cours : Échap et le clic à côté ne ferment pas */
  occupe?: boolean;
  children: ReactNode;
  actions: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitre = useId();
  const idTexte = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (ouvert && !d.open) {
      d.showModal();
      d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    } else if (!ouvert && d.open) {
      d.close();
    }
  }, [ouvert]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitre}
      aria-describedby={idTexte}
      className="dialogue"
      // Échap : le navigateur veut fermer ; c'est NOUS qui décidons (pas pendant une action).
      // stopPropagation : dans React, « cancel » remonte aussi vers un <dialog> PARENT (éditeur de
      // calendrier) ; sans ça, Échap sur cette confirmation fermerait aussi la fenêtre du dessous.
      onCancel={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!occupe) fermer();
      }}
      // Le navigateur peut fermer la fenêtre de lui-même (Échap appuyé plusieurs fois de suite) :
      // on remet alors l'état à jour, sinon elle ne pourrait plus se rouvrir.
      onClose={(e) => {
        e.stopPropagation();
        if (ouvert && !ref.current?.open) fermer();
      }}
      // Clic sur le fond assombri (en dehors de la carte) = fermer.
      onClick={(e) => {
        if (e.target === e.currentTarget && !occupe) fermer();
      }}
    >
      <div className="w-[460px] max-w-full rounded-[20px] border border-line bg-surface p-6 shadow-pop">
        <div className="flex gap-4">
          {image ? (
            <Icone3D src={image} taille={48} />
          ) : (
            <PastilleIcone ton={ton} taille={44}>
              {icone}
            </PastilleIcone>
          )}
          <div className="min-w-0 flex-1 pt-0.5">
            <h2 id={idTitre} className="text-16 font-semibold">
              {titre}
            </h2>
            <div id={idTexte} className="mt-1.5 text-14 leading-relaxed text-fg-2">
              {children}
            </div>
          </div>
        </div>
        <div className="mt-6 flex flex-wrap justify-end gap-2">{actions}</div>
      </div>
    </dialog>
  );
}
