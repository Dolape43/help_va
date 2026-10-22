import { ICONES_3D } from "../icones3d";
import { lienVendeur, MESSAGES_VENDEUR } from "../licence";
import { ouvrirLien } from "../plateforme";

/**
 * « Contacter le support » : ouvre directement la conversation Telegram avec le vendeur, avec un
 * message déjà écrit. Toujours visible (barre latérale, pied des écrans de licence) : si
 * l'utilisateur est bloqué sur un écran ou a un problème, il sait où demander de l'aide.
 *
 * variante « ligne » : comme un lien de la barre latérale ; « discret » : petit lien de pied de page.
 */
export default function BoutonSupport({ variante = "ligne" }: { variante?: "ligne" | "discret" }) {
  const ouvrir = () => void ouvrirLien(lienVendeur(MESSAGES_VENDEUR.support));
  if (variante === "discret") {
    return (
      <button
        type="button"
        onClick={ouvrir}
        className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-12 font-medium text-fg-2 transition-colors duration-150 hover:bg-fg/[0.05] hover:text-fg"
      >
        <img src={ICONES_3D.telegram} alt="" className="h-4 w-4 object-contain" />
        Contacter le support
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={ouvrir}
      className="flex h-10 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left text-14 text-fg-2 transition-colors duration-150 hover:bg-fg/[0.05] hover:text-fg"
    >
      <img src={ICONES_3D.telegram} alt="" className="h-6 w-6 object-contain" />
      <span className="min-w-0 flex-1 truncate">Contacter le support</span>
    </button>
  );
}
