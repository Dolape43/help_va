/**
 * useRanger.ts — la logique du module « Ranger les médias » (copie du déroulé de l'ancienne app,
 * app_ctk.py > _page_ranger / _lancer_ranger), pour UN OU PLUSIEURS comptes Instagram :
 *
 *   1. les comptes (comptes_lire) : chacun a SES dossiers sources et SON calendrier, qui dit
 *      combien de créneaux de chaque type il faut remplir ; les types cochés sont communs à tous
 *      les comptes (mémorisés dans les paramètres : ranger_types) ;
 *   2. un dossier source par type et par compte ; après chaque changement, le MOTEUR analyse
 *      (ranger_analyser, mode `comptes`) : fichiers trouvés, manques, fichiers ignorés, dossier
 *      dans la sortie, doublons, dossiers partagés entre comptes… ;
 *   3. « Ranger » : on revérifie, on montre le récapitulatif (« Confirmer le rangement »),
 *      puis ranger_lancer avec `remplacer` = le chemin exact montré si le dossier existe déjà.
 *
 * Chaque changement d'un compte (nombre, nom, dossier, calendrier) enregistre la liste COMPLÈTE
 * (comptes_sauver) : l'état affiché est toujours celui que le moteur a renvoyé.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  MAX_COMPTES,
  TYPES_POST,
  type AnalyseRanger,
  type Calendrier,
  type CompteRanger,
  type Moteur,
  type ResultatRanger,
  type SourcesRanger,
  type TypePost,
  type VueCalendrier,
  type VueCompte,
  type VueComptes,
} from "./api";
import type { EtatConnexion } from "./useMoteur";
import { useSuivi } from "./useSuivi";
import { ErreurMoteur } from "./protocole";
import { sortieAConfirmer } from "../erreurs";
import { pluriel } from "../fr";

/** « réels », « stories », « stories CTA », « carrousels » (agent/ranger.py > LIBELLES, en minuscule). */
export const NOMS_TYPES: Record<TypePost, string> = {
  reel: "réels",
  story: "stories",
  story_cta: "stories CTA",
  carousel: "carrousels",
};
export const LIBELLES_TYPES: Record<TypePost, string> = {
  reel: "Réels",
  story: "Stories",
  story_cta: "Stories CTA",
  carousel: "Carrousels",
};

/* Même règle que le moteur (engine/commandes.py > _nom_valide) : les heures du calendrier ET les
   noms des comptes deviennent des NOMS DE DOSSIERS (semaine-01/jour-1/1_12h15_reel, ranger/@marie).
   On prévient ici, avant d'enregistrer. */
const INTERDITS = /[<>:"/\\|?*\u0000-\u001f]/;
/* COM0 à COM9, LPT0 à LPT9, aussi avec les chiffres en exposant (COM¹…), et CONIN$ / CONOUT$. */
const RESERVES = new Set(["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", ...["COM", "LPT"].flatMap((p) => [..."0123456789¹²³"].map((i) => `${p}${i}`))]);
export function nomDossierValide(nom: string): boolean {
  return (
    nom.length > 0 &&
    nom.length <= 40 &&
    nom.trim() === nom &&
    nom !== "." &&
    nom !== ".." &&
    !nom.endsWith(".") &&
    !RESERVES.has(nom.split(".")[0].trim().toUpperCase()) &&
    !INTERDITS.test(nom)
  );
}

/** Pourquoi un nom de compte est refusé (null = accepté). `autres` : les noms des AUTRES comptes. */
export function erreurNomCompte(nom: string, autres: string[]): string | null {
  const propre = nom.trim();
  if (!propre) return "Donnez un nom au compte.";
  if (propre.length > 40) return "40 caractères au maximum.";
  if (!nomDossierValide(propre))
    return 'Ce nom deviendra un nom de dossier : évitez \\ / : * ? " < > |, le point final et les noms réservés (CON, NUL…).';
  // Comme le moteur : « COMPTE~1 » est le nom court Windows du dossier « Compte 1 ».
  if (/~\d/.test(propre)) return "Évitez le signe ~ suivi d'un chiffre : Windows s'en sert pour les noms courts (COMPTE~1 = le dossier « Compte 1 »).";
  if (autres.some((a) => a.toLowerCase() === propre.toLowerCase())) return `Un autre compte s'appelle déjà « ${propre} ».`;
  return null;
}

function cochesDepuis(parametres: Record<string, unknown> | null): Record<TypePost, boolean> {
  const choix = (parametres?.ranger_types ?? {}) as Partial<Record<TypePost, unknown>>;
  const sur = typeof choix === "object" && choix !== null ? choix : {};
  return Object.fromEntries(TYPES_POST.map((t) => [t, sur[t] === undefined ? true : Boolean(sur[t])])) as Record<TypePost, boolean>;
}

/** Types à ranger pour UN compte : cochés ET présents dans SON calendrier (comme _types_ranger_actifs). */
export function actifsDe(c: VueCompte | null | undefined, coches: Record<TypePost, boolean>): TypePost[] {
  return c ? TYPES_POST.filter((t) => coches[t] && (c.vue.compte[t] ?? 0) > 0) : [];
}

/** Le compte tel qu'on l'envoie au moteur (sans le résumé `vue`, que le moteur recalcule). */
const versCompte = (c: CompteRanger): CompteRanger => ({ id: c.id, nom: c.nom, sources: { ...c.sources }, calendrier: c.calendrier });
/** Les deux listes décrivent les mêmes comptes (mêmes ids, noms, dossiers et calendriers). */
const memesComptes = (a: CompteRanger[], b: CompteRanger[]) => JSON.stringify(a.map(versCompte)) === JSON.stringify(b.map(versCompte));

/** Un compte qui a des dossiers ou un calendrier personnalisé : on demande avant de l'oublier. */
export const aDesDonnees = (c: CompteRanger) => Object.values(c.sources).some(Boolean) || c.calendrier !== null;

/** Retirer ces comptes (les derniers de la liste) demande une confirmation : voir definirNombre. */
export type DemandeRetrait = { cible: number; retires: CompteRanger[] };

/** « c7 » -> 7 (0 pour un id d'une autre forme). */
const numeroId = (id: string) => Number(/^c(\d+)$/.exec(id)?.[1] ?? 0);

/**
 * Un compte de plus : « Compte n » avec le plus petit n libre, aucun dossier, et une COPIE du
 * calendrier du compte 1 (y compris null = calendrier d'origine). Son id n'a JAMAIS servi
 * (au-delà de `numeroMax`, le plus grand déjà vu) : un compte supprimé ne « revient » pas dans
 * l'éditeur ou à l'étape 2 sous les traits du nouveau.
 */
function nouveauCompte(liste: CompteRanger[], numeroMax: number): CompteRanger {
  const noms = new Set(liste.map((c) => c.nom.toLowerCase()));
  let n = 1;
  while (noms.has(`compte ${n}`)) n++;
  const modele = liste[0]?.calendrier ?? null;
  return {
    id: `c${Math.max(numeroMax, ...liste.map((c) => numeroId(c.id))) + 1}`,
    nom: `Compte ${n}`,
    sources: {},
    calendrier: modele ? (JSON.parse(JSON.stringify(modele)) as Calendrier) : null,
  };
}

/** Erreur du lancement qui nomme un compte (details.compte, details.types) : lequel montrer. */
function compteFautif(e: unknown): { id: string; type: TypePost | null } | null {
  if (!(e instanceof ErreurMoteur)) return null;
  const d = e.details as { compte?: unknown; types?: unknown } | null;
  if (typeof d?.compte !== "string") return null;
  const t = Array.isArray(d.types) ? d.types[0] : null;
  return { id: d.compte, type: TYPES_POST.includes(t as TypePost) ? (t as TypePost) : null };
}

export function useRanger(p: {
  moteur: Moteur;
  connexion: EtatConnexion;
  parametres: Record<string, unknown> | null;
  ecrireParametres: (valeurs: Record<string, unknown>) => Promise<unknown>;
  erreur: (titre: string, e: unknown) => void;
  surFin: (res: ResultatRanger) => void;
  /** le nom d'une AUTRE action en cours (le moteur n'en fait qu'une à la fois), ou null */
  occupeAilleurs: () => string | null;
}) {
  const suivi = useSuivi<ResultatRanger>();
  const [comptes, setComptes] = useState<VueCompte[]>([]);
  const [max, setMax] = useState(MAX_COMPTES);
  /** le compte affiché à l'étape 2 (celui qu'on a cliqué) */
  const [idChoisi, setIdChoisi] = useState<string | null>(null);
  const [onglet, setOnglet] = useState<TypePost | null>(null);
  const [aleatoire, setAleatoire] = useState(true);
  const [analyse, setAnalyse] = useState<AnalyseRanger | null>(null);
  const [analyseEnCours, setAnalyseEnCours] = useState(false);
  /** récapitulatif à confirmer avant de ranger, avec les comptes EXACTS qui ont été analysés */
  const [confirmation, setConfirmation] = useState<AnalyseRanger | null>(null);
  const argsConfirmes = useRef<{ comptes: CompteRanger[]; types: TypePost[] }>({ comptes: [], types: [] });
  /** cases cochées tout de suite à l'écran, sans attendre l'aller-retour avec le moteur */
  const [cochesLocales, setCochesLocales] = useState<Record<TypePost, boolean> | null>(null);

  const ref = useRef(p);
  ref.current = p;

  const coches = useMemo(() => cochesLocales ?? cochesDepuis(p.parametres), [cochesLocales, p.parametres]);
  const comptesCharges = comptes.length > 0;
  /** le compte choisi (le premier si celui choisi n'existe plus) */
  const compte = comptes.find((c) => c.id === idChoisi) ?? comptes[0] ?? null;
  const compteActif = compte?.id ?? null;
  /** types à ranger du compte choisi */
  const actifs = useMemo(() => actifsDe(compte, coches), [compte, coches]);
  /** types cochés présents dans au moins un calendrier */
  const actifsTous = useMemo(() => TYPES_POST.filter((t) => coches[t] && comptes.some((c) => (c.vue.compte[t] ?? 0) > 0)), [coches, comptes]);
  /** créneaux de chaque type, tous comptes confondus (compteurs des cases de l'étape 1) */
  const totaux = useMemo(() => {
    const n: Record<TypePost, number> = { reel: 0, story: 0, story_cta: 0, carousel: 0 };
    for (const c of comptes) for (const t of TYPES_POST) n[t] += c.vue.compte[t] ?? 0;
    return n;
  }, [comptes]);

  // L'onglet ouvert doit toujours être un type actif du compte choisi.
  useEffect(() => {
    if (actifs.length && (!onglet || !actifs.includes(onglet))) setOnglet(actifs[0]);
  }, [actifs, onglet]);

  /* ---------- Comptes ---------- */
  /** la dernière liste renvoyée par le moteur, lisible tout de suite (avant le prochain rendu) */
  const confirmes = useRef<VueCompte[]>([]);
  /** le plus grand numéro d'id déjà vu (c7 -> 7) : voir nouveauCompte */
  const numeroMax = useRef(0);
  const appliquer = useCallback((v: VueComptes) => {
    confirmes.current = v.comptes;
    numeroMax.current = Math.max(numeroMax.current, ...v.comptes.map((c) => numeroId(c.id)));
    setComptes(v.comptes);
    if (typeof v.max === "number" && v.max > 0) setMax(v.max);
  }, []);

  const chargerComptes = useCallback(async () => {
    try {
      appliquer(await ref.current.moteur.comptesLire());
    } catch (e) {
      ref.current.erreur("Comptes", e);
    }
  }, [appliquer]);

  useEffect(() => {
    if (p.connexion === "connecte") void chargerComptes();
  }, [p.moteur, p.connexion, chargerComptes]);

  /**
   * Applique `changer` à la DERNIÈRE liste enregistrée, puis enregistre la liste complète.
   * Les modifications passent une par une, dans l'ordre des clics (la file `file`).
   * `changer` renvoie null s'il n'y a rien à faire.
   * Une erreur du moteur est relancée : c'est à l'appelant de la montrer.
   */
  const file = useRef<Promise<unknown>>(Promise.resolve());
  const modifier = useCallback(
    (changer: (liste: CompteRanger[]) => CompteRanger[] | null): Promise<VueComptes | null> => {
      const suite = file.current.then(async () => {
        if (!confirmes.current.length) throw new Error("Les comptes ne sont pas encore chargés. Réessayez dans un instant.");
        const liste = changer(confirmes.current.map(versCompte));
        if (!liste) return null;
        const v = await ref.current.moteur.comptesSauver(liste);
        appliquer(v);
        return v;
      });
      file.current = suite.catch(() => undefined);
      return suite;
    },
    [appliquer],
  );

  /**
   * « − n + » : ajoute des « Compte n » (calendrier du compte 1) ou retire les derniers.
   * `n` : le nombre voulu, ou une fonction du nombre ACTUEL (« + » : `(k) => k + 1`), évaluée DANS
   * la file, sur la dernière liste enregistrée. Pourquoi ? L'écran a un clic de retard tant que le
   * moteur n'a pas répondu : deux clics rapides sur « + » demanderaient deux fois « 4 comptes ».
   * Retirer un compte qui a des dossiers ou un calendrier personnalisé demande une confirmation,
   * elle aussi calculée sur la VRAIE liste : sans son id dans `dejaConfirmes`, rien n'est retiré et
   * la fonction renvoie ce qu'il faut faire confirmer (null sinon).
   */
  const definirNombre = useCallback(
    async (n: number | ((actuel: number) => number), dejaConfirmes: string[] = []): Promise<DemandeRetrait | null> => {
      let demande: DemandeRetrait | null = null;
      try {
        const v = await modifier((liste) => {
          const voulu = typeof n === "function" ? n(liste.length) : n;
          if (!Number.isFinite(voulu)) return null;
          const cible = Math.min(Math.max(1, Math.round(voulu)), max);
          if (cible === liste.length) return null;
          if (cible < liste.length) {
            const retires = liste.slice(cible);
            if (retires.some((c) => aDesDonnees(c) && !dejaConfirmes.includes(c.id))) {
              demande = { cible, retires };
              return null;
            }
            return liste.slice(0, cible);
          }
          const plus = [...liste];
          while (plus.length < cible) plus.push(nouveauCompte(plus, numeroMax.current));
          return plus;
        });
        // Le compte affiché a été retiré : on montre le dernier qui reste (son voisin).
        if (v) setIdChoisi((choisi) => (choisi && !v.comptes.some((c) => c.id === choisi) ? (v.comptes[v.comptes.length - 1]?.id ?? null) : choisi));
      } catch (e) {
        ref.current.erreur("Nombre de comptes", e);
      }
      return demande;
    },
    [max, modifier],
  );

  const supprimerCompte = useCallback(
    async (id: string) => {
      const i = confirmes.current.findIndex((c) => c.id === id);
      try {
        const v = await modifier((liste) => (liste.length > 1 && liste.some((c) => c.id === id) ? liste.filter((c) => c.id !== id) : null));
        // Le compte supprimé était affiché : on montre son voisin.
        if (v) setIdChoisi((choisi) => (choisi === id ? (v.comptes[Math.min(i, v.comptes.length - 1)]?.id ?? null) : choisi));
      } catch (e) {
        ref.current.erreur("Compte non supprimé", e);
      }
    },
    [modifier],
  );

  /** Renomme un compte. Faux si le moteur refuse : l'ancien nom reste. */
  const renommer = useCallback(
    async (id: string, nom: string): Promise<boolean> => {
      const propre = nom.trim();
      try {
        await modifier((liste) => {
          const c = liste.find((x) => x.id === id);
          if (!c || c.nom === propre) return null;
          return liste.map((x) => (x.id === id ? { ...x, nom: propre } : x));
        });
        return true;
      } catch (e) {
        ref.current.erreur("Nom du compte", e);
        return false;
      }
    },
    [modifier],
  );

  const changerSources = useCallback(
    async (id: string, changer: (s: SourcesRanger) => void) => {
      try {
        await modifier((liste) => {
          if (!liste.some((c) => c.id === id)) return null;
          return liste.map((c) => {
            if (c.id !== id) return c;
            const sources = { ...c.sources };
            changer(sources);
            return { ...c, sources };
          });
        });
      } catch (e) {
        ref.current.erreur("Dossier non enregistré", e);
      }
    },
    [modifier],
  );

  /** Le dossier source d'un type, pour un compte (l'analyse se refait toute seule). */
  const definirDossier = useCallback(
    (id: string, t: TypePost, d: string) => {
      setIdChoisi(id);
      setOnglet(t);
      return changerSources(id, (s) => {
        s[t] = d;
      });
    },
    [changerSources],
  );

  const retirerDossier = useCallback(
    (id: string, t: TypePost) =>
      changerSources(id, (s) => {
        delete s[t];
      }),
    [changerSources],
  );

  const choisirDossier = useCallback(
    async (id: string, t: TypePost) => {
      try {
        const c = confirmes.current.find((x) => x.id === id);
        const pour = c && confirmes.current.length > 1 ? ` de « ${c.nom} »` : "";
        const d = await ref.current.moteur.choisirDossier(`Choisir le dossier des ${NOMS_TYPES[t]}${pour}`);
        if (d) await definirDossier(id, t, d);
      } catch (e) {
        ref.current.erreur("Fenêtre de choix", e);
      }
    },
    [definirDossier],
  );

  /**
   * « Enregistrer » de l'éditeur de calendrier, pour UN compte. Renvoie le résumé du calendrier
   * enregistré ; en cas de refus, l'erreur est relancée (l'éditeur reste ouvert et la montre).
   */
  const enregistrerCalendrier = useCallback(
    async (id: string, cal: Calendrier): Promise<VueCalendrier> => {
      const v = await modifier((liste) => (liste.some((c) => c.id === id) ? liste.map((c) => (c.id === id ? { ...c, calendrier: cal } : c)) : null));
      const c = v?.comptes.find((x) => x.id === id);
      if (!c) throw new Error("Ce compte n'existe plus : fermez l'éditeur puis rouvrez le calendrier depuis la liste des comptes.");
      return { ...c.vue, message: `Calendrier de « ${c.nom} » enregistré (${pluriel(c.vue.semaines, "semaine")}).\nAppliqué au prochain rangement.` };
    },
    [modifier],
  );

  /* ---------- Analyse (refaite après chaque changement) ---------- */
  const numero = useRef(0);
  /** ce que l'analyse ET le lancement envoient au moteur : les comptes et les types cochés */
  const argsAnalyse = useMemo(() => ({ comptes: comptes.map(versCompte), types: TYPES_POST.filter((t) => coches[t]) }), [comptes, coches]);
  const argsRef = useRef(argsAnalyse);
  argsRef.current = argsAnalyse;

  const analyser = useCallback(async (): Promise<{ a: AnalyseRanger; args: typeof argsAnalyse; aJour: boolean } | null> => {
    const n = ++numero.current;
    const args = argsRef.current;
    setAnalyseEnCours(true);
    try {
      const a = await ref.current.moteur.rangerAnalyser(args);
      if (n === numero.current) setAnalyse(a);
      return { a, args, aJour: n === numero.current };
    } catch (e) {
      if (n === numero.current) ref.current.erreur("Ranger", e);
      return null;
    } finally {
      if (n === numero.current) setAnalyseEnCours(false);
    }
  }, []);

  const cleAnalyse = JSON.stringify(argsAnalyse);
  useEffect(() => {
    if (p.connexion !== "connecte" || !comptesCharges) return;
    void analyser();
  }, [cleAnalyse, p.connexion, comptesCharges, analyser]);

  /** L'analyse d'un compte (null tant qu'elle n'est pas arrivée). */
  const analyseDe = useCallback((id: string | null) => (id && analyse?.comptes?.find((c) => c.id === id)) || null, [analyse]);

  /* ---------- Actions ---------- */
  const basculer = useCallback(
    (t: TypePost, valeur: boolean) => {
      const nouveau = { ...coches, [t]: valeur };
      setCochesLocales(nouveau);
      ref.current.ecrireParametres({ ranger_types: nouveau }).catch((e) => ref.current.erreur("Préférence non enregistrée", e));
    },
    [coches],
  );

  /** « Ranger les médias » : vérifications, puis récapitulatif à confirmer. */
  const lancer = useCallback(async () => {
    if (suivi.occupe) return;
    const { erreur } = ref.current;
    // Un enregistrement des comptes peut être en cours : nom validé en quittant le champ (donc
    // juste avant ce clic), « + », dossier retiré… On l'attend, puis on analyse la liste
    // ENREGISTRÉE. Si elle change encore pendant l'analyse, on recommence (5 fois au plus) :
    // sinon le bouton semblerait mort, ou le récapitulatif montrerait l'ANCIEN nom du compte.
    let r: Awaited<ReturnType<typeof analyser>> = null;
    for (let essai = 0; essai < 5; essai++) {
      await file.current;
      r = await analyser();
      if (!r || (r.aJour && memesComptes(r.args.comptes, confirmes.current))) break;
    }
    if (!r) return;
    if (!r.aJour || !memesComptes(r.args.comptes, confirmes.current)) {
      erreur("Ranger", new Error("Les comptes viennent de changer : cliquez de nouveau sur « Ranger les médias »."));
      return;
    }
    const { a } = r;
    const parCompte = a.comptes ?? [];
    const plusieurs = parCompte.length > 1;
    const montrer = (id: string, t?: TypePost) => {
      setIdChoisi(id);
      if (t) setOnglet(t);
    };
    if (!a.actifs.length) {
      erreur(
        "Ranger",
        new Error(
          r.args.types.length
            ? "Aucun calendrier ne contient les types cochés : ajoutez-y des créneaux, ou cochez d'autres types (étape 1)."
            : "Cochez au moins un type de post (étape 1).",
        ),
      );
      return;
    }
    const calFaux = parCompte.find((c) => c.calendrier_erreur);
    if (calFaux || a.calendrier_erreur) {
      if (calFaux) montrer(calFaux.id);
      erreur(plusieurs && calFaux ? `Calendrier de « ${calFaux.nom} »` : "Calendrier", new Error(calFaux?.calendrier_erreur ?? a.calendrier_erreur ?? ""));
      return;
    }
    const sansDossier = parCompte.filter((c) => c.manquants.length);
    if (sansDossier.length || a.manquants.length) {
      if (sansDossier.length) montrer(sansDossier[0].id, sansDossier[0].manquants[0]);
      else setOnglet(a.manquants[0]);
      erreur(
        "Ranger",
        new Error(
          plusieurs
            ? "Choisissez les dossiers manquants :\n" + sansDossier.map((c) => `• ${c.nom} : ${c.manquants.map((t) => LIBELLES_TYPES[t]).join(", ")}`).join("\n")
            : "Choisissez un dossier pour :\n" + a.manquants.map((t) => `• ${LIBELLES_TYPES[t]}`).join("\n"),
        ),
      );
      return;
    }
    const dansSortie = parCompte.find((c) => c.source_dans_sortie.length);
    if (dansSortie || a.source_dans_sortie.length) {
      const t = dansSortie ? dansSortie.source_dans_sortie[0] : a.source_dans_sortie[0];
      if (dansSortie) montrer(dansSortie.id, t);
      else setOnglet(t);
      const de = plusieurs && dansSortie ? ` de « ${dansSortie.nom} »` : "";
      erreur(
        "Dossier invalide",
        new Error(`Le dossier des ${NOMS_TYPES[t]}${de} est dans le dossier de sortie, qui va être remplacé. Choisissez un autre dossier.`),
      );
      return;
    }
    argsConfirmes.current = r.args;
    setConfirmation(a);
  }, [suivi.occupe, analyser]);

  const confirmer = useCallback(async () => {
    const a = confirmation;
    setConfirmation(null);
    if (!a) return;
    const { moteur, erreur, surFin, occupeAilleurs } = ref.current;
    const autre = occupeAilleurs();
    if (autre) {
      erreur("Patientez", new Error(`« ${autre} » est en cours. Relancez quand ce sera fini.`));
      return;
    }
    const { comptes: liste, types } = argsConfirmes.current;
    // Les comptes ont changé depuis le récapitulatif (réponse du moteur arrivée en retard) : on en
    // remontre un à jour, plutôt que de ranger dans le dossier d'un compte qui a changé de nom.
    if (!memesComptes(liste, confirmes.current)) {
      void lancer();
      return;
    }
    const parCompte = a.comptes ?? [];
    // Total des créneaux à remplir, TOUS comptes confondus (la fraction du moteur est globale).
    const total = parCompte.length
      ? parCompte.reduce((n, c) => n + c.creneaux, 0)
      : a.actifs.reduce((n, t) => n + a.types[t].creneaux, 0);
    const ranges = parCompte.filter((c) => c.actifs.length).length;
    const quoi = a.actifs.map((t) => LIBELLES_TYPES[t]).join(", ");
    try {
      const res = await suivi.demarrer(
        (ev) => moteur.rangerLancer({ comptes: liste, types, aleatoire, remplacer: a.existe ? a.sortie : undefined }, ev),
        { total, intro: ranges > 1 ? `Rangement de ${pluriel(ranges, "compte")} (${quoi}) → ${a.sortie}` : `Rangement de ${quoi} → ${a.sortie}` },
      );
      surFin(res);
    } catch (e) {
      // Le dossier « ranger » est apparu (ou a changé) depuis le récapitulatif : on redemande.
      if (sortieAConfirmer(e)) void lancer();
      else {
        // Le moteur nomme le compte en cause (dossier introuvable…) : on l'affiche.
        const f = compteFautif(e);
        if (f) {
          setIdChoisi(f.id);
          if (f.type) setOnglet(f.type);
        }
        erreur("Ranger", e);
      }
    } finally {
      void analyser(); // la sortie existe maintenant : l'analyse le dira au prochain rangement
    }
  }, [confirmation, aleatoire, suivi, analyser, lancer]);

  const annuler = useCallback(() => suivi.annuler((e) => ref.current.erreur("Annulation", e)), [suivi]);

  return {
    ...suivi,
    comptes,
    comptesCharges,
    max,
    compte,
    compteActif,
    setCompteActif: setIdChoisi,
    onglet,
    setOnglet,
    aleatoire,
    setAleatoire,
    analyse,
    analyseEnCours,
    analyseDe,
    coches,
    actifs,
    actifsTous,
    totaux,
    basculer,
    definirNombre,
    supprimerCompte,
    renommer,
    definirDossier,
    retirerDossier,
    choisirDossier,
    enregistrerCalendrier,
    lancer,
    annuler,
    confirmation,
    confirmer,
    refuserConfirmation: () => setConfirmation(null),
  };
}

export type Rangement = ReturnType<typeof useRanger>;
