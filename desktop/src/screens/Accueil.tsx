import { ArrowRight } from "@phosphor-icons/react";
import { Bouton, Carte, Icone3D, Surtitre, TitrePage, Tuile3D } from "../components/ui";
import { ICONES_3D } from "../icones3d";
import { MODULES, type CleModule } from "../modules";
import type { ReactNode } from "react";
import type { Activite } from "../App";
import { fr } from "../fr";

const dateDuJour = () => {
  const d = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" }).format(new Date());
  return d.charAt(0).toUpperCase() + d.slice(1);
};

export default function Accueil({
  ouvrirModule,
  allerParametres,
  ouvrirSortie,
  sortie,
  nom,
  formule,
  activite,
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
              <Icone3D src={ICONES_3D.dossier} taille={18} />
              Ouvrir
            </Bouton>
            <Bouton taille="sm" variante="fantome" onClick={allerParametres}>
              <Icone3D src={ICONES_3D.crayon} taille={18} />
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
        <span className="text-12 text-fg-3">4 modules</span>
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
            <span className="grid h-16 w-16 shrink-0 place-items-center rounded-[16px] border border-line bg-[linear-gradient(180deg,var(--surface-2),var(--surface))]">
              <img src={m.icone} alt="" className="icone-3d h-12 w-12 object-contain" />
            </span>
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

      <p className="mt-7 flex items-center gap-2 text-13 text-fg-3">
        <Icone3D src={ICONES_3D.bouclier} taille={22} />
        {fr("Vos originaux ne sont jamais modifiés : HelpVA travaille sur des copies.")}
      </p>
    </div>
  );
}
