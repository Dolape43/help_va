import { ArrowCounterClockwise, WarningCircle } from "@phosphor-icons/react";
import { Bouton, Carte, Case, Rouage, Segments, Surtitre, TitrePage, Tuile3D } from "../components/ui";
import { ICONES_3D } from "../icones3d";
import Dialogue from "../components/Dialogue";
import { useState, type ReactNode } from "react";
import type { Preferences, StatutLicence } from "../engine/api";
import { dateLongue, nomLicence } from "../licence";
import { messageErreur } from "../erreurs";
import { fr } from "../fr";

/**
 * Paramètres : dossier de sortie (lu et modifié via le moteur), choix par défaut des modules,
 * fin de traitement, et licence (avec la résiliation).
 */
export default function Parametres({
  sortie,
  personnalise,
  licence,
  formule,
  changerSortie,
  reinitialiserSortie,
  ouvrirSortie,
  resilier,
  saisirCode,
  prefs,
  changerPref,
  bandeau,
}: {
  sortie: string | null;
  /** dossier de sortie choisi par l'utilisateur (sinon : Bureau\HelpVA par défaut) */
  personnalise: boolean;
  licence: StatutLicence | null;
  /** « Abonnement mensuel »… (calculé par App, qui connaît aussi le mode développement) */
  formule: string;
  changerSortie: () => void;
  /** retour au dossier par défaut (Bureau\HelpVA) */
  reinitialiserSortie: () => void;
  ouvrirSortie: () => void;
  /** supprime la licence de ce PC ; l'écran d'activation prend alors le relais */
  resilier: () => Promise<void>;
  /** offre gratuite : ouvre l'écran du code d'activation */
  saisirCode: () => void;
  /** choix par défaut et fin de traitement (enregistrés dans parametres.json par App) */
  prefs: Preferences;
  changerPref: <K extends keyof Preferences>(cle: K, valeur: Preferences[K]) => void;
  bandeau: ReactNode;
}) {
  const [confirmer, setConfirmer] = useState(false);
  const [resiliation, setResiliation] = useState(false);
  const [erreurResiliation, setErreurResiliation] = useState<string | null>(null);

  const ouvrirConfirmation = () => {
    setErreurResiliation(null);
    setConfirmer(true);
  };
  const confirmerResiliation = async () => {
    if (resiliation) return;
    setResiliation(true);
    setErreurResiliation(null);
    try {
      await resilier(); // réussite : l'app passe à l'écran d'activation, cet écran disparaît
    } catch (e) {
      setErreurResiliation(messageErreur(e));
      setResiliation(false);
    }
  };

  const gratuit = licence?.type === "gratuit"; // offre gratuite : pas de licence à résilier
  const aVie = licence?.ok && !gratuit && (licence.type === "vie" || !licence.expire_le);
  const debut = dateLongue(licence?.debut_le);
  const fin = dateLongue(licence?.expire_le);

  return (
    <div className="entree mx-auto max-w-[760px] px-6 pb-10 pt-9 @min-[700px]:px-10">
      {bandeau}
      <TitrePage>Paramètres</TitrePage>
      <p className="mt-1.5 text-14 text-fg-2">Dossier de sortie, choix par défaut, fin de traitement et licence.</p>

      <Carte className="mt-7 p-5">
        <div className="flex items-start gap-3">
          <Tuile3D src={ICONES_3D.dossier} taille={52} />
          <div className="min-w-0 flex-1">
            <p className="text-16 font-semibold">Dossier de sortie</p>
            <p className="text-13 text-fg-2">
              Emplacement où vos fichiers préparés sont enregistrés{personnalise ? "." : " (par défaut : Bureau)."}
            </p>
            <p className="selectable mt-3 truncate rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-12" title={sortie ?? undefined}>
              {sortie ?? "Chargement…"}
            </p>
            <div className="mt-3 flex gap-2">
              <Bouton id="bouton-changer-sortie" taille="sm" variante="primaire" onClick={changerSortie}>
                Changer…
              </Bouton>
              <Bouton taille="sm" onClick={ouvrirSortie} disabled={!sortie}>
                Ouvrir
              </Bouton>
              {personnalise && (
                <Bouton
                  taille="sm"
                  variante="fantome"
                  onClick={() => {
                    document.getElementById("bouton-changer-sortie")?.focus();
                    reinitialiserSortie();
                  }}
                >
                  <ArrowCounterClockwise className="h-4 w-4" />
                  Réinitialiser (Bureau)
                </Bouton>
              )}
            </div>
          </div>
        </div>
      </Carte>

      <Carte className="mt-4 p-5">
        <div className="flex items-start gap-3">
          <Tuile3D src={ICONES_3D.parametres} taille={52} />
          <div className="min-w-0 flex-1">
            <h2 className="text-16 font-semibold">Choix par défaut</h2>
            <p className="text-13 text-fg-2">
              {fr("Retenus d'une fois sur l'autre. Vous pouvez aussi les changer dans chaque module.")}
            </p>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <span className="text-14" aria-hidden="true">
                Format des images
              </span>
              <Segments
                nom="parametres-format-images"
                libelle="Format des images converties"
                valeur={prefs.format_images}
                onChange={(v) => changerPref("format_images", v)}
                choix={[
                  { valeur: "jpg", libelle: "JPG" },
                  { valeur: "png", libelle: "PNG" },
                ]}
              />
            </div>

            <div className="mt-5">
              <Surtitre>{fr("Renommer 1, 2, 3…")}</Surtitre>
              <div className="mt-2.5 flex flex-col gap-2.5">
                <Case coche={prefs.renommer_images} onChange={(v) => changerPref("renommer_images", v)} aide="Convertir des images">
                  Images
                </Case>
                <Case coche={prefs.renommer_mp4} onChange={(v) => changerPref("renommer_mp4", v)} aide="Convertir en MP4">
                  Vidéos MP4
                </Case>
                <Case
                  coche={prefs.renommer_metadonnees}
                  onChange={(v) => changerPref("renommer_metadonnees", v)}
                  aide="Changer les métadonnées (recommandé)"
                >
                  Métadonnées
                </Case>
              </div>
            </div>

            <div className="mt-5">
              <Surtitre>Ranger les médias</Surtitre>
              <Case
                className="mt-2.5"
                coche={prefs.ranger_aleatoire}
                onChange={(v) => changerPref("ranger_aleatoire", v)}
                aide={fr("Les carrousels gardent toujours l'ordre 1, 2, 3…")}
              >
                Répartir au hasard
              </Case>
            </div>
          </div>
        </div>
      </Carte>

      <Carte className="mt-4 p-5">
        <div className="flex items-start gap-3">
          <Tuile3D src={ICONES_3D.succes} taille={52} />
          <div className="min-w-0 flex-1">
            <h2 className="text-16 font-semibold">Fin de traitement</h2>
            <p className="text-13 text-fg-2">Ce que fait HelpVA quand une conversion ou un rangement se termine.</p>
            <div className="mt-4 flex flex-col gap-2.5">
              <Case
                coche={prefs.fin_ouvrir_dossier}
                onChange={(v) => changerPref("fin_ouvrir_dossier", v)}
                aide="L'Explorateur s'ouvre tout seul sur vos fichiers prêts."
              >
                Ouvrir le dossier du résultat
              </Case>
              <Case
                coche={prefs.fin_notification}
                onChange={(v) => changerPref("fin_notification", v)}
                aide="Seulement si HelpVA n'est pas au premier plan."
              >
                Me prévenir par une notification
              </Case>
            </div>
          </div>
        </div>
      </Carte>

      <Carte className="mt-4 p-5">
        <div className="flex items-start gap-3">
          <Tuile3D src={ICONES_3D.licence} taille={52} />
          <div className="min-w-0 flex-1">
            <p className="text-16 font-semibold">Licence &amp; abonnement</p>
            <dl className="mt-3 grid grid-cols-[170px_1fr] gap-y-2 text-13">
              <dt className="text-fg-3">Détenteur</dt>
              <dd id="parametres-detenteur" className="font-medium">
                {nomLicence(licence) ?? "—"}
              </dd>
              <dt className="text-fg-3">Formule</dt>
              <dd id="parametres-formule">{aVie ? "Licence à vie — sans expiration" : formule}</dd>
              {!aVie && debut && (
                <>
                  <dt className="text-fg-3">Début de l'abonnement</dt>
                  <dd className="tabular">{debut}</dd>
                </>
              )}
              {!aVie && fin && (
                <>
                  <dt className="text-fg-3">{licence?.type === "essai" ? "Fin de l'essai" : "Fin de l'abonnement"}</dt>
                  <dd className="tabular">{fin}</dd>
                </>
              )}
            </dl>
            {gratuit ? (
              <Bouton taille="sm" variante="primaire" className="mt-4" onClick={saisirCode}>
                J'ai déjà une licence
              </Bouton>
            ) : (
              <Bouton taille="sm" variante="danger" className="mt-4" onClick={ouvrirConfirmation}>
                Résilier / changer de licence
              </Bouton>
            )}
          </div>
        </div>
      </Carte>

      <Dialogue
        ouvert={confirmer}
        fermer={() => setConfirmer(false)}
        occupe={resiliation}
        ton="danger"
        icone={<WarningCircle weight="duotone" className="h-6 w-6" />}
        image={ICONES_3D.alerte}
        titre="Résilier la licence de ce PC ?"
        actions={
          <>
            <Bouton data-autofocus onClick={resiliation ? undefined : () => setConfirmer(false)} aria-disabled={resiliation || undefined}>
              Annuler
            </Bouton>
            <Bouton variante="alerte" onClick={confirmerResiliation}
              aria-disabled={resiliation || undefined}
            >
              {resiliation ? (
                <>
                  <Rouage />
                  Résiliation…
                </>
              ) : (
                "Résilier la licence"
              )}
            </Bouton>
          </>
        }
      >
        <p>{fr("La licence sera supprimée de ce PC et HelpVA reviendra à l'écran d'activation.")}</p>
        <p className="mt-3 rounded-xl border border-danger/20 bg-danger/[0.06] px-3.5 py-2.5 text-13 text-fg">
          {fr("Votre code d'activation a déjà servi : il faudra un NOUVEAU code fourni par le vendeur pour réactiver HelpVA.")}
        </p>
        {erreurResiliation && (
          <p role="alert" className="mt-3 flex items-start gap-1.5 text-13 text-danger">
            <WarningCircle weight="fill" className="mt-px h-4 w-4 shrink-0" aria-hidden="true" />
            {fr(erreurResiliation)}
          </p>
        )}
      </Dialogue>
    </div>
  );
}
