import { ArrowRight } from "@phosphor-icons/react";
import { Bouton, Carte, Surtitre, TitrePage, Tuile3D } from "../components/ui";
import { ICONES_3D } from "../icones3d";
import { MODULES, type CleModule } from "../modules";
import type { ReactNode } from "react";
import type { Activite } from "../App";
import type { Compteurs, ResumeActivite } from "../engine/api";
import { dateLongue } from "../licence";
import { fr } from "../fr";

const dateDuJour = () => {
  const d = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" }).format(new Date());
  return d.charAt(0).toUpperCase() + d.slice(1);
};

/** 1234 → « 1 234 » (espace fine insécable : le nombre ne se coupe jamais en fin de ligne). */
const nombre = (n: number) => new Intl.NumberFormat("fr-FR").format(n);

/** Les 4 compteurs, dans l'ordre des modules. */
const REPARTITION: { cle: Exclude<keyof Compteurs, "total">; libelle: string }[] = [
  { cle: "images", libelle: "Images" },
  { cle: "videos", libelle: "Vidéos" },
  { cle: "metadonnees", libelle: "Métadonnées" },
  { cle: "ranges", libelle: "Rangés" },
];

/**
 * « Votre activité » : combien de médias ont été traités sur ce PC (compteurs du moteur,
 * commande activite_lire). Zéro activité : une phrase d'encouragement plutôt qu'une carte vide.
 */
function CarteActivite({ r }: { r: ResumeActivite }) {
  const depuis = dateLongue(r.depuis);
  // Répartition de la semaine (comme le grand chiffre) ; semaine vide : celle depuis le début.
  const semaineVide = r.semaine.total === 0;
  const detail = semaineVide ? r.total : r.semaine;
  return (
    <Carte className="mt-6 p-5">
      <section aria-label="Votre activité">
        <Surtitre accent>Votre activité</Surtitre>
        {r.total.total === 0 ? (
          <div className="mt-3 flex items-center gap-3">
            <Tuile3D src={ICONES_3D.succes} taille={52} />
            <p className="text-14 leading-relaxed text-fg-2">
              {fr("Votre compteur démarre à votre premier traitement : chaque média converti, modifié ou rangé sera compté ici.")}
            </p>
          </div>
        ) : (
          <>
            <div className="mt-3 grid grid-cols-1 gap-5 @min-[640px]:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] @min-[640px]:items-end">
              <div>
                <p id="accueil-activite-semaine" className="tabular text-[44px] font-semibold leading-none tracking-[-0.02em]">
                  {nombre(r.semaine.total)}
                </p>
                <p className="mt-1.5 text-13 text-fg-2">
                  {r.semaine.total > 1 ? "médias traités" : "média traité"} cette semaine
                </p>
              </div>
              <dl className="grid grid-cols-3 gap-3">
                {[
                  { libelle: "Aujourd'hui", valeur: r.aujourd_hui.total, titre: undefined },
                  { libelle: "30 jours", valeur: r.mois.total, titre: undefined },
                  { libelle: "Depuis le début", valeur: r.total.total, titre: depuis ? `Depuis le ${depuis}` : undefined },
                ].map((x) => (
                  <div key={x.libelle} className="rounded-xl border border-line bg-surface-2 px-3 py-2.5" title={x.titre}>
                    <dt className="truncate text-12 text-fg-3">{x.libelle}</dt>
                    <dd className="tabular mt-0.5 text-20 font-semibold">{nombre(x.valeur)}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-13">
              <span className="text-fg-3">{semaineVide ? "Depuis le début :" : "Cette semaine :"}</span>
              {REPARTITION.map((x) => (
                <span key={x.cle} className="tabular">
                  <span className="text-fg-2">{x.libelle}</span> <span className="font-semibold">{nombre(detail[x.cle])}</span>
                </span>
              ))}
            </div>
          </>
        )}
        {r.partage && <p className="mt-3 text-12 text-fg-3">Ces chiffres sont partagés avec votre agence.</p>}
      </section>
    </Carte>
  );
}

export default function Accueil({
  ouvrirModule,
  allerParametres,
  ouvrirSortie,
  sortie,
  nom,
  formule,
  activite,
  resumeActivite,
  bandeau,
}: {
  ouvrirModule: (cle: CleModule) => void;
  allerParametres: () => void;
  ouvrirSortie: () => void;
  /** dossier de sortie (paramètres du moteur) ; null pendant le chargement */
  sortie: string | null;
  /** nom du détenteur de la licence (null si inconnu) */
  nom: string | null;
  /** « Abonnement mensuel », « Licence non activée »… */
  formule: string;
  /** le module qui travaille en ce moment (pastille « En cours · 43 % » sur sa carte) */
  activite: Activite;
  /** compteurs d'activité de ce PC ; null = pas encore lus (ou moteur trop ancien) : pas de carte */
  resumeActivite: ResumeActivite | null;
  bandeau: ReactNode;
}) {
  const nomDossier = sortie ? sortie.split(/[\\/]/).filter(Boolean).pop() ?? sortie : "…";
  return (
    <div className="entree mx-auto max-w-[860px] px-6 pb-10 pt-11 @min-[700px]:px-10">
      {bandeau}
      {/* En-tête */}
      <header>
        <p className="text-13 text-fg-3">{dateDuJour()}</p>
        <div className="mt-1">
          <TitrePage>{nom ? `Bonjour, ${nom}` : "Bonjour"}</TitrePage>
        </div>
        <p className="mt-1.5 text-14 text-fg-2">
          Préparez vos contenus en quelques étapes. <span className="text-fg-3">· {formule}</span>
        </p>
      </header>

      {/* Dossier de sortie + conseil */}
      <div className="mt-7 grid grid-cols-1 gap-4 @min-[760px]:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Carte className="p-5">
          <Surtitre accent>Dossier de sortie</Surtitre>
          <div className="mt-3 flex items-center gap-3">
            <Tuile3D src={ICONES_3D.dossier} taille={52} />
            <div className="min-w-0">
              <p className="truncate text-16 font-semibold tracking-[-0.01em]">{nomDossier}</p>
              <p id="accueil-sortie" className="selectable truncate font-mono text-12 text-fg-3" title={sortie ?? undefined}>
                {sortie ?? "Chargement…"}
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Bouton taille="sm" onClick={ouvrirSortie} disabled={!sortie}>
              Ouvrir
            </Bouton>
            <Bouton taille="sm" variante="fantome" onClick={allerParametres}>
              Changer
            </Bouton>
            <span className="ml-auto text-12 text-fg-3">Vos fichiers préparés arrivent ici.</span>
          </div>
        </Carte>

        <Carte className="flex flex-col p-5">
          <Surtitre accent>Conseil</Surtitre>
          <div className="mt-3 flex gap-3">
            <Tuile3D src={ICONES_3D.ampoule} taille={52} />
            <p className="text-14 leading-relaxed text-fg-2">
              Changez d'abord <span className="text-fg">les métadonnées</span>, puis rangez vos médias selon le
              calendrier.
            </p>
          </div>
        </Carte>
      </div>

      {/* Modules */}
      <div className="mb-3 mt-9 flex items-end justify-between">
        <h2 className="text-16 font-semibold">Préparer le contenu</h2>
      </div>
      <div className="grid grid-cols-1 gap-3.5 @min-[760px]:grid-cols-2">
        {MODULES.map((m, i) => (
          <button
            key={m.cle}
            type="button"
            onClick={() => ouvrirModule(m.cle)}
            className="carte-module entree flex items-center gap-4 rounded-2xl border border-line bg-surface p-5 text-left shadow-card"
            style={{ animationDelay: `${60 + i * 40}ms` }}
          >
            <img src={m.icone} alt="" className="icone-3d h-14 w-14 shrink-0 object-contain" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-16 font-semibold tracking-[-0.01em]">{m.titre}</span>
              {activite?.module === m.cle ? (
                <span className="tabular mt-1 inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-2 py-0.5 text-12 font-medium text-brand-text">
                  <span className="point-actif h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                  {fr(`En cours · ${activite.pct} %`)}
                </span>
              ) : (
                <span className="mt-0.5 line-clamp-2 text-13 text-fg-2">{m.texte}</span>
              )}
            </span>
            <span className="fleche grid h-8 w-8 shrink-0 place-items-center rounded-full bg-fg/[0.05] text-fg-3">
              <ArrowRight weight="bold" className="h-4 w-4" />
            </span>
          </button>
        ))}
      </div>

      {/* Activité (pleine largeur, sous les modules) */}
      {resumeActivite && <CarteActivite r={resumeActivite} />}
    </div>
  );
}
