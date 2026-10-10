/**
 * useRanger.ts — la logique du module « Ranger les médias » (copie du déroulé de l'ancienne app,
 * app_ctk.py > _page_ranger / _lancer_ranger) :
 *
 *   1. le calendrier (calendrier_lire) dit combien de créneaux de chaque type il faut remplir ;
 *      l'utilisateur coche les types à ranger (mémorisé dans les paramètres : ranger_types) ;
 *   2. un dossier source par type ; après chaque choix, le MOTEUR analyse (ranger_analyser) :
 *      fichiers trouvés, manques, fichiers ignorés, dossier dans la sortie, doublons… ;
 *   3. « Ranger » : on revérifie, on montre le récapitulatif (« Confirmer le rangement »),
 *      puis ranger_lancer avec `remplacer` = le chemin exact montré si le dossier existe déjà.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TYPES_POST, type AnalyseRanger, type Moteur, type ResultatRanger, type SourcesRanger, type TypePost, type VueCalendrier } from "./api";
import type { EtatConnexion } from "./useMoteur";
import { useSuivi } from "./useSuivi";
import { sortieAConfirmer } from "../erreurs";

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

function cochesDepuis(parametres: Record<string, unknown> | null): Record<TypePost, boolean> {
  const choix = (parametres?.ranger_types ?? {}) as Partial<Record<TypePost, unknown>>;
  const sur = typeof choix === "object" && choix !== null ? choix : {};
  return Object.fromEntries(TYPES_POST.map((t) => [t, sur[t] === undefined ? true : Boolean(sur[t])])) as Record<TypePost, boolean>;
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
  const [calendrier, setCalendrier] = useState<VueCalendrier | null>(null);
  const [sources, setSources] = useState<SourcesRanger>({});
  const [onglet, setOnglet] = useState<TypePost | null>(null);
  const [aleatoire, setAleatoire] = useState(true);
  const [analyse, setAnalyse] = useState<AnalyseRanger | null>(null);
  const [analyseEnCours, setAnalyseEnCours] = useState(false);
  /** récapitulatif à confirmer avant de ranger, avec les dossiers EXACTS qui ont été analysés */
  const [confirmation, setConfirmation] = useState<AnalyseRanger | null>(null);
  const sourcesConfirmees = useRef<SourcesRanger>({});
  /** cases cochées tout de suite à l'écran, sans attendre l'aller-retour avec le moteur */
  const [cochesLocales, setCochesLocales] = useState<Record<TypePost, boolean> | null>(null);

  const ref = useRef(p);
  ref.current = p;

  const coches = useMemo(() => cochesLocales ?? cochesDepuis(p.parametres), [cochesLocales, p.parametres]);
  const compte = calendrier?.compte;
  /** types cochés ET présents dans le calendrier (comme _types_ranger_actifs) */
  const actifs = useMemo(() => TYPES_POST.filter((t) => coches[t] && (compte?.[t] ?? 0) > 0), [coches, compte]);

  // L'onglet ouvert doit toujours être un type actif.
  useEffect(() => {
    if (actifs.length && (!onglet || !actifs.includes(onglet))) setOnglet(actifs[0]);
  }, [actifs, onglet]);

  /* ---------- Calendrier ---------- */
  const chargerCalendrier = useCallback(async () => {
    try {
      setCalendrier(await ref.current.moteur.calendrierLire());
    } catch (e) {
      ref.current.erreur("Calendrier", e);
    }
  }, []);

  useEffect(() => {
    if (p.connexion === "connecte") void chargerCalendrier();
  }, [p.moteur, p.connexion, chargerCalendrier]);

  /* ---------- Analyse (refaite après chaque changement) ---------- */
  const numero = useRef(0);
  const sourcesRef = useRef(sources);
  sourcesRef.current = sources;
  const actifsRef = useRef(actifs);
  actifsRef.current = actifs;

  const analyser = useCallback(async (): Promise<{ a: AnalyseRanger; sources: SourcesRanger; aJour: boolean } | null> => {
    const n = ++numero.current;
    const sources = { ...sourcesRef.current };
    setAnalyseEnCours(true);
    try {
      const a = await ref.current.moteur.rangerAnalyser({ sources, types: actifsRef.current });
      if (n === numero.current) setAnalyse(a);
      return { a, sources, aJour: n === numero.current };
    } catch (e) {
      if (n === numero.current) ref.current.erreur("Ranger", e);
      return null;
    } finally {
      if (n === numero.current) setAnalyseEnCours(false);
    }
  }, []);

  const cleAnalyse = JSON.stringify([sources, actifs, calendrier?.calendrier ?? null]);
  useEffect(() => {
    if (p.connexion !== "connecte" || !calendrier) return;
    void analyser();
  }, [cleAnalyse, p.connexion, calendrier, analyser]);

  /* ---------- Actions ---------- */
  const basculer = useCallback(
    (t: TypePost, valeur: boolean) => {
      const nouveau = { ...coches, [t]: valeur };
      setCochesLocales(nouveau);
      ref.current.ecrireParametres({ ranger_types: nouveau }).catch((e) => ref.current.erreur("Préférence non enregistrée", e));
    },
    [coches],
  );

  /** Le dossier source d'un type (l'analyse se refait toute seule). */
  const definirDossier = useCallback((t: TypePost, d: string) => {
    setSources((s) => ({ ...s, [t]: d }));
    setOnglet(t);
  }, []);

  const choisirDossier = useCallback(
    async (t: TypePost) => {
      try {
        const d = await ref.current.moteur.choisirDossier(`Choisir le dossier des ${NOMS_TYPES[t]}`);
        if (d) definirDossier(t, d);
      } catch (e) {
        ref.current.erreur("Fenêtre de choix", e);
      }
    },
    [definirDossier],
  );

  const retirerDossier = useCallback((t: TypePost) => {
    setSources((s) => {
      const copie = { ...s };
      delete copie[t];
      return copie;
    });
  }, []);

  /** « Ranger les médias » : vérifications, puis récapitulatif à confirmer. */
  const lancer = useCallback(async () => {
    if (suivi.occupe) return;
    const r = await analyser();
    // Un dossier ou une case a changé pendant l'analyse : celle-ci est dépassée, on ne montre rien.
    if (!r || !r.aJour) return;
    const { a } = r;
    const { erreur } = ref.current;
    if (!a.actifs.length) {
      erreur("Ranger", new Error("Cochez au moins un type de post (étape 1)."));
      return;
    }
    if (a.calendrier_erreur) {
      erreur("Calendrier", new Error(a.calendrier_erreur));
      return;
    }
    if (a.manquants.length) {
      setOnglet(a.manquants[0]);
      erreur("Ranger", new Error("Choisissez un dossier pour :\n" + a.manquants.map((t) => `• ${LIBELLES_TYPES[t]}`).join("\n")));
      return;
    }
    if (a.source_dans_sortie.length) {
      const t = a.source_dans_sortie[0];
      setOnglet(t);
      erreur(
        "Dossier invalide",
        new Error(`Le dossier des ${NOMS_TYPES[t]} est dans le dossier de sortie, qui va être remplacé. Choisissez un autre dossier.`),
      );
      return;
    }
    sourcesConfirmees.current = r.sources;
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
    const total = a.actifs.reduce((n, t) => n + a.types[t].creneaux, 0);
    try {
      const res = await suivi.demarrer(
        (ev) =>
          moteur.rangerLancer(
            { sources: sourcesConfirmees.current, types: a.actifs, aleatoire, remplacer: a.existe ? a.sortie : undefined },
            ev,
          ),
        { total, intro: `Rangement de ${a.actifs.map((t) => LIBELLES_TYPES[t]).join(", ")} → ${a.sortie}` },
      );
      surFin(res);
    } catch (e) {
      // Le dossier « ranger » est apparu (ou a changé) depuis le récapitulatif : on redemande.
      if (sortieAConfirmer(e)) void lancer();
      else erreur("Ranger", e);
    } finally {
      void analyser(); // la sortie existe maintenant : l'analyse le dira au prochain rangement
    }
  }, [confirmation, aleatoire, suivi, analyser, lancer]);

  const annuler = useCallback(() => suivi.annuler((e) => ref.current.erreur("Annulation", e)), [suivi]);

  return {
    ...suivi,
    calendrier,
    setCalendrier,
    sources,
    onglet,
    setOnglet,
    aleatoire,
    setAleatoire,
    analyse,
    analyseEnCours,
    coches,
    actifs,
    basculer,
    definirDossier,
    choisirDossier,
    retirerDossier,
    lancer,
    annuler,
    confirmation,
    confirmer,
    refuserConfirmation: () => setConfirmation(null),
  };
}

export type Rangement = ReturnType<typeof useRanger>;
