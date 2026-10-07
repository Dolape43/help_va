/**
 * useMoteur.ts — le « crochet » React qui garde la connexion au moteur et ses infos de base.
 *
 * Au démarrage : connexion (pont de dev / sidecar / sinon démo), puis on lit en parallèle
 * info, paramètres (dossier de sortie) et licence_statut (qui peut durer jusqu'à 30 s hors-ligne,
 * d'où le chargement indépendant : l'écran n'attend pas la licence pour afficher le reste).
 *
 * licence_statut sert AUSSI de « déverrouillage » côté moteur : sans lui, le moteur refuse les
 * tâches longues (LICENCE_REQUISE). C'est voulu (défense en profondeur).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { InfoMoteur, Moteur, StatutLicence } from "./api";
import { connecterMoteur } from "./connexion";
import { moteurDeSecours } from "./indisponible";
import type { EvLog } from "./protocole";
import { avantFermeture } from "../plateforme";

export type EtatConnexion = "connexion" | "connecte" | "non_connecte";

export type EtatMoteur = {
  connexion: EtatConnexion;
  moteur: Moteur;
  /** pourquoi le moteur n'est pas connecté (affiché en info-bulle / bandeau) */
  raison: string | null;
  info: InfoMoteur | null;
  licence: StatutLicence | null;
  /** dossier de sortie (paramètres) */
  sortie: string | null;
};

/** En dev, on réessaie tout seul : le développeur lance souvent le pont APRÈS Vite. */
const NOUVEL_ESSAI_MS = 4000;

export function useMoteur(surLogLibre: (ev: EvLog) => void) {
  const [etat, setEtat] = useState<EtatMoteur>(() => ({
    connexion: "connexion",
    moteur: moteurDeSecours(),
    raison: null,
    info: null,
    licence: null,
    sortie: null,
  }));
  const [essai, setEssai] = useState(0);
  const logLibre = useRef(surLogLibre);
  logLibre.current = surLogLibre;

  useEffect(() => {
    let actif = true; // false quand l'effet est nettoyé (StrictMode monte deux fois en dev)
    let moteurOuvert: Moteur | null = null;
    let minuteur: ReturnType<typeof setTimeout> | undefined;

    (async () => {
      const { moteur, raison } = await connecterMoteur();
      if (!actif) {
        await moteur.fermer();
        return;
      }
      moteurOuvert = moteur;
      if (moteur.mode !== "reel") {
        setEtat((e) => ({ ...e, connexion: "non_connecte", moteur, raison }));
        if (import.meta.env.DEV) minuteur = setTimeout(() => actif && setEssai((n) => n + 1), NOUVEL_ESSAI_MS);
      } else {
        moteur.surLogLibre((ev) => logLibre.current(ev));
        moteur.surDeconnexion((r) => {
          if (!actif) return;
          setEtat((e) => ({ ...e, connexion: "non_connecte", moteur: moteurDeSecours(r), raison: r }));
          if (import.meta.env.DEV) minuteur = setTimeout(() => actif && setEssai((n) => n + 1), NOUVEL_ESSAI_MS);
        });
        setEtat((e) => ({ ...e, connexion: "connecte", moteur, raison: null }));
      }
      // Lectures indépendantes : chacune met à jour l'écran dès qu'elle arrive.
      moteur.info().then((info) => actif && setEtat((e) => ({ ...e, info })), () => {});
      moteur.parametresLire().then((p) => actif && setEtat((e) => ({ ...e, sortie: p.dossier_sortie })), () => {});
      moteur.licenceStatut().then((licence) => actif && setEtat((e) => ({ ...e, licence })), () => {});
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

  const relireParametres = useCallback(async () => {
    const p = await etat.moteur.parametresLire();
    setEtat((e) => ({ ...e, sortie: p.dossier_sortie }));
  }, [etat.moteur]);

  return { ...etat, reconnecter, relireParametres };
}
