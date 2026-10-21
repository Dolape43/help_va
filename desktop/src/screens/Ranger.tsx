import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ArrowRight, CalendarBlank, Check, FolderOpen, Package, Warning, X } from "@phosphor-icons/react";
import { Bouton, Case, Icone3D, LienDossier, Rouage, Surtitre, joindre } from "../components/ui";
import { ICONES_3D } from "../icones3d";
import EnteteModule from "../components/EnteteModule";
import Dialogue from "../components/Dialogue";
import CarteProgression from "../components/module/CarteProgression";
import CarteResultat from "../components/module/CarteResultat";
import Journal from "../components/module/Journal";
import { Etape } from "../components/module/Etape";
import EditeurCalendrier from "../components/ranger/EditeurCalendrier";
import { LigneCompte, OngletsComptes, SelecteurNombre, enumerer, etatCompte, type EtatCompte } from "../components/ranger/Comptes";
import { moduleParCle } from "../modules";
import {
  TYPES_POST,
  type AnalyseRanger,
  type AnalyseTypeRanger,
  type Calendrier,
  type CompteRanger,
  type Moteur,
  type ResultatRanger,
  type TypePost,
  type VueCompte,
} from "../engine/api";
import { LIBELLES_TYPES, NOMS_TYPES, aDesDonnees, actifsDe, type Rangement } from "../engine/useRanger";
import { fr, pluriel } from "../fr";

const unite = (t: TypePost, n: number) => pluriel(n, t === "reel" ? "vidéo" : "image");

/** La règle de chaque type, comme l'ancienne app (_contenu_onglet_ranger). */
function regle(t: TypePost, parCarrousel: number) {
  if (t === "carousel")
    return `Photos nommées 1, 2, 3… : rangées dans l'ordre par groupes de ${parCarrousel} (1-2-3 → 1er carrousel, etc.).`;
  if (t === "reel") return "Uniquement des vidéos (.mp4, .mov…) : les images sont ignorées.";
  return "Uniquement des images (.jpg, .png…) : les vidéos sont ignorées.";
}

/** Ce qu'on perdrait en retirant le compte, en une phrase (« Ce compte, ses dossiers et son calendrier… »). */
function phraseOubli(c: CompteRanger) {
  const dossiers = Object.values(c.sources).some(Boolean);
  const calendrier = c.calendrier !== null;
  if (dossiers && calendrier) return "Ce compte, ses dossiers et son calendrier personnalisé seront oubliés.";
  return `Ce compte et ${dossiers ? "ses dossiers" : "son calendrier personnalisé"} seront oubliés.`;
}

/* ---------- Résultat ---------- */

type BilanTypes = Pick<ResultatRanger, "types" | "besoins" | "places" | "manques">;

/** Une ligne par type rangé : « Réels : 30/30 vidéos · il en manque 2 » (copie du message « fini_ranger »). */
function lignesTypes(r: BilanTypes, parCarrousel: number): { lignes: ReactNode[]; manque: boolean } {
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
  return { lignes, manque };
}

/** Récapitulatif du rangement terminé : par type, ou par compte puis par type (≥ 2 comptes). */
function detailsResultat(r: ResultatRanger, parCarrousel: number): { lignes: ReactNode; manque: boolean } {
  let manque = false;
  let contenu: ReactNode = null;
  if (r.comptes && r.comptes.length > 1) {
    contenu = (
      <ul className="mt-1.5 space-y-1.5 text-13 text-fg-2">
        {r.comptes.map((c) => {
          const x = lignesTypes(c, parCarrousel);
          if (x.manque) manque = true;
          return (
            <li key={c.id}>
              <span className="font-semibold text-fg">{c.nom}</span>
              {c.arrete && <span className="text-fg-3"> (arrêté)</span>}
              {x.lignes.length > 0 ? <ul className="mt-0.5 space-y-0.5 pl-3">{x.lignes}</ul> : <span className="text-fg-3">{fr(" : rien de rangé")}</span>}
            </li>
          );
        })}
      </ul>
    );
  } else {
    const x = lignesTypes(r, parCarrousel);
    manque = x.manque;
    if (x.lignes.length > 0) contenu = <ul className="mt-1.5 space-y-0.5 text-13 text-fg-2">{x.lignes}</ul>;
  }
  const enTrop = r.arrete ? 0 : Object.values(r.surplus ?? {}).reduce((a, b) => a + (b ?? 0), 0);
  return {
    manque,
    lignes: (
      <>
        {contenu}
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

/* ---------- « Confirmer le rangement » ---------- */

/** « • Réels : 12 vidéos pour 15 requises · il en manque 3 » (message_confirmation de l'ancienne app). */
function LignesAnalyse({ types, actifs }: { types: Record<TypePost, AnalyseTypeRanger>; actifs: TypePost[] }) {
  return (
    <ul className="mt-1 space-y-0.5 text-13">
      {actifs.map((t) => {
        const x = types[t];
        return (
          <li key={t}>
            • <span className="font-medium text-fg">{LIBELLES_TYPES[t]}</span>
            {fr(` : ${unite(t, x.trouves)} pour ${x.requis} requise${x.requis > 1 ? "s" : ""}`)}
            {x.manque > 0 && <span className="text-warning">{fr(` · il en manque ${x.manque}`)}</span>}
          </li>
        );
      })}
    </ul>
  );
}

function Alerte({ children, danger = false }: { children: ReactNode; danger?: boolean }) {
  return (
    <li className={`flex items-start gap-1.5 ${danger ? "text-danger" : "text-warning"}`}>
      <Warning weight="fill" className="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="min-w-0">{children}</span>
    </li>
  );
}

const texteDoublon = (x: TypePost, y: TypePost) =>
  fr(`Le même dossier sert pour ${LIBELLES_TYPES[x]} et ${LIBELLES_TYPES[y]} : les mêmes images seront rangées deux fois.`);

/**
 * Le contenu du récapitulatif « Confirmer le rangement » (message_confirmation de l'ancienne app).
 * Avec plusieurs comptes : une section par compte (sous-dossier, types, alertes) puis les dossiers
 * partagés entre comptes, le tout dans une zone qui défile si la liste est longue.
 * Le <dialog> ne défile pas lui-même (overflow visible, page inerte derrière) : un contenu trop haut
 * pousserait « Annuler » / « Ranger les médias » hors de l'écran. D'où la hauteur maximale du tout.
 */
function Recapitulatif({ a }: { a: AnalyseRanger }) {
  const comptes = a.comptes ?? [];
  const partages = a.partages ?? [];
  const plusieurs = comptes.length > 1;
  const sep = a.sortie.includes("\\") ? "\\" : "/";
  const alertesTete = (!plusieurs && (a.incomplet || a.doublons.length > 0)) || partages.length > 0 || a.existe;
  return (
    // Une SEULE zone qui défile (deux zones imbriquées se disputent la molette).
    // tabIndex : elle défile, il faut pouvoir la faire défiler au clavier ;
    // px-1 / -mx-1 : la place de son contour de focus (sinon coupé sur les côtés).
    <div tabIndex={0} role="region" aria-label="Récapitulatif" className="scroll-fin -mx-1 max-h-[calc(100vh-240px)] overflow-y-auto px-1">
      <p className="font-medium text-fg">À ranger :</p>
      {plusieurs ? (
        <div aria-label="Détail par compte" role="group" className="mt-1.5 space-y-2 rounded-lg border border-line bg-surface-2 p-2">
          {comptes.map((c) => {
            const sous = c.sortie.startsWith(a.sortie) ? c.sortie.slice(a.sortie.length).replace(/^[\\/]+/, "") : c.nom;
            return (
              <section key={c.id} aria-label={c.nom} className="rounded-md bg-surface px-3 py-2 shadow-[0_0_0_1px_var(--line)]">
                <p className="flex min-w-0 items-baseline gap-2">
                  <span className="truncate font-semibold text-fg">{c.nom}</span>
                  <span className="truncate font-mono text-11 text-fg-3" title={c.sortie}>
                    {`ranger${sep}${sous}`}
                  </span>
                </p>
                {c.actifs.length > 0 ? (
                  <LignesAnalyse types={c.types} actifs={c.actifs} />
                ) : (
                  <p className="mt-0.5 text-13 text-fg-3">{fr("Aucun type à ranger : compte ignoré.")}</p>
                )}
                {(c.incomplet || c.doublons.length > 0) && (
                  <ul className="mt-1 space-y-1 text-13">
                    {c.incomplet && <Alerte>Certains créneaux resteront incomplets.</Alerte>}
                    {c.doublons.map(([x, y]) => (
                      <Alerte key={`${x}-${y}`}>{texteDoublon(x, y)}</Alerte>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
          {/* Un même dossier peut revenir deux fois (une pour les vidéos, une pour les images) :
              la clé ajoute le type du 1er compte, qui dit de quelle sorte de médias il s'agit. */}
          {partages.length > 0 && (
            <ul aria-label="Dossiers partagés entre comptes" className="space-y-1.5 px-1 pt-1 text-13">
              {partages.map((pt) => (
                <Alerte key={`${pt.dossier}|${pt.comptes[0]?.type ?? ""}`}>
                  {fr(
                    `Le même dossier sert pour ${enumerer(pt.comptes.map((x) => `${x.nom} (${LIBELLES_TYPES[x.type]})`))} : les mêmes médias seront rangés plusieurs fois.`,
                  )}
                  <span className="selectable mt-0.5 block font-mono text-11 [overflow-wrap:anywhere]">{pt.dossier}</span>
                </Alerte>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <LignesAnalyse types={a.types} actifs={a.actifs} />
      )}
      <p className="mt-3 font-medium text-fg">Destination :</p>
      <p className="selectable mt-1 rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-12 text-fg [overflow-wrap:anywhere]">{a.sortie}</p>
      {plusieurs && <p className="mt-1 text-12 text-fg-3">Un sous-dossier par compte, à son nom.</p>}
      {alertesTete && (
        <ul className="mt-3 space-y-1.5 text-13">
          {!plusieurs && a.incomplet && <Alerte>Certains créneaux resteront incomplets.</Alerte>}
          {!plusieurs &&
            a.doublons.map(([x, y]) => (
              <Alerte key={`${x}-${y}`}>{texteDoublon(x, y)}</Alerte>
            ))}
          {/* Le détail est en bas de la zone qui défile : ce rappel d'une ligne reste toujours visible. */}
          {partages.length > 0 && (
            <Alerte>
              {fr(
                `${partages.length > 1 ? "Des dossiers servent" : "Un dossier sert"} à plusieurs comptes : les mêmes médias seront rangés plusieurs fois (détail ci-dessus).`,
              )}
            </Alerte>
          )}
          {a.existe && <Alerte danger>Ce dossier existe déjà et sera REMPLACÉ.</Alerte>}
        </ul>
      )}
    </div>
  );
}

type Confirmation = { titre: string; texte: string; action: string; faire: () => void } | null;

export default function Ranger({
  r,
  moteur,
  imagesParCarrousel,
  occupeAilleurs,
  bandeau,
  retour,
  ouvrirDossier,
  dossierExiste,
  sortie,
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
  dossierExiste: (chemin: string) => Promise<boolean>;
  /** le dossier de sortie général (null pendant le chargement) */
  sortie: string | null;
  erreur: (titre: string, e: unknown) => void;
  info: (titre: string, texte: string) => void;
}) {
  const mod = moduleParCle("ranger");
  /** le compte dont le calendrier est ouvert dans l'éditeur (null = éditeur fermé) */
  const [editeur, setEditeur] = useState<string | null>(null);
  /** « Supprimer ce compte ? » / « Retirer 2 comptes ? » (quand on perdrait des dossiers ou un calendrier) */
  const [aConfirmer, setAConfirmer] = useState<Confirmation>(null);
  const occupe = r.occupe;
  const termine = r.etat === "fini" || r.etat === "arrete";
  const plusieurs = r.comptes.length > 1;
  const cheminRanger = sortie ? joindre(sortie, "ranger") : null;
  /** le compte affiché à l'étape 2 */
  const c = r.compte;
  const ac = r.analyseDe(r.compteActif);
  const n = c?.vue.compte;

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

  // Un compte de plus : on fait défiler la liste jusqu'à lui.
  const liste = useRef<HTMLUListElement>(null);
  const nbAvant = useRef(r.comptes.length);
  useEffect(() => {
    if (nbAvant.current > 0 && r.comptes.length > nbAvant.current) liste.current?.lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    nbAvant.current = r.comptes.length;
  }, [r.comptes.length]);

  // Onglets des types : flèches gauche / droite, Début / Fin (comportement standard des onglets).
  const onglets = useRef<Partial<Record<TypePost, HTMLButtonElement | null>>>({});
  const fleche = (e: KeyboardEvent, t: TypePost) => {
    const i = r.actifs.indexOf(t);
    const cible =
      e.key === "ArrowRight"
        ? r.actifs[i + 1]
        : e.key === "ArrowLeft"
          ? r.actifs[i - 1]
          : e.key === "Home"
            ? r.actifs[0]
            : e.key === "End"
              ? r.actifs[r.actifs.length - 1]
              : null;
    if (!cible) return;
    e.preventDefault();
    r.setOnglet(cible);
    onglets.current[cible]?.focus();
  };

  /** l'état des dossiers de chaque compte (lignes de l'étape 1, onglets de l'étape 2) */
  const etats: Record<string, EtatCompte> = Object.fromEntries(r.comptes.map((x) => [x.id, etatCompte(x, actifsDe(x, r.coches), r.analyseDe(x.id))]));
  const absents = r.comptesCharges ? TYPES_POST.filter((type) => r.totaux[type] === 0) : [];
  const t = r.onglet;
  const x = t && ac ? ac.types[t] : null;
  const dossier = t && c ? c.sources[t] : undefined;
  const de = plusieurs && c ? ` de « ${c.nom} »` : "";
  const fin = termine && r.resultat ? detailsResultat(r.resultat, imagesParCarrousel) : null;
  const resultatParCompte = !!r.resultat?.comptes && r.resultat.comptes.length > 1;
  /** le premier compte dont un type coché n'a pas encore de dossier (l'analyse dira ensuite s'il en manque) */
  const premierIncomplet = r.comptes.find((y) => actifsDe(y, r.coches).some((type) => !y.sources[type])) ?? null;
  const dossiersPrets = r.actifsTous.length > 0 && !premierIncomplet;
  const comptesRanges = r.comptes.filter((y) => actifsDe(y, r.coches).length > 0);
  const creneauxActifs = comptesRanges.reduce((total, y) => total + actifsDe(y, r.coches).reduce((s, type) => s + (y.vue.compte[type] ?? 0), 0), 0);
  // Pour les lecteurs d'écran : le résultat de l'analyse du dossier affiché, une fois connu.
  const annonceAnalyse =
    t && x && dossier && !r.analyseEnCours
      ? !x.dossier_valide
        ? fr(`Dossier des ${NOMS_TYPES[t]}${de} introuvable.`)
        : fr(`Dossier des ${NOMS_TYPES[t]}${de} : ${unite(t, x.trouves)} trouvée${x.trouves > 1 ? "s" : ""}${x.manque > 0 ? `, il en manque ${x.manque}` : ""}.`)
      : "";

  /* ---------- Comptes : nombre, suppression, calendrier ---------- */
  /**
   * « − n + » ou saisie. C'est le crochet qui dit, sur la VRAIE liste (l'écran peut avoir un clic de
   * retard), si on perdrait des dossiers ou un calendrier : on ne demande confirmation que dans ce
   * cas. Confirmé, on recommence en donnant les comptes acceptés (s'il en manque un, on redemande).
   */
  const demanderNombre = async (n: number | ((actuel: number) => number), dejaConfirmes: string[] = []) => {
    const d = await r.definirNombre(n, dejaConfirmes);
    if (!d) return;
    const { cible, retires } = d;
    const avecDonnees = retires.filter(aDesDonnees);
    setAConfirmer({
      titre: retires.length > 1 ? `Retirer ${retires.length} comptes ?` : `Retirer « ${retires[0].nom} » ?`,
      texte:
        retires.length > 1
          ? `Les ${retires.length} derniers comptes de la liste seront retirés. ${enumerer(avecDonnees.map((y) => `« ${y.nom} »`))} ${
              avecDonnees.length > 1 ? "ont" : "a"
            } des dossiers ou un calendrier personnalisé, qui seront oubliés. Vos médias, eux, ne sont pas touchés.`
          : `${phraseOubli(retires[0])} Vos médias, eux, ne sont pas touchés.`,
      action: retires.length > 1 ? `Retirer ${retires.length} comptes` : "Retirer le compte",
      faire: () => void demanderNombre(cible, retires.map((y) => y.id)),
    });
  };

  const supprimer = (y: VueCompte) => {
    const i = r.comptes.findIndex((z) => z.id === y.id);
    const voisin = r.comptes[i + 1] ?? r.comptes[i - 1];
    const faire = () =>
      void r.supprimerCompte(y.id).then(() =>
        // Le bouton « Supprimer » a disparu avec la ligne : le focus va sur le compte voisin.
        requestAnimationFrame(() => {
          if (!document.getElementById(`calendrier-${y.id}`) && voisin) document.getElementById(`calendrier-${voisin.id}`)?.focus();
        }),
      );
    if (!aDesDonnees(y)) {
      faire();
      return;
    }
    setAConfirmer({
      titre: `Supprimer « ${y.nom} » ?`,
      texte: `${phraseOubli(y)} Vos médias, eux, ne sont pas touchés.`,
      action: "Supprimer le compte",
      faire,
    });
  };

  const compteEdite = editeur ? (r.comptes.find((y) => y.id === editeur) ?? null) : null;
  // Le compte de l'éditeur a disparu (« − » cliqué juste avant « Calendrier ») : on oublie son id,
  // sinon l'éditeur resterait « ouvert » pour un compte qui n'existe plus.
  useEffect(() => {
    if (editeur && !compteEdite) setEditeur(null);
  }, [editeur, compteEdite]);
  const enregistrerCalendrier = async (cal: Calendrier) => {
    if (!editeur) throw new Error("Aucun compte choisi.");
    const v = await r.enregistrerCalendrier(editeur, cal);
    if (v.message) info("Calendrier", v.message.replace("\n", " "));
    return v;
  };

  /* ---------- Étape 2 : les onglets des types du compte affiché ---------- */
  const panneauTypes = !c ? null : r.actifs.length === 0 ? (
    <p className="mt-4 text-13 text-fg-3">
      {fr(`Le calendrier de « ${c.nom} » n'a aucun créneau des types cochés : ce compte sera ignoré. Ajoutez-en via « Calendrier » (étape 1).`)}
    </p>
  ) : (
    <>
      <div role="tablist" aria-label={plusieurs ? `Types de posts de « ${c.nom} »` : "Types de posts"} className="mt-4 flex flex-wrap gap-1.5">
        {r.actifs.map((type) => {
          const actif = type === t;
          const choisi = !!c.sources[type];
          const manque = ac?.types[type] && choisi && ac.types[type].manque > 0;
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
            <Bouton id={`importer-${t}`} onClick={() => void r.choisirDossier(c.id, t)} disabled={occupe}>
              <FolderOpen className="h-4 w-4 text-fg-2" aria-hidden="true" />
              Importer le dossier des {NOMS_TYPES[t]}…
            </Bouton>
          </div>
          <div
            className={`mt-3 flex items-center gap-3 rounded-xl border p-3.5 ${dossier ? "border-brand/20 bg-brand-soft" : "border-dashed border-line-2"}`}
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
                  void r.retirerDossier(c.id, t);
                  // Le bouton « Retirer » disparaît : le focus va sur « Importer le dossier… ».
                  requestAnimationFrame(() => document.getElementById(`importer-${t}`)?.focus());
                }}
                aria-label={`Retirer le dossier des ${NOMS_TYPES[t]}${de}`}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-fg-3 transition-colors duration-150 hover:bg-fg/[0.06] hover:text-fg"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      )}
    </>
  );

  return (
    <div className="entree grid min-h-full content-start gap-5 px-6 pb-7 pt-6 @min-[840px]:grid-cols-[minmax(0,1fr)_300px] @min-[840px]:content-stretch @min-[840px]:px-8 @min-[1040px]:grid-cols-[minmax(0,1fr)_340px]">
      <div className="@container min-w-0">
        {bandeau}
        <EnteteModule
          mod={mod}
          sousTitre="Classe vos photos et vidéos selon votre calendrier de posts."
          points={["Un calendrier par compte", "Semaine / jour / créneau", "Copie : originaux intacts"]}
          details="HelpVA crée un dossier par semaine, par jour et par créneau, et y copie vos médias. Chaque type de post (réels, stories, stories CTA, carrousels) a son propre dossier source. Avec plusieurs comptes Instagram, chaque compte a ses propres dossiers, son propre calendrier, et son sous-dossier dans « ranger ». Les carrousels gardent l'ordre 1, 2, 3… Vos originaux ne sont pas touchés."
          retour={retour}
        />
        <div className="mt-2">

        {/* Étape 1 : comptes (nombre, nom, calendrier de chacun) + types communs */}
        <Etape
          numero={1}
          titre="Comptes et calendriers"
          sousTitre="Combien de comptes Instagram, et le calendrier de posts de chacun."
          fait={r.comptesCharges && r.actifsTous.length > 0}
        >
          {!r.comptesCharges ? (
            <p role="status" className="mt-4 flex items-center gap-2 text-13 text-fg-3">
              <Rouage className="h-3.5 w-3.5" /> Chargement des comptes…
            </p>
          ) : (
            <>
              <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
                <span id="libelle-nombre-comptes" className="text-14 font-medium">
                  Nombre de comptes
                </span>
                <SelecteurNombre valeur={r.comptes.length} max={r.max} onChange={(k) => void demanderNombre(k)} disabled={occupe} idLibelle="libelle-nombre-comptes" />
                <span className="text-12 text-fg-3">{fr(`Jusqu'à ${r.max}, chacun avec ses dossiers et son calendrier.`)}</span>
              </div>
              <ul ref={liste} aria-label="Comptes" className="scroll-fin -mx-1 mt-3 flex max-h-[460px] flex-col gap-2 overflow-y-auto px-1 py-0.5">
                {r.comptes.map((y, i) => (
                  <LigneCompte
                    key={y.id}
                    c={y}
                    numero={i + 1}
                    choisi={y.id === r.compteActif}
                    plusieurs={plusieurs}
                    etat={etats[y.id]}
                    erreurCalendrier={r.analyseDe(y.id)?.calendrier_erreur ?? null}
                    autresNoms={r.comptes.filter((z) => z.id !== y.id).map((z) => z.nom)}
                    occupe={occupe}
                    choisir={() => r.setCompteActif(y.id)}
                    renommer={(nom) => r.renommer(y.id, nom)}
                    ouvrirCalendrier={() => setEditeur(y.id)}
                    supprimer={() => supprimer(y)}
                  />
                ))}
              </ul>
              <div className="mt-4 border-t border-line pt-4">
                <fieldset disabled={occupe}>
                  <legend className="text-13 font-medium">
                    Types de posts à ranger
                    {plusieurs && <span className="font-normal text-fg-3"> · pour tous les comptes</span>}
                  </legend>
                  <div className="mt-2.5 flex flex-wrap gap-x-6 gap-y-2.5">
                    {TYPES_POST.map((type) => (
                      <Case key={type} coche={r.totaux[type] > 0 && r.coches[type]} onChange={(v) => r.basculer(type, v)} disabled={r.totaux[type] === 0 || occupe}>
                        {LIBELLES_TYPES[type]} <span className="tabular text-fg-3">({r.totaux[type]})</span>
                      </Case>
                    ))}
                  </div>
                </fieldset>
                {absents.length > 0 && (
                  <p className="mt-3 text-12 text-fg-3">
                    {fr(
                      `Aucun créneau ${absents.map((type) => `« ${LIBELLES_TYPES[type]} »`).join(", ")} ${
                        plusieurs ? "dans les calendriers" : "dans le calendrier"
                      } : ajoutez-en via « Calendrier » pour l'activer.`,
                    )}
                  </p>
                )}
              </div>
            </>
          )}
        </Etape>

        {/* Étape 2 : un dossier par type (onglets), pour le compte choisi */}
        <Etape
          numero={2}
          titre="Dossiers des médias"
          sousTitre={plusieurs ? "Pour chaque compte, un dossier par type de post." : "Un dossier par type de post."}
          fait={dossiersPrets}
        >
          {!r.comptesCharges ? (
            <p className="mt-4 text-13 text-fg-3">Chargement…</p>
          ) : r.actifsTous.length === 0 ? (
            <p className="mt-4 text-13 text-fg-3">{"Cochez au moins un type de post à l'étape 1."}</p>
          ) : (
            <>
              {plusieurs && <OngletsComptes comptes={r.comptes} actif={r.compteActif} etats={etats} choisir={r.setCompteActif} />}
              <div
                id={plusieurs ? "panneau-compte" : undefined}
                role={plusieurs ? "tabpanel" : undefined}
                aria-labelledby={plusieurs && c ? `onglet-compte-${c.id}` : undefined}
              >
                {panneauTypes}
              </div>
            </>
          )}
        </Etape>

        <p className="sr-only" aria-live="polite">
          {annonceAnalyse}
        </p>

        {/* Étape 3 : lancer */}
        <Etape numero={3} titre="Options du rangement" sousTitre="Les médias sont copiés dans votre dossier de sortie." dernier>
          <Case className="mt-4" coche={r.aleatoire} onChange={r.setAleatoire} disabled={occupe}>
            {"Répartir au hasard (les carrousels gardent toujours l'ordre 1, 2, 3…)"}
          </Case>
        </Etape>

        </div>

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
            <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 pl-5 shadow-card @min-[600px]:flex-row @min-[600px]:items-center @min-[600px]:gap-5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-14 font-semibold">
                  {occupeAilleurs
                    ? "Une autre action est en cours"
                    : !r.comptesCharges
                      ? "Chargement des comptes…"
                      : !r.actifsTous.length
                        ? "Cochez au moins un type de post"
                        : premierIncomplet
                          ? plusieurs
                            ? fr(`Choisissez les dossiers de « ${premierIncomplet.nom} »`)
                            : "Choisissez un dossier pour chaque type"
                          : plusieurs
                            ? fr(`${pluriel(comptesRanges.length, "compte")} · ${creneauxActifs} créneau${creneauxActifs > 1 ? "x" : ""} à remplir`)
                            : fr(`${pluriel(r.actifs.length, "type")} de post · ${creneauxActifs} créneau${creneauxActifs > 1 ? "x" : ""} à remplir`)}
                </p>
                {occupeAilleurs ? (
                  <p className="text-12 text-fg-3">{fr(`Patientez : « ${occupeAilleurs} » doit d'abord se terminer.`)}</p>
                ) : (
                  cheminRanger && (
                    <LienDossier
                      chemin={cheminRanger}
                      ouvrir={() => ouvrirDossier(cheminRanger)}
                      existe={dossierExiste}
                      cle={r.resultat}
                      libelle={plusieurs ? "Un sous-dossier par compte dans :" : "Résultat dans :"}
                    />
                  )
                )}
              </div>
              <Bouton
                ref={boutonLancer}
                variante="primaire"
                taille="lg"
                className="group w-full @min-[600px]:w-auto @min-[600px]:min-w-[210px]"
                onClick={() => void r.lancer()}
                disabled={!r.actifsTous.length || !!occupeAilleurs || !r.comptesCharges}
                aria-busy={r.analyseEnCours || undefined}
                title={occupeAilleurs ? fr(`Patientez : « ${occupeAilleurs} » est en cours.`) : undefined}
              >
                Ranger les médias
                <ArrowRight weight="bold" className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
              </Bouton>
            </div>
            {termine && r.resultat && fin && (
              <CarteResultat
                id="resultat-ranger"
                arrete={r.resultat.arrete}
                titre={
                  r.resultat.arrete
                    ? fr(`Rangement arrêté : ${r.resultat.creneaux} créneau${r.resultat.creneaux > 1 ? "x" : ""} déjà rangé${r.resultat.creneaux > 1 ? "s" : ""}`)
                    : "Médias rangés"
                }
                sousTitre={fr(resultatParCompte ? "Dans « ranger », un sous-dossier par compte (semaine / jour / créneau)." : "Dans « ranger » (semaine / jour / créneau).")}
                avertissement={fin.manque ? { texte: "Certains créneaux sont incomplets : ajoutez des médias puis relancez." } : null}
                details={fin.lignes}
                sortie={r.resultat.sortie}
                ouvrirSortie={() => r.resultat && ouvrirDossier(r.resultat.sortie)}
              />
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

      {/* « Supprimer ce compte ? » / « Retirer 2 comptes ? » */}
      <Dialogue
        ouvert={!!aConfirmer}
        fermer={() => setAConfirmer(null)}
        ton="danger"
        icone={<Warning weight="duotone" className="h-6 w-6" />}
        image={ICONES_3D.alerte}
        titre={aConfirmer?.titre ?? ""}
        actions={
          <>
            <Bouton data-autofocus onClick={() => setAConfirmer(null)}>
              Annuler
            </Bouton>
            <Bouton
              variante="alerte"
              onClick={() => {
                aConfirmer?.faire();
                setAConfirmer(null);
              }}
            >
              {aConfirmer?.action}
            </Bouton>
          </>
        }
      >
        <p>{aConfirmer ? fr(aConfirmer.texte) : ""}</p>
      </Dialogue>

      <EditeurCalendrier
        ouvert={!!compteEdite}
        fermer={() => setEditeur(null)}
        moteur={moteur}
        compte={compteEdite}
        autres={r.comptes.filter((y) => y.id !== editeur)}
        imagesParCarrousel={imagesParCarrousel}
        enregistrer={enregistrerCalendrier}
        erreur={erreur}
      />
    </div>
  );
}
