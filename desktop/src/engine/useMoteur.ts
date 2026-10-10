/**
 * useMoteur.ts — le « crochet » React qui garde la connexion au moteur et ses infos de base.
 *
 * Au démarrage : connexion (sidecar dans Tauri / pont de dev / sinon moteur indisponible), puis
 * on lit en parallèle `info` et les paramètres (dossier de sortie, « déjà démarré », thème…).
 * La licence a son propre crochet (useLicence.ts) : sa vérification peut durer ~40 s hors-ligne,
 * et l'écran n'a pas à l'attendre pour le reste.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { InfoMoteur, Moteur, VueParametres } from "./api";
import { connecterMoteur } from "./connexion";
import { MoteurIndisponible } from "./indisponible";
import type { EvLog } from "./protocole";
import { avantFermeture } from "../plateforme";

export type EtatConnexion = "connexion" | "connecte" | "non_connecte";

export type EtatMoteur = {
  connexion: EtatConnexion;
  moteur: Moteur;
  /** pourquoi le moteur n'est pas connecté (affiché en info-bulle / bandeau) */
  raison: string | null;
  info: InfoMoteur | null;
  /** paramètres enregistrés (parametres.json) + dossier de sortie ; null pendant le chargement */
  vue: VueParametres | null;
};

/** En dev, on réessaie tout seul : le développeur lance souvent le pont APRÈS Vite. */
const NOUVEL_ESSAI_MS = 4000;

export function useMoteur(surLogLibre: (ev: EvLog) => void) {
  const [etat, setEtat] = useState<EtatMoteur>(() => ({
    connexion: "connexion",
    moteur: new MoteurIndisponible(),
    raison: null,
    info: null,
    vue: null,
  }));
  const [essai, setEssai] = useState(0);
  const logLibre = useRef(surLogLibre);
  logLibre.current = surLogLibre;

  useEffect(() => {
    let actif = true; // false quand l'effet est nettoyé (StrictMode monte deux fois en dev)
    let moteurOuvert: Moteur | null = null;
    let minuteur: ReturnType<typeof setTimeout> | undefined;
    const reessayerEnDev = () => {
      if (import.meta.env.DEV) minuteur = setTimeout(() => actif && setEssai((n) => n + 1), NOUVEL_ESSAI_MS);
    };

    (async () => {
      const { moteur, raison } = await connecterMoteur();
      if (!actif) {
        await moteur.fermer();
        return;
      }
      moteurOuvert = moteur;
      if (moteur.mode !== "reel") {
        setEtat((e) => ({ ...e, connexion: "non_connecte", moteur, raison }));
        reessayerEnDev();
        return;
      }
      moteur.surLogLibre((ev) => logLibre.current(ev));
      moteur.surDeconnexion((r) => {
        if (!actif) return;
        setEtat((e) => ({ ...e, connexion: "non_connecte", moteur: new MoteurIndisponible(r), raison: r }));
        reessayerEnDev();
      });
      setEtat((e) => ({ ...e, connexion: "connecte", moteur, raison: null }));
      // Lectures indépendantes : chacune met à jour l'écran dès qu'elle arrive.
      moteur.info().then((info) => actif && setEtat((e) => ({ ...e, info })), () => {});
      moteur.parametresLire().then(
        (vue) => actif && setEtat((e) => ({ ...e, vue })),
        // Paramètres illisibles : on fait comme l'ancienne app (valeurs par défaut).
        () =>
          actif &&
          setEtat((e) => ({
            ...e,
            vue: e.vue ?? { parametres: {}, dossier_sortie: "", dossier_sortie_defaut: "", personnalise: false },
          })),
      );
    })();

    return () => {
      actif = false;
      clearTimeout(minuteur);
      moteurOuvert?.fermer();
    };
  }, [essai]);

  // Fermeture de la page (navigateur, pont de dev) : on libère le moteur.
  useEffect(() => {
    const quitter = () => {
      etat.moteur.fermer();
    };
    window.addEventListener("beforeunload", quitter);
    return () => window.removeEventListener("beforeunload", quitter);
  }, [etat.moteur]);

  // Fermeture de la FENÊTRE Tauri : on attend que le moteur ait fini son ménage avant de
  // laisser l'app quitter (voir plateforme.ts > avantFermeture). Une ref, pour viser le moteur
  // ACTUEL même s'il a changé (reconnexion) depuis l'installation de l'écouteur.
  const moteurCourant = useRef(etat.moteur);
  moteurCourant.current = etat.moteur;
  useEffect(() => {
    let actif = true;
    let retirer: (() => void) | null = null;
    avantFermeture(() => moteurCourant.current.fermer()).then(
      (f) => {
        if (actif) retirer = f;
        else f(); // composant déjà démonté (StrictMode) : on retire tout de suite
      },
      () => {},
    );
    return () => {
      actif = false;
      retirer?.();
    };
  }, []);

  const reconnecter = useCallback(() => {
    setEtat((e) => ({ ...e, connexion: "connexion" }));
    setEssai((n) => n + 1);
  }, []);

  /** Enregistre des paramètres (le moteur vérifie chaque valeur) et met l'écran à jour. */
  const ecrireParametres = useCallback(async (valeurs: Record<string, unknown>) => {
    const vue = await moteurCourant.current.parametresEcrire(valeurs);
    setEtat((e) => ({ ...e, vue }));
    return vue;
  }, []);

  return {
    ...etat,
    /** dossier de sortie effectif (null pendant le chargement) */
    sortie: etat.vue?.dossier_sortie || null,
    parametres: etat.vue?.parametres ?? null,
    reconnecter,
    ecrireParametres,
  };
}

export type EtatMoteurComplet = ReturnType<typeof useMoteur>;
