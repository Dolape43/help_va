/**
 * useTraitement.ts — la logique commune aux modules « source → options → lancer » :
 * Convertir en MP4, Convertir les images, Changer les métadonnées.
 *
 * Déroulé (engine/README.md, section 3) :
 *   1. choisir un dossier ou des fichiers → « preparer » vérifie TOUT côté moteur (existe ?
 *      contient des médias ? pas dans la sortie ?) et compte les médias ;
 *   2. « Lancer » → « preparer » à nouveau (la sortie a pu changer) ; si le dossier de sortie
 *      existe et sera remplacé → fenêtre « Remplacer ? » qui montre le chemin exact ;
 *   3. la tâche démarre avec `remplacer: <ce chemin>` : le moteur ne supprime QUE ce dossier.
 *      Si la sortie a changé entre-temps, il refuse (SORTIE_EXISTE) et on redemande.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { ArgsTraitement, CommandeTraitement, FiltreFichiers, Moteur, ResultatTraitement, Source } from "./api";
import { useSuivi } from "./useSuivi";
import { sortieAConfirmer } from "../erreurs";

/** La source choisie, déjà vérifiée par le moteur. */
export type SourceChoisie = {
  source: Source;
  /** texte court affiché (« C:\…\Shooting juin » ou « clip_07.mov, clip_08.mov +2 ») */
  libelle: string;
  /** info-bulle : chemin complet / liste complète */
  libelleComplet: string;
  /** nombre de médias utiles trouvés par le moteur */
  nbMedias: number;
  /** où ira le résultat */
  sortie: string;
  /** conversion_mp4 : .mp4 déjà présents qui seront remplacés (ffmpeg écrase sans prévenir) */
  dejaPresents: number;
  /** le dossier de sortie existe déjà et sera REMPLACÉ (images, métadonnées) */
  remplace: boolean;
};

export type OptionsTraitement = Omit<ArgsTraitement, "source" | "remplacer">;

/** « Remplacer ? » en attente de réponse. `change` : la sortie a changé depuis le premier accord. */
export type DemandeRemplacement = { sortie: string; change: boolean };

const nomFichier = (chemin: string) => chemin.split(/[\\/]/).pop() || chemin;

export function useTraitement(p: {
  moteur: Moteur;
  commande: CommandeTraitement;
  options: OptionsTraitement;
  /** titres des fenêtres de choix */
  titreDossier: string;
  titreFichiers: string;
  filtre: FiltreFichiers;
  /** affiche une erreur (notification) */
  erreur: (titre: string, e: unknown) => void;
  /** appelé à la fin (réussie ou annulée) : App prévient si l'utilisateur est sur un autre écran */
  surFin: (res: ResultatTraitement) => void;
  /** le nom d'une AUTRE action en cours (le moteur n'en fait qu'une à la fois), ou null */
  occupeAilleurs: () => string | null;
}) {
  const suivi = useSuivi<ResultatTraitement>();
  const [source, setSource] = useState<SourceChoisie | null>(null);
  const [verification, setVerification] = useState(false);
  const [remplacement, setRemplacement] = useState<DemandeRemplacement | null>(null);

  // Les fonctions ci-dessous lisent toujours les DERNIÈRES valeurs (options changées, etc.).
  const ref = useRef(p);
  ref.current = p;
  const sourceRef = useRef(source);
  sourceRef.current = source;

  /** Vérifie une source avec le moteur ; renvoie la source prête, ou null (erreur déjà affichée). */
  const verifier = useCallback(async (src: Source, silencieux = false): Promise<SourceChoisie | null> => {
    const { moteur, commande, options, erreur } = ref.current;
    try {
      const prep = await moteur.preparer(commande, { source: src, ...options });
      return {
        source: src,
        libelle:
          src.type === "dossier"
            ? src.chemin
            : src.chemins.slice(0, 2).map(nomFichier).join(", ") + (src.chemins.length > 2 ? ` +${src.chemins.length - 2}` : ""),
        libelleComplet: src.type === "dossier" ? src.chemin : src.chemins.join("\n"),
        nbMedias: prep.nb_medias,
        sortie: prep.sortie,
        dejaPresents: prep.deja_presents ?? 0,
        remplace: prep.remplacement,
      };
    } catch (e) {
      if (!silencieux) erreur("Source refusée", e);
      return null;
    }
  }, []);

  const utiliserSource = useCallback(
    async (src: Source) => {
      setVerification(true);
      const s = await verifier(src);
      setVerification(false);
      if (!s) return;
      sourceRef.current = s; // tout de suite : une revérification en vol ne doit pas la remplacer
      setSource(s);
      suivi.oublierResultat();
    },
    [verifier, suivi],
  );

  const choisir = useCallback(
    async (type: "dossier" | "fichiers") => {
      const { moteur, titreDossier, titreFichiers, filtre, erreur } = ref.current;
      try {
        if (type === "dossier") {
          const d = await moteur.choisirDossier(titreDossier);
          if (d) await utiliserSource({ type: "dossier", chemin: d });
        } else {
          const f = await moteur.choisirFichiers(titreFichiers, filtre);
          if (f.length) await utiliserSource({ type: "fichiers", chemins: f });
        }
      } catch (e) {
        erreur("Fenêtre de choix", e);
      }
    },
    [utiliserSource],
  );

  // Une option qui change la sortie (format JPG → PNG) : on revérifie la source en silence,
  // pour afficher la bonne destination. (Une vraie erreur réapparaîtra au lancement.)
  const cleOptions = JSON.stringify(p.options);
  useEffect(() => {
    const s = sourceRef.current;
    if (!s) return;
    let actif = true;
    void verifier(s.source, true).then((maj) => {
      if (actif && maj && sourceRef.current?.source === s.source) setSource(maj);
    });
    return () => {
      actif = false;
    };
  }, [cleOptions, verifier]);

  /** Démarre vraiment la tâche (après l'éventuel « Remplacer ? »). */
  const executer = useCallback(
    async (s: SourceChoisie, remplacer: string | undefined) => {
      const { moteur, commande, options, erreur, surFin, occupeAilleurs } = ref.current;
      const autre = occupeAilleurs();
      if (autre) {
        erreur("Patientez", new Error(`« ${autre} » est en cours. Relancez quand ce sera fini.`));
        return;
      }
      const premier = s.libelleComplet.split("\n")[0];
      const intro = `Source : ${premier}${s.source.type === "fichiers" && s.source.chemins.length > 1 ? " …" : ""}`;
      try {
        const res = await suivi.demarrer((ev) => moteur.traiter(commande, { source: s.source, ...options, remplacer }, ev), {
          total: s.nbMedias,
          intro,
        });
        surFin(res);
      } catch (e) {
        const autre = sortieAConfirmer(e);
        if (autre) {
          // La sortie a changé depuis la confirmation (paramètre modifié, clé USB retirée…).
          setRemplacement({ sortie: autre, change: true });
          return;
        }
        erreur("Impossible de terminer", e);
      }
    },
    [suivi],
  );

  const lancer = useCallback(async () => {
    const s = sourceRef.current;
    if (!s || suivi.occupe || verification) return;
    // On revérifie au moment du clic : le dossier a pu changer depuis le choix.
    setVerification(true);
    const maj = await verifier(s.source);
    setVerification(false);
    if (!maj) return;
    sourceRef.current = maj;
    setSource(maj);
    if (maj.remplace) {
      setRemplacement({ sortie: maj.sortie, change: false });
      return;
    }
    await executer(maj, undefined);
  }, [suivi.occupe, verification, verifier, executer]);

  const confirmerRemplacement = useCallback(async () => {
    const r = remplacement;
    const s = sourceRef.current;
    setRemplacement(null);
    if (r && s) await executer(s, r.sortie);
  }, [remplacement, executer]);

  const annuler = useCallback(() => suivi.annuler((e) => ref.current.erreur("Annulation", e)), [suivi]);

  return {
    ...suivi,
    source,
    /** vérification de la source en cours (bouton « Lancer » en attente) */
    verification,
    choisir,
    utiliserSource,
    lancer,
    annuler,
    remplacement,
    confirmerRemplacement,
    refuserRemplacement: () => setRemplacement(null),
  };
}

export type Traitement = ReturnType<typeof useTraitement>;
