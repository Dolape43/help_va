import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import Toasts, { type Toast } from "./components/Toasts";
import BandeauMoteur from "./components/BandeauMoteur";
import Accueil from "./screens/Accueil";
import ConvertirMp4 from "./screens/ConvertirMp4";
import Parametres from "./screens/Parametres";
import ModuleBientot from "./screens/ModuleBientot";
import type { CleModule } from "./modules";
import { useMoteur } from "./engine/useMoteur";
import type { ResultatConversion, Source, TacheEnCours } from "./engine/api";
import { ErreurMoteur, type EvLog } from "./engine/protocole";
import {
  ligneDepuisLog,
  ligneDossier,
  progressionDepuis,
  type LigneJournal,
  type Progression,
} from "./engine/affichage";
import { fr, pluriel } from "./fr";
import { libelleFormule, nomLicence } from "./licence";
import { themeFenetre } from "./plateforme";

export type Page = "accueil" | "parametres" | { module: CleModule };
export type Theme = "light" | "dark";
export type EtatTache = "inactif" | "en_cours" | "annulation" | "fini" | "arrete";

/** La source choisie pour « Convertir en MP4 », déjà vérifiée par le moteur (commande « preparer »). */
export type SourceChoisie = {
  source: Source;
  /** texte court affiché (« C:\…\Shooting juin » ou « clip_07.mov, clip_08.mov +2 ») */
  libelle: string;
  /** info-bulle : chemin complet / liste complète */
  libelleComplet: string;
  /** nombre de vidéos trouvées par le moteur (sert au « 4 / 11 vidéos ») */
  nbVideos: number;
  /** où iront les .mp4 */
  sortie: string;
  /** .mp4 déjà présents dans la sortie, qui seront remplacés (ffmpeg écrase sans prévenir) */
  dejaPresents: number;
};

/* Le thème est mémorisé dans le navigateur (simple confort ; try/catch car le stockage peut être bloqué). */
function themeInitial(): Theme {
  const t = document.documentElement.dataset.theme;
  return t === "light" ? "light" : "dark";
}
function memoriserTheme(t: Theme) {
  try {
    localStorage.setItem("helpva-theme", t);
  } catch {
    /* stockage indisponible : tant pis, le thème reste celui de la session */
  }
}

const nomFichier = (chemin: string) => chemin.split(/[\\/]/).pop() || chemin;

/** Texte d'une erreur du moteur, avec une phrase plus claire pour les cas fréquents. */
function messageErreur(e: unknown): string {
  if (!(e instanceof ErreurMoteur)) return String(e);
  if (e.code === "LICENCE_REQUISE") return "Licence non activée : activez HelpVA dans l'application actuelle (ou lancez le pont avec --sans-licence en dev).";
  if (e.code === "MOTEUR_ARRETE") return `Le moteur s'est arrêté. ${e.message}`;
  return e.message;
}

export default function App() {
  const [page, setPage] = useState<Page>("accueil");
  const [theme, setThemeState] = useState<Theme>(themeInitial);
  const [etat, setEtat] = useState<EtatTache>("inactif");
  const [source, setSource] = useState<SourceChoisie | null>(null);
  const [progression, setProgression] = useState<Progression | null>(null);
  const [journal, setJournal] = useState<LigneJournal[]>([]);
  const [resultat, setResultat] = useState<ResultatConversion | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const tache = useRef<TacheEnCours<ResultatConversion> | null>(null);
  const contenu = useRef<HTMLElement>(null);
  const prochainId = useRef(1);
  // Page courante lisible depuis la fin de conversion (qui arrive plusieurs secondes après le clic).
  const pageRef = useRef<Page>(page);
  pageRef.current = page;

  const ajouterLigne = useCallback((l: LigneJournal | null) => {
    if (l) setJournal((j) => [...j, l]);
  }, []);
  // Journal « sans propriétaire » (plantage dur du moteur) : on l'affiche aussi.
  const logLibre = useCallback((ev: EvLog) => ajouterLigne(ligneDepuisLog(ev)), [ajouterLigne]);
  const m = useMoteur(logLibre);
  const moteur = m.moteur;

  const setTheme = useCallback((t: Theme) => {
    document.documentElement.dataset.theme = t;
    memoriserTheme(t);
    themeFenetre(t); // barre de titre Windows assortie (dans Tauri seulement)
    setThemeState(t);
  }, []);
  useEffect(() => themeFenetre(themeInitial()), []);

  const aller = useCallback((p: Page) => {
    setPage(p);
    contenu.current?.scrollTo({ top: 0 });
  }, []);

  const notifier = useCallback((t: Omit<Toast, "id">) => {
    const id = prochainId.current++;
    setToasts((l) => [...l.slice(-2), { ...t, id }]);
  }, []);
  const info = useCallback((titre: string, texte: string) => notifier({ type: "info", titre, texte, duree: 3500 }), [notifier]);
  const erreur = useCallback((titre: string, e: unknown) => notifier({ type: "erreur", titre, texte: messageErreur(e), duree: 8000 }), [notifier]);
  const fermerToast = useCallback((id: number) => setToasts((l) => l.filter((t) => t.id !== id)), []);

  /* ---------- Ouvrir un dossier dans l'Explorateur (fait par le moteur, qui vérifie le chemin) ---------- */
  const ouvrir = useCallback(
    async (chemin: string) => {
      try {
        await moteur.ouvrirDossier(chemin);
      } catch (e) {
        erreur("Ouverture impossible", e);
      }
    },
    [moteur, erreur],
  );
  const ouvrirSortieGenerale = useCallback(async () => {
    try {
      // « dossier_sortie » le CRÉE s'il n'existe pas encore (comme l'ancienne app), puis on l'ouvre.
      const d = await moteur.dossierSortie();
      await moteur.ouvrirDossier(d.chemin);
    } catch (e) {
      erreur("Ouverture impossible", e);
    }
  }, [moteur, erreur]);

  const changerSortie = useCallback(async () => {
    try {
      const d = await moteur.choisirDossier("Choisir le dossier de sortie");
      if (!d) return;
      await moteur.parametresEcrire({ dossier_sortie: d });
      await m.relireParametres();
      info("Dossier de sortie", fr(`Vos fichiers arriveront dans : ${d}`));
    } catch (e) {
      erreur("Dossier de sortie", e);
    }
  }, [moteur, m, info, erreur]);

  /* ---------- Choix de la source (fenêtre de choix, puis vérification par le moteur) ---------- */
  const utiliserSource = useCallback(
    async (src: Source) => {
      try {
        // « preparer » vérifie TOUT côté moteur (existe ? contient des vidéos ? pas dans la sortie ?)
        // et compte les vidéos. Une erreur ici (ex. SOURCE_VIDE) s'affiche AVANT de lancer.
        const prep = await moteur.preparer("conversion_mp4", { source: src });
        const libelle =
          src.type === "dossier"
            ? src.chemin
            : src.chemins.slice(0, 2).map(nomFichier).join(", ") + (src.chemins.length > 2 ? ` +${src.chemins.length - 2}` : "");
        setSource({
          source: src,
          libelle,
          libelleComplet: src.type === "dossier" ? src.chemin : src.chemins.join("\n"),
          nbVideos: prep.nb_medias,
          sortie: prep.sortie,
          dejaPresents: prep.deja_presents ?? 0,
        });
        setResultat(null);
        if (etat === "fini" || etat === "arrete") setEtat("inactif");
      } catch (e) {
        erreur("Source refusée", e);
      }
    },
    [moteur, erreur, etat],
  );

  const choisir = useCallback(
    async (type: "dossier" | "fichiers") => {
      try {
        if (type === "dossier") {
          const d = await moteur.choisirDossier("Choisir le dossier de vidéos");
          if (d) await utiliserSource({ type: "dossier", chemin: d });
        } else {
          const f = await moteur.choisirFichiers("Choisir des vidéos", "videos");
          if (f.length) await utiliserSource({ type: "fichiers", chemins: f });
        }
      } catch (e) {
        erreur("Fenêtre de choix", e);
      }
    },
    [moteur, utiliserSource, erreur],
  );

  /* ---------- Conversion ---------- */
  const lancer = useCallback(async () => {
    if (tache.current || !source) return;
    setJournal([]);
    setProgression(null);
    setResultat(null);
    setEtat("en_cours");
    ajouterLigne({ niveau: "info", texte: fr(`Source : ${source.libelleComplet.split("\n")[0]}${source.source.type === "fichiers" && source.source.chemins.length > 1 ? " …" : ""}`) });

    let dernierGroupe = "";
    const t = moteur.convertirMp4(source.source, {
      onProgress: (ev) => {
        const p = progressionDepuis(ev, source.nbVideos);
        // Nouveau dossier → une ligne « Dossier 2/3 — Modèle A » dans le journal.
        if (p.groupe) {
          const cle = `${p.groupe.index}/${p.groupe.total}`;
          if (cle !== dernierGroupe) {
            dernierGroupe = cle;
            ajouterLigne(ligneDossier(p.groupe));
          }
        }
        setProgression(p);
      },
      onLog: (ev) => ajouterLigne(ligneDepuisLog(ev)),
    });
    tache.current = t;

    let res: ResultatConversion;
    try {
      res = await t.resultat;
    } catch (e) {
      tache.current = null;
      setEtat("inactif");
      setProgression(null);
      ajouterLigne({ niveau: "erreur", texte: messageErreur(e) });
      erreur("Conversion impossible", e);
      return;
    }
    tache.current = null;
    setResultat(res);
    setEtat(res.arrete ? "arrete" : "fini");

    // Sur l'écran MP4, la carte de résultat (qui reste affichée) suffit. La notification ne sert
    // que si l'utilisateur est parti sur un autre écran pendant la conversion.
    const surMp4 = typeof pageRef.current === "object" && pageRef.current.module === "mp4";
    if (surMp4) return;
    const s = res.traites > 1 ? "s" : "";
    if (res.arrete) {
      notifier({
        type: "arret",
        titre: "Interrompu",
        texte: fr(`Opération arrêtée. ${pluriel(res.traites, "vidéo")} déjà convertie${s}.`),
      });
    } else {
      notifier({
        type: "succes",
        titre: "Conversion terminée",
        texte: fr(
          res.dossiers > 1
            ? `${pluriel(res.traites, "vidéo")} convertie${s} dans ${pluriel(res.dossiers, "dossier")} ! Même arborescence que votre dossier.`
            : `${pluriel(res.traites, "vidéo")} convertie${s} !`,
        ),
        action: { libelle: fr("Ouvrir « media (mp4) »"), onClick: () => ouvrir(res.sortie) },
        duree: 8000,
      });
    }
  }, [source, moteur, ajouterLigne, erreur, notifier, ouvrir]);

  const annuler = useCallback(() => {
    if (!tache.current || etat !== "en_cours") return;
    setEtat("annulation");
    // Le moteur arrête ffmpeg tout de suite et supprime le fichier à moitié écrit.
    // La fin arrive ensuite comme un résultat normal, avec arrete: true.
    tache.current.annuler().catch((e) => erreur("Annulation", e));
  }, [etat, erreur]);

  // Échap annule la conversion en cours (comme une fenêtre de progression classique).
  useEffect(() => {
    if (etat !== "en_cours") return;
    const touche = (e: KeyboardEvent) => {
      if (e.key === "Escape") annuler();
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [etat, annuler]);

  /* ---------- Crochets de DÉVELOPPEMENT (captures d'écran, tests automatiques) ----------
     Dans la console :  __demo("theme", "light")  ·  __demo("page", "mp4")
                        __helpvaTest.source({ type: "dossier", chemin: "C:\\…" })   (sans fenêtre de choix)
     Absents de l'app livrée (import.meta.env.DEV vaut false au build). */
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const w = window as unknown as {
      __demo?: (scenario: string, arg?: unknown) => void;
      __helpvaTest?: { source: (s: Source) => Promise<void>; connexion: () => string };
    };
    w.__demo = (scenario, arg) => {
      if (scenario === "theme") setTheme(arg === "light" ? "light" : "dark");
      else if (scenario === "page") aller(arg === "mp4" ? { module: "mp4" } : arg === "parametres" ? "parametres" : "accueil");
    };
    w.__helpvaTest = { source: utiliserSource, connexion: () => m.connexion };
    return () => {
      delete w.__demo;
      delete w.__helpvaTest;
    };
  }, [aller, setTheme, utiliserSource, m.connexion]);

  const occupe = etat === "en_cours" || etat === "annulation";
  const nom = nomLicence(m.licence);
  const formule = libelleFormule(m.licence);
  const bandeau = <BandeauMoteur connexion={m.connexion} raison={m.raison} reconnecter={m.reconnecter} />;

  const ecran = (() => {
    if (page === "accueil")
      return (
        <Accueil
          ouvrirModule={(cle) => aller({ module: cle })}
          allerParametres={() => aller("parametres")}
          ouvrirSortie={ouvrirSortieGenerale}
          sortie={m.sortie}
          nom={nom}
          formule={formule}
          bandeau={bandeau}
        />
      );
    if (page === "parametres")
      return (
        <Parametres
          sortie={m.sortie}
          licence={m.licence}
          info={m.info}
          transport={moteur.transport}
          changerSortie={changerSortie}
          ouvrirSortie={ouvrirSortieGenerale}
          notifier={info}
          bandeau={bandeau}
        />
      );
    if (page.module === "mp4")
      return (
        <ConvertirMp4
            bandeau={bandeau}
            source={source}
            choisir={choisir}
            demo={moteur.mode === "simule"}
            etat={etat}
            progression={progression}
            resultat={resultat}
            journal={journal}
            lancer={lancer}
            annuler={annuler}
            ouvrirSortie={() => resultat && ouvrir(resultat.sortie)}
            effacer={() => {
              setJournal([]);
              setResultat(null);
              setEtat("inactif");
            }}
            retour={() => aller("accueil")}
          />
      );
    return <ModuleBientot cle={page.module} retour={() => aller("accueil")} voirMp4={() => aller({ module: "mp4" })} />;
  })();

  // Clé d'écran : rejoue l'animation d'entrée à chaque changement de page.
  const cle = typeof page === "string" ? page : page.module;

  return (
    <div className="flex h-full bg-window">
      <Sidebar
        page={page}
        aller={aller}
        theme={theme}
        setTheme={setTheme}
        pctMp4={occupe ? Math.round((progression?.fraction ?? 0) * 100) : null}
        nom={nom}
        formule={formule}
        licenceOk={m.licence ? m.licence.ok : null}
        connexion={m.connexion}
        transport={moteur.transport}
        raison={m.raison}
      />
      <main
        ref={contenu}
        className="halo scroll-fin my-2 mr-2 min-w-0 flex-1 overflow-y-auto rounded-[14px] border border-line shadow-[0_1px_3px_rgba(0,0,0,0.04)]"
      >
        {/* @container : les écrans s'adaptent à la largeur de CETTE zone (container queries),
            pas à celle de la fenêtre. Utile car la barre latérale prend déjà 248 px. */}
        <div key={cle} className="@container h-full">
          {ecran}
        </div>
      </main>
      <Toasts toasts={toasts} fermer={fermerToast} />
    </div>
  );
}
