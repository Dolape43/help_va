/**
 * useSuivi.ts — suit UNE tâche longue d'un module : état, progression, journal, résultat.
 *
 * Les 4 modules (MP4, images, métadonnées, rangement) s'en servent de la même façon :
 *   demarrer(ev => moteur.traiter(...), { total }) → progression et journal en direct → résultat.
 * L'état vit dans App (via les crochets des modules) : on peut changer d'écran pendant une
 * conversion, et retrouver son journal et son résultat en revenant.
 */
import { useCallback, useRef, useState } from "react";
import type { EcouteursTache, TacheEnCours } from "./api";
import { ligneDepuisLog, ligneDossier, progressionDepuis, type LigneJournal, type Progression } from "./affichage";
import { messageErreur } from "../erreurs";

export type EtatTache = "inactif" | "en_cours" | "annulation" | "fini" | "arrete";

/** Au-delà, on garde seulement les dernières lignes : un dossier de 10 000 photos ne doit pas
 *  ralentir l'écran (le détail complet n'a pas d'intérêt à l'écran). */
const LIGNES_MAX = 1500;
const LIGNES_GARDEES = 1200;

export function useSuivi<R extends { arrete: boolean }>() {
  const [etat, setEtatBrut] = useState<EtatTache>("inactif");
  const [progression, setProgression] = useState<Progression | null>(null);
  const [journal, setJournal] = useState<LigneJournal[]>([]);
  const [resultat, setResultat] = useState<R | null>(null);
  const tache = useRef<TacheEnCours<R> | null>(null);
  // L'état courant, lisible depuis des fonctions créées avant le dernier rendu.
  const etatRef = useRef<EtatTache>("inactif");
  const setEtat = useCallback((e: EtatTache) => {
    etatRef.current = e;
    setEtatBrut(e);
  }, []);

  const ajouter = useCallback((l: LigneJournal | null) => {
    if (!l) return;
    setJournal((j) => (j.length >= LIGNES_MAX ? [...j.slice(-LIGNES_GARDEES), l] : [...j, l]));
  }, []);

  /**
   * Lance la tâche. Renvoie le résultat (aussi en cas d'annulation : `arrete` vaut alors true).
   * En cas d'erreur, la ligne d'erreur est ajoutée au journal, puis l'erreur est relancée :
   * c'est à l'appelant de décider quoi en faire (notification, « Remplacer ? »…).
   */
  const demarrer = useCallback(
    async (lancer: (ev: EcouteursTache) => TacheEnCours<R>, opts: { total: number | null; intro?: string }): Promise<R> => {
      if (tache.current) throw new Error("Une action est déjà en cours, patientez…");
      setJournal(opts.intro ? [{ niveau: "info", texte: opts.intro }] : []);
      setProgression(null);
      setResultat(null);
      setEtat("en_cours");

      let dernierGroupe = "";
      const t = lancer({
        onProgress: (ev) => {
          const p = progressionDepuis(ev, opts.total);
          // Nouveau dossier (ou nouveau jour du calendrier) → une ligne de titre dans le journal.
          // Le compte fait partie de la clé : « Semaine 1/3 — Jour 1 » revient pour chaque compte.
          if (p.groupe) {
            const cle = `${p.compte?.id ?? ""}|${p.groupe.mot}${p.groupe.index}/${p.groupe.total}|${p.groupe.nom ?? ""}`;
            if (cle !== dernierGroupe) {
              dernierGroupe = cle;
              ajouter(ligneDossier(p.groupe));
            }
          }
          setProgression(p);
        },
        onLog: (ev) => ajouter(ligneDepuisLog(ev)),
      });
      tache.current = t;
      try {
        const res = await t.resultat;
        setResultat(res);
        setEtat(res.arrete ? "arrete" : "fini");
        return res;
      } catch (e) {
        setEtat("inactif");
        setProgression(null);
        ajouter({ niveau: "erreur", texte: messageErreur(e) });
        throw e;
      } finally {
        tache.current = null;
      }
    },
    [ajouter, setEtat],
  );

  /** Annulation : le moteur arrête proprement ; la fin arrive ensuite comme un résultat normal. */
  const annuler = useCallback(
    (surErreur: (e: unknown) => void) => {
      if (!tache.current || etatRef.current !== "en_cours") return;
      setEtat("annulation");
      tache.current.annuler().catch(surErreur);
    },
    [setEtat],
  );

  /** « Effacer » le journal (et la carte de résultat). */
  const effacer = useCallback(() => {
    if (tache.current) return;
    setJournal([]);
    setResultat(null);
    setProgression(null);
    setEtat("inactif");
  }, [setEtat]);

  /** Nouvelle source choisie : l'ancien résultat ne la concerne plus. */
  const oublierResultat = useCallback(() => {
    if (tache.current) return;
    setResultat(null);
    if (etatRef.current === "fini" || etatRef.current === "arrete") setEtat("inactif");
  }, [setEtat]);

  const occupe = etat === "en_cours" || etat === "annulation";
  /** `ajouter` : une ligne venue d'ailleurs (journal « sans propriétaire » du moteur, voir App). */
  return { etat, progression, journal, resultat, occupe, demarrer, annuler, effacer, oublierResultat, ajouter };
}

export type Suivi<R extends { arrete: boolean }> = ReturnType<typeof useSuivi<R>>;
