import { ArrowSquareOut, FolderSimple, IdentificationCard, PencilSimple } from "@phosphor-icons/react";
import { Bouton, Carte, PastilleIcone, Surtitre, TitrePage } from "../components/ui";
import { useEffect, useState, type ReactNode } from "react";
import { versionApp } from "../plateforme";
import type { InfoMoteur, StatutLicence } from "../engine/api";
import { dateLongue, libelleFormule, nomLicence } from "../licence";

/** Paramètres : dossier de sortie (lu et modifié via le moteur) et licence (lecture seule ici). */
export default function Parametres({
  sortie,
  licence,
  info,
  transport,
  changerSortie,
  ouvrirSortie,
  notifier,
  bandeau,
}: {
  sortie: string | null;
  licence: StatutLicence | null;
  info: InfoMoteur | null;
  transport: string;
  changerSortie: () => void;
  ouvrirSortie: () => void;
  notifier: (titre: string, texte: string) => void;
  bandeau: ReactNode;
}) {
  const [version, setVersion] = useState(__APP_VERSION__);
  useEffect(() => {
    versionApp().then(setVersion);
  }, []);
  const fin = dateLongue(licence?.expire_le);
  return (
    <div className="entree mx-auto max-w-[760px] px-6 pb-10 pt-9 @min-[700px]:px-10">
      {bandeau}
      <TitrePage>Paramètres</TitrePage>
      <p className="mt-1.5 text-14 text-fg-2">Dossier de sortie et licence.</p>

      <Carte className="mt-7 p-5">
        <div className="flex items-start gap-3">
          <PastilleIcone>
            <FolderSimple weight="duotone" className="h-5 w-5" />
          </PastilleIcone>
          <div className="min-w-0 flex-1">
            <p className="text-16 font-semibold">Dossier de sortie</p>
            <p className="text-13 text-fg-2">Emplacement où vos fichiers préparés sont enregistrés.</p>
            <p className="selectable mt-3 truncate rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-12" title={sortie ?? undefined}>
              {sortie ?? "Chargement…"}
            </p>
            <div className="mt-3 flex gap-2">
              <Bouton taille="sm" variante="primaire" onClick={changerSortie}>
                <PencilSimple className="h-4 w-4" />
                Changer…
              </Bouton>
              <Bouton taille="sm" onClick={ouvrirSortie} disabled={!sortie}>
                <ArrowSquareOut className="h-4 w-4" />
                Ouvrir
              </Bouton>
            </div>
          </div>
        </div>
      </Carte>

      <Carte className="mt-4 p-5">
        <div className="flex items-start gap-3">
          <PastilleIcone>
            <IdentificationCard weight="duotone" className="h-5 w-5" />
          </PastilleIcone>
          <div className="min-w-0 flex-1">
            <p className="text-16 font-semibold">Licence &amp; abonnement</p>
            <dl className="mt-3 grid grid-cols-[160px_1fr] gap-y-2 text-13">
              <dt className="text-fg-3">Détenteur</dt>
              <dd className="font-medium">{nomLicence(licence) ?? "—"}</dd>
              <dt className="text-fg-3">Formule</dt>
              <dd>{libelleFormule(licence)}</dd>
              {fin && (
                <>
                  <dt className="text-fg-3">Fin de l'abonnement</dt>
                  <dd className="tabular">{fin}</dd>
                </>
              )}
            </dl>
            <Bouton
              taille="sm"
              variante="danger"
              className="mt-4"
              onClick={() => notifier("Licence", "Pas encore disponible dans la nouvelle interface : utilisez l'application actuelle.")}
            >
              Résilier / changer de licence
            </Bouton>
          </div>
        </div>
      </Carte>

      <div className="mt-6">
        <Surtitre>À propos</Surtitre>
        <p className="mt-1.5 text-13 text-fg-3">
          HelpVA {version} · interface Tauri v2 (React) ·{" "}
          {info ? `moteur ${info.version} (Python ${info.python}, ${transport})` : `moteur : ${transport}`}
        </p>
      </div>
    </div>
  );
}
