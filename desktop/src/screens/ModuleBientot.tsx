import { Hammer } from "@phosphor-icons/react";
import { Bouton, Carte } from "../components/ui";
import EnteteModule from "../components/EnteteModule";
import { moduleParCle, type CleModule } from "../modules";
import { fr } from "../fr";

/** Les 3 autres modules ne sont pas encore branchés dans la nouvelle interface : écran d'attente propre. */
export default function ModuleBientot({ cle, retour, voirMp4 }: { cle: CleModule; retour: () => void; voirMp4: () => void }) {
  const mod = moduleParCle(cle);
  return (
    <div className="entree mx-auto max-w-[760px] px-6 pb-10 pt-6 @min-[700px]:px-10">
      <EnteteModule mod={mod} sousTitre={mod.texte} retour={retour} />
      <Carte className="mt-7 flex flex-col items-center px-8 py-12 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-2xl border border-line bg-surface-2 text-fg-3">
          <Hammer weight="duotone" className="h-6 w-6" />
        </span>
        <p className="mt-4 text-16 font-semibold">Bientôt dans la nouvelle interface</p>
        <p className="mt-1 max-w-sm text-13 text-fg-2">
          {fr("Ce module marche déjà dans l'application actuelle. Ici, seul « Convertir en MP4 » est branché sur le moteur pour l'instant.")}
        </p>
        <Bouton variante="primaire" className="mt-5" onClick={voirMp4}>
          {fr("Voir « Convertir en MP4 »")}
        </Bouton>
      </Carte>
    </div>
  );
}
