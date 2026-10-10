import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ArrowRight, CalendarBlank, Check, FolderOpen, Package, Warning, X } from "@phosphor-icons/react";
import { Bouton, Case, Icone3D, Rouage, Surtitre } from "../components/ui";
import { ICONES_3D } from "../icones3d";
import EnteteModule from "../components/EnteteModule";
import Dialogue from "../components/Dialogue";
import CarteProgression from "../components/module/CarteProgression";
import CarteResultat from "../components/module/CarteResultat";
import Journal from "../components/module/Journal";
import { BlocInfo, Etape } from "../components/module/Etape";
import EditeurCalendrier from "../components/ranger/EditeurCalendrier";
import { moduleParCle } from "../modules";
import { TYPES_POST, type AnalyseRanger, type Moteur, type ResultatRanger, type TypePost, type VueCalendrier } from "../engine/api";
import { LIBELLES_TYPES, NOMS_TYPES, type Rangement } from "../engine/useRanger";
import { fr, pluriel } from "../fr";

const unite = (t: TypePost, n: number) => pluriel(n, t === "reel" ? "vidéo" : "image");

/** La règle de chaque type, comme l'ancienne app (_contenu_onglet_ranger). */
function regle(t: TypePost, parCarrousel: number) {
  if (t === "carousel")
    return `Photos nommées 1, 2, 3… : rangées dans l'ordre par groupes de ${parCarrousel} (1-2-3 → 1er carrousel, etc.).`;
  if (t === "reel") return "Uniquement des vidéos (.mp4, .mov…) : les images sont ignorées.";
  return "Uniquement des images (.jpg, .png…) : les vidéos sont ignorées.";
}

/** Récapitulatif du rangement terminé (copie du message « fini_ranger »). */
function detailsResultat(r: ResultatRanger, parCarrousel: number): { lignes: ReactNode; manque: boolean } {
  let manque = false;
  const lignes = r.types.map((t) => {
    const requis = (r.besoins?.[t] ?? 0) * (t === "carousel" ? parCarrousel : 1);
    const places = r.places?.[t] ?? 0;
    const m = r.manques?.[t] ?? 0;
    if (m) manque = true;
    return (
      <li key={t} className="flex items-center gap-1.5">
        <span className="font-medium text-fg">{LIBELLES_TYPES[t]}</span>
        <span className="tabular">
          : {places}/{requis} {t === "reel" ? "vidéos" : "images"}
        </span>
        {m > 0 && <span className="text-warning">{fr(`· il en manque ${m}`)}</span>}
      </li>
    );
  });
  const enTrop = r.arrete ? 0 : Object.values(r.surplus ?? {}).reduce((a, b) => a + (b ?? 0), 0);
  return {
    manque,
    lignes: (
      <>
        {lignes.length > 0 && <ul className="mt-1.5 space-y-0.5 text-13 text-fg-2">{lignes}</ul>}
        {enTrop > 0 && (
          <p className="mt-1 flex items-center gap-1.5 text-13 text-fg-2">
            <Package weight="duotone" className="h-4 w-4 text-brand-text" aria-hidden="true" />
            {fr(`${pluriel(enTrop, "média")} en trop → dossier « surplus ».`)}
          </p>
        )}
      </>
    ),
  };
}

/** Le contenu du récapitulatif « Confirmer le rangement » (message_confirmation de l'ancienne app). */
function Recapitulatif({ a }: { a: AnalyseRanger }) {
  return (
    <>
      <p className="font-medium text-fg">À ranger :</p>
      <ul className="mt-1 space-y-0.5 text-13">
        {a.actifs.map((t) => {
          const x = a.types[t];
          return (
            <li key={t}>
              • <span className="font-medium text-fg">{LIBELLES_TYPES[t]}</span>
              {fr(` : ${unite(t, x.trouves)} pour ${x.requis} requise${x.requis > 1 ? "s" : ""}`)}
              {x.manque > 0 && <span className="text-warning">{fr(` · il en manque ${x.manque}`)}</span>}
            </li>
          );
        })}
      </ul>
      <p className="mt-3 font-medium text-fg">Destination :</p>
      <p className="selectable mt-1 rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-12 text-fg [overflow-wrap:anywhere]">{a.sortie}</p>
      {(a.incomplet || a.doublons.length > 0 || a.existe) && (
        <ul className="mt-3 space-y-1.5 text-13">
          {a.incomplet && (
            <li className="flex items-start gap-1.5 text-warning">
              <Warning weight="fill" className="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              Certains créneaux resteront incomplets.
            </li>
          )}
          {a.doublons.map(([x, y]) => (
            <li key={`${x}-${y}`} className="flex items-start gap-1.5 text-warning">
              <Warning weight="fill" className="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {fr(`Le même dossier sert pour ${LIBELLES_TYPES[x]} et ${LIBELLES_TYPES[y]} : les mêmes images seront rangées deux fois.`)}
            </li>
          ))}
          {a.existe && (
            <li className="flex items-start gap-1.5 text-danger">
              <Warning weight="fill" className="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              Ce dossier existe déjà et sera REMPLACÉ.
            </li>
          )}
        </ul>
      )}
    </>
  );
}

export default function Ranger({
  r,
  moteur,
  imagesParCarrousel,
  occupeAilleurs,
  bandeau,
  retour,
  ouvrirDossier,
  erreur,
  info,
}: {
  r: Rangement;
  moteur: Moteur;
  imagesParCarrousel: number;
  occupeAilleurs: string | null;
  bandeau: ReactNode;
  retour: () => void;
  ouvrirDossier: (chemin: string) => void;
  erreur: (titre: string, e: unknown) => void;
  info: (titre: string, texte: string) => void;
}) {
  const mod = moduleParCle("ranger");
  const [editeur, setEditeur] = useState(false);
  const occupe = r.occupe;
  const termine = r.etat === "fini" || r.etat === "arrete";
  const n = r.calendrier?.compte;
  const a = r.analyse;

  // Fin du rangement : même retour du focus et même défilement que les autres modules.
  const boutonLancer = useRef<HTMLButtonElement>(null);
  const etaitOccupe = useRef(occupe);
  useEffect(() => {
    if (etaitOccupe.current && !occupe) {
      if (document.activeElement === document.body || !document.activeElement) boutonLancer.current?.focus({ preventScroll: true });
      document.getElementById("resultat-ranger")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    etaitOccupe.current = occupe;
  }, [occupe]);

  // Onglets des types : flèches gauche / droite (comportement standard des onglets).
  const onglets = useRef<Partial<Record<TypePost, HTMLButtonElement | null>>>({});
  const fleche = (e: KeyboardEvent, t: TypePost) => {
    const i = r.actifs.indexOf(t);
    const cible = e.key === "ArrowRight" ? r.actifs[i + 1] : e.key === "ArrowLeft" ? r.actifs[i - 1] : null;
    if (!cible) return;
    e.preventDefault();
    r.setOnglet(cible);
    onglets.current[cible]?.focus();
  };

  const absents = n ? TYPES_POST.filter((t) => n[t] === 0) : [];
  const t = r.onglet;
  const x = t && a ? a.types[t] : null;
  const dossier = t ? r.sources[t] : undefined;
  const fin = termine && r.resultat ? detailsResultat(r.resultat, imagesParCarrousel) : null;
  // Pour les lecteurs d'écran : le résultat de l'analyse du dossier affiché, une fois connu.
  const annonceAnalyse =
    t && x && dossier && !r.analyseEnCours
      ? !x.dossier_valide
        ? `Dossier des ${NOMS_TYPES[t]} introuvable.`
        : fr(`Dossier des ${NOMS_TYPES[t]} : ${unite(t, x.trouves)} trouvée${x.trouves > 1 ? "s" : ""}${x.manque > 0 ? `, il en manque ${x.manque}` : ""}.`)
      : "";

  const surEnregistre = (vue: VueCalendrier) => {
    r.setCalendrier(vue);
    if (vue.message) info("Calendrier", vue.message.replace("\n", " "));
  };

  return (
    <div className="entree grid min-h-full content-start gap-5 px-6 pb-7 pt-6 @min-[840px]:grid-cols-[minmax(0,1fr)_300px] @min-[840px]:content-stretch @min-[840px]:px-8 @min-[1040px]:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        {bandeau}
        <EnteteModule mod={mod} sousTitre="Classe vos photos et vidéos selon votre calendrier de posts." retour={retour} />
        <BlocInfo>
          HelpVA crée un dossier par semaine / jour / créneau et y copie vos médias. Chaque type de post a son propre dossier
          source. Vos originaux ne sont pas touchés.
        </BlocInfo>

        {/* Étape 1 : calendrier + types */}
        <Etape
          numero={1}
          titre="Régler le calendrier"
          sousTitre="Choisissez les types de posts à ranger."
          action={
            <Bouton taille="sm" onClick={() => setEditeur(true)} disabled={!r.calendrier || occupe}>
              <CalendarBlank className="h-4 w-4 text-fg-2" aria-hidden="true" />
              Modifier le calendrier
            </Bouton>
          }
        >
          <p className="tabular mt-4 text-14 font-medium">
            {r.calendrier
              ? fr(`Calendrier : ${pluriel(r.calendrier.semaines, "semaine")} · ${r.calendrier.creneaux} créneau${r.calendrier.creneaux > 1 ? "x" : ""}`)
              : "Chargement du calendrier…"}
          </p>
          <fieldset className="mt-3 flex flex-wrap gap-x-6 gap-y-2.5" disabled={occupe}>
            <legend className="sr-only">Types de posts à ranger</legend>
            {TYPES_POST.map((type) => (
              <Case key={type} coche={!!n && n[type] > 0 && r.coches[type]} onChange={(v) => r.basculer(type, v)} disabled={!n || n[type] === 0 || occupe}>
                {LIBELLES_TYPES[type]} <span className="tabular text-fg-3">({n?.[type] ?? 0})</span>
              </Case>
            ))}
          </fieldset>
          {absents.length > 0 && (
            <p className="mt-3 text-12 text-fg-3">
              {fr(
                `Aucun créneau ${absents.map((t) => `« ${LIBELLES_TYPES[t]} »`).join(", ")} dans le calendrier : ajoutez-en via « Modifier le calendrier » pour l'activer.`,
              )}
            </p>
          )}
          {a?.calendrier_erreur && (
            <p role="alert" className="mt-3 flex items-start gap-1.5 whitespace-pre-line text-13 text-danger">
              <Warning weight="fill" className="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {a.calendrier_erreur}
            </p>
          )}
        </Etape>

        {/* Étape 2 : un dossier par type (onglets) */}
        <Etape numero={2} titre="Choisir les dossiers" sousTitre="Un dossier par type de post.">
          {r.actifs.length === 0 ? (
            <p className="mt-4 text-13 text-fg-3">{r.calendrier ? "Cochez au moins un type de post à l'étape 1." : "Chargement…"}</p>
          ) : (
            <>
              <div role="tablist" aria-label="Types de posts" className="mt-4 flex flex-wrap gap-1.5">
                {r.actifs.map((type) => {
                  const actif = type === t;
                  const choisi = !!r.sources[type];
                  const manque = a?.types[type] && choisi && a.types[type].manque > 0;
                  return (
                    <button
                      key={type}
                      id={`onglet-${type}`}
                      ref={(el) => {
                        onglets.current[type] = el;
                      }}
                      type="button"
                      role="tab"
                      aria-selected={actif}
                      aria-controls="panneau-type"
                      tabIndex={actif ? 0 : -1}
                      onClick={() => r.setOnglet(type)}
                      onKeyDown={(e) => fleche(e, type)}
                      className={`flex h-9 items-center gap-1.5 rounded-[10px] px-3.5 text-13 font-medium transition-colors duration-150 ${
                        actif ? "bg-brand-btn text-white" : "bg-fg/[0.05] text-fg-2 hover:bg-fg/[0.09] hover:text-fg"
                      }`}
                    >
                      {LIBELLES_TYPES[type]}
                      {choisi && !manque && <Check weight="bold" className="h-3.5 w-3.5" aria-label="dossier choisi" />}
                      {manque && <Warning weight="fill" className={`h-3.5 w-3.5 ${actif ? "" : "text-warning"}`} aria-label="médias manquants" />}
                    </button>
                  );
                })}
              </div>
              {t && (
                <div id="panneau-type" role="tabpanel" aria-labelledby={`onglet-${t}`} className="mt-4">
                  <p className="text-13 text-fg-2">{fr(regle(t, imagesParCarrousel))}</p>
                  <p className="tabular mt-2 text-14 font-semibold text-brand-text">
                    {fr(
                      `Besoin : ${unite(t, x?.requis ?? (n?.[t] ?? 0) * (t === "carousel" ? imagesParCarrousel : 1))}${
                        t === "carousel" ? ` (${pluriel(n?.[t] ?? 0, "carrousel")})` : ""
                      }`,
                    )}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Bouton id={`importer-${t}`} onClick={() => r.choisirDossier(t)} disabled={occupe}>
                      <FolderOpen className="h-4 w-4 text-fg-2" aria-hidden="true" />
                      Importer le dossier des {NOMS_TYPES[t]}…
                    </Bouton>
                  </div>
                  <div
                    className={`mt-3 flex items-center gap-3 rounded-xl border p-3.5 ${
                      dossier ? "border-brand/20 bg-brand-soft" : "border-dashed border-line-2"
                    }`}
                  >
                    <span className="grid h-12 w-12 shrink-0 place-items-center rounded-[12px] bg-surface shadow-[0_0_0_1px_var(--line)]">
                      <Icone3D src={ICONES_3D.dossier} taille={34} className={dossier ? "" : "opacity-50 grayscale"} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <Surtitre>Dossier des {NOMS_TYPES[t]}</Surtitre>
                      <p className="selectable mt-0.5 truncate text-14 font-medium" title={dossier}>
                        {dossier ?? <span className="font-normal text-fg-3">Aucun dossier sélectionné</span>}
                      </p>
                      {dossier && x && (
                        <p className={`mt-0.5 flex items-center gap-1.5 text-12 ${x.manque > 0 || !x.dossier_valide ? "text-warning" : "text-success-text"}`}>
                          {r.analyseEnCours ? (
                            <span className="flex items-center gap-1.5 text-fg-3">
                              <Rouage className="h-3 w-3" /> Analyse…
                            </span>
                          ) : !x.dossier_valide ? (
                            "Dossier introuvable : choisissez-en un autre."
                          ) : (
                            <>
                              {x.manque > 0 ? (
                                <Warning weight="fill" className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                              ) : (
                                <Check weight="bold" className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                              )}
                              {fr(
                                `${unite(t, x.trouves)} trouvée${x.trouves > 1 ? "s" : ""}${x.manque > 0 ? ` · il en manque ${x.manque}` : ""}${
                                  x.ignores ? ` · ${pluriel(x.ignores, "fichier")} ignoré${x.ignores > 1 ? "s" : ""}` : ""
                                }`,
                              )}
                            </>
                          )}
                        </p>
                      )}
                    </div>
                    {dossier && !occupe && (
                      <button
                        type="button"
                        onClick={() => {
                          r.retirerDossier(t);
                          // Le bouton « Retirer » disparaît : le focus va sur « Importer le dossier… ».
                          requestAnimationFrame(() => document.getElementById(`importer-${t}`)?.focus());
                        }}
                        aria-label={`Retirer le dossier des ${NOMS_TYPES[t]}`}
                        className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-fg-3 transition-colors duration-150 hover:bg-fg/[0.06] hover:text-fg"
                      >
                        <X className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </Etape>

        <p className="sr-only" aria-live="polite">
          {annonceAnalyse}
        </p>

        {/* Étape 3 : lancer */}
        <Etape numero={3} titre="Lancer le rangement" sousTitre="Les médias sont copiés dans votre dossier de sortie.">
          <Case className="mt-4" coche={r.aleatoire} onChange={r.setAleatoire} disabled={occupe}>
            {"Répartir au hasard (les carrousels gardent toujours l'ordre 1, 2, 3…)"}
          </Case>
        </Etape>

        {occupe ? (
          <CarteProgression
            progression={r.progression}
            annulation={r.etat === "annulation"}
            annuler={r.annuler}
            icone={mod.icone}
            titre="Rangement en cours…"
            enAttente="Préparation du rangement"
            unite="créneaux"
            texteAnnulation="HelpVA termine le créneau en cours, puis s'arrête. Les créneaux déjà rangés sont gardés."
          />
        ) : (
          <>
            <Bouton
              ref={boutonLancer}
              variante="primaire"
              taille="lg"
              className="group mt-5 w-full"
              onClick={() => void r.lancer()}
              disabled={!r.actifs.length || !!occupeAilleurs || !r.calendrier}
              aria-busy={r.analyseEnCours || undefined}
              title={occupeAilleurs ? fr(`Patientez : « ${occupeAilleurs} » est en cours.`) : undefined}
            >
              Ranger les médias
              <ArrowRight weight="bold" className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
            </Bouton>
            {termine && r.resultat && fin ? (
              <CarteResultat
                id="resultat-ranger"
                arrete={r.resultat.arrete}
                titre={
                  r.resultat.arrete
                    ? fr(`Rangement arrêté : ${r.resultat.creneaux} créneau${r.resultat.creneaux > 1 ? "x" : ""} déjà rangé${r.resultat.creneaux > 1 ? "s" : ""}`)
                    : "Médias rangés"
                }
                sousTitre={fr("Dans « ranger » (semaine / jour / créneau).")}
                avertissement={fin.manque ? { texte: "Certains créneaux sont incomplets : ajoutez des médias puis relancez." } : null}
                details={fin.lignes}
                sortie={r.resultat.sortie}
                ouvrirSortie={() => r.resultat && ouvrirDossier(r.resultat.sortie)}
              />
            ) : (
              <p className="mt-2.5 text-center text-12 text-fg-3">
                {occupeAilleurs
                  ? fr(`Une autre action est en cours (« ${occupeAilleurs} ») : patientez.`)
                  : fr("Résultat dans « ranger » (dans votre dossier de sortie). Un récapitulatif s'affiche avant de commencer.")}
              </p>
            )}
          </>
        )}
      </div>

      <Journal
        etat={r.etat}
        journal={r.journal}
        effacer={r.effacer}
        vide="Le détail de chaque semaine et de chaque créneau s'affichera ici pendant le rangement."
        className="h-[340px] @min-[840px]:h-auto"
      />

      {/* « Confirmer le rangement » */}
      <Dialogue
        ouvert={!!r.confirmation}
        fermer={r.refuserConfirmation}
        ton={r.confirmation?.existe ? "warning" : "brand"}
        icone={<CalendarBlank weight="duotone" className="h-6 w-6" />}
        image={ICONES_3D.calendrier}
        titre="Confirmer le rangement"
        actions={
          <>
            <Bouton data-autofocus onClick={r.refuserConfirmation}>
              Annuler
            </Bouton>
            <Bouton variante="primaire" onClick={() => void r.confirmer()} disabled={!!occupeAilleurs}>
              {r.confirmation?.existe ? "Remplacer et ranger" : "Ranger les médias"}
            </Bouton>
          </>
        }
      >
        {r.confirmation && <Recapitulatif a={r.confirmation} />}
      </Dialogue>

      <EditeurCalendrier
        ouvert={editeur}
        fermer={() => setEditeur(false)}
        moteur={moteur}
        imagesParCarrousel={imagesParCarrousel}
        surEnregistre={surEnregistre}
        erreur={erreur}
      />
    </div>
  );
}
