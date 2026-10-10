/**
 * useLicence.ts — la licence, côté interface.
 *
 *  - vérifie la licence dès qu'un moteur est prêt (au démarrage, après une reconnexion) ;
 *  - revérifie toutes les heures un abonnement ou un essai, et toutes les 5 minutes quand on
 *    est hors-ligne (comme l'ancienne app : _planifier_verif_periodique / _traiter_verif) ;
 *  - active un code, résilie la licence.
 *
 * C'est App.tsx qui choisit l'écran à montrer à partir de ces infos (licence.ts > ecranLicence).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { Moteur, ResultatActivation, StatutLicence } from "./api";
import { ErreurMoteur } from "./protocole";
import type { EtatConnexion } from "./useMoteur";
import { messageErreur } from "../erreurs";

/** Contrôle d'un abonnement / essai : toutes les heures (INTERVALLE_VERIF_MS de app_ctk.py). */
export const INTERVALLE_VERIF_MS = 60 * 60 * 1000;
/** Hors-ligne (ou contrôle raté) : on réessaie plus tôt, pour retirer le bandeau dès le retour du réseau. */
export const NOUVEL_ESSAI_MS = 5 * 60 * 1000;

const PAS_ACTIVE: StatutLicence = { ok: false, raison: "pas_active", type: null, expire_le: null, jours_restants: null };

export function useLicence(moteur: Moteur, connexion: EtatConnexion) {
  const [statut, setStatut] = useState<StatutLicence | null>(null);
  /** le dernier contrôle a échoué (moteur arrêté, erreur interne…) : son message */
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  /** +1 à chaque contrôle terminé : relance le minuteur, même si le statut n'a pas changé */
  const [cycle, setCycle] = useState(0);

  const moteurRef = useRef(moteur);
  moteurRef.current = moteur;
  const enVol = useRef<{ moteur: Moteur; promesse: Promise<StatutLicence | null> } | null>(null);
  /**
   * « Génération » de la licence : +1 à chaque activation ou résiliation.
   * Un contrôle lancé AVANT (il peut durer 40 s hors-ligne) ne doit pas écraser le résultat
   * d'une activation faite PENDANT : il rapporterait l'ancienne situation.
   */
  const generation = useRef(0);

  const verifier = useCallback((): Promise<StatutLicence | null> => {
    const m = moteurRef.current;
    // Plusieurs demandes en même temps (« Réessayer » cliqué 3 fois) : une seule vérification.
    if (enVol.current?.moteur === m) return enVol.current.promesse;
    const gen = generation.current;
    setEnCours(true);
    // `vol` est enregistré AVANT la première attente : à la fin, on sait si c'est encore lui le vol en cours.
    const vol = { moteur: m, promesse: Promise.resolve<StatutLicence | null>(null) };
    enVol.current = vol;
    vol.promesse = (async () => {
      try {
        const st = await m.licenceStatut();
        if (moteurRef.current !== m || generation.current !== gen) return null;
        setStatut(st);
        setErreur(null);
        return st;
      } catch (e) {
        if (moteurRef.current === m) setErreur(messageErreur(e));
        return null;
      } finally {
        if (enVol.current === vol) {
          enVol.current = null;
          setEnCours(false);
        }
        if (moteurRef.current === m) setCycle((c) => c + 1);
      }
    })();
    return vol.promesse;
  }, []);

  // Un nouveau moteur prêt (démarrage, reconnexion) : on vérifie la licence.
  useEffect(() => {
    if (connexion === "connexion") return;
    setErreur(null);
    void verifier();
  }, [moteur, connexion, verifier]);

  // Contrôle périodique : toutes les heures pour un abonnement ou un essai. Hors-ligne, toutes les
  // 5 minutes et pour TOUS les types (à vie compris) : le bandeau disparaît dès le retour du réseau,
  // et la règle des 3 jours (agent/licence.py, GRACE_HORS_LIGNE_H) s'applique à tous. Au-delà,
  // l'écran « Connexion internet requise » remplace l'app, même en cours de session (voulu).
  useEffect(() => {
    if (!statut?.ok) return;
    const abonnement = statut.type === "mois" || statut.type === "an" || statut.type === "essai";
    if (!abonnement && !statut.hors_ligne) return;
    const delai = statut.hors_ligne || erreur ? NOUVEL_ESSAI_MS : INTERVALLE_VERIF_MS;
    const id = setTimeout(() => void verifier(), delai);
    return () => clearTimeout(id);
  }, [statut, erreur, cycle, verifier]);

  /** Code d'activation → licence. Un refus (code faux, pas de réseau) revient avec ok = false. */
  const activer = useCallback(async (code: string): Promise<ResultatActivation> => {
    const m = moteurRef.current;
    const r = await m.licenceActiver(code);
    if (r.ok && r.statut && moteurRef.current === m) {
      generation.current++;
      setStatut(r.statut);
      setErreur(null);
    }
    return r;
  }, []);

  /** Supprime la licence de ce PC : l'écran d'activation s'affiche. */
  const resilier = useCallback(async () => {
    const m = moteurRef.current;
    const r = await m.licenceResilier();
    if (!r.ok) {
      // Fichier impossible à effacer : on relit la vraie situation, puis on prévient.
      void verifier();
      throw new ErreurMoteur(
        "RESILIATION_IMPOSSIBLE",
        "La licence n'a pas pu être supprimée de ce PC. Fermez HelpVA, rouvrez-le, puis réessayez.",
      );
    }
    generation.current++;
    setStatut(PAS_ACTIVE);
    setErreur(null);
  }, [verifier]);

  return { statut, erreur, enCours, verifier, activer, resilier };
}

export type Licence = ReturnType<typeof useLicence>;
