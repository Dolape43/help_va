import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import Toasts, { type Toast } from "./components/Toasts";
import BandeauMoteur from "./components/BandeauMoteur";
import RappelsLicence from "./components/RappelsLicence";
import Accueil from "./screens/Accueil";
import ConvertirMp4 from "./screens/ConvertirMp4";
import ConvertirImages, { type FormatImage } from "./screens/ConvertirImages";
import Metadonnees from "./screens/Metadonnees";
import Ranger from "./screens/Ranger";
import Parametres from "./screens/Parametres";
import Portail from "./screens/licence/Portail";
import Verification from "./screens/licence/Verification";
import Activation from "./screens/licence/Activation";
import ConnexionRequise from "./screens/licence/ConnexionRequise";
import Panne from "./screens/licence/Panne";
import Bienvenue from "./screens/licence/Bienvenue";
import { MODULES, moduleParCle, type CleModule } from "./modules";
import { useMoteur } from "./engine/useMoteur";
import { useLicence } from "./engine/useLicence";
import { useTraitement } from "./engine/useTraitement";
import { useRanger } from "./engine/useRanger";
import type { Bilan, Source, TypePost } from "./engine/api";
import type { EvLog } from "./engine/protocole";
import { ligneDepuisLog } from "./engine/affichage";
import { fr } from "./fr";
import { ecranLicence, libelleFormule, nomLicence } from "./licence";
import { messageErreur } from "./erreurs";
import { ouvrirLien, themeFenetre } from "./plateforme";

export type Page = "accueil" | "parametres" | { module: CleModule };
export type Theme = "light" | "dark";

/** Ce qui tourne en ce moment (une seule tâche longue à la fois, comme dans le moteur). */
export type Activite = { module: CleModule; pct: number } | null;

/* Le thème est mémorisé dans le navigateur (affiché dès le premier instant, sans flash) ET dans
   les paramètres du moteur (comme l'ancienne app). try/catch : le stockage peut être bloqué. */
function themeInitial(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}
function themeMemorise(): string | null {
  try {
    return localStorage.getItem("helpva-theme");
  } catch {
    return null;
  }
}
function memoriserTheme(t: Theme) {
  try {
    localStorage.setItem("helpva-theme", t);
  } catch {
    /* stockage indisponible : tant pis, le thème reste celui de la session */
  }
}

/**
 * Le texte d'une notification de fin, tiré du bilan du moteur (même texte que l'ancienne popup) :
 * « ✅ 12 image(s) en .jpg traité(s) !\n\nRésultat :\n…\n\n⚠️ 2 fichier(s) n'ont PAS pu… »
 *   → « 12 image(s) en .jpg traité(s) ! » + la première ligne de l'avertissement, s'il y en a un.
 */
function resumeBilan(b: Bilan, cle: CleModule): string {
  const paragraphes = b.message.split("\n\n");
  const nettoyer = (t: string) => t.replace(/^[\s✅⚠️📦]+/u, "").split("\n")[0];
  const resume = nettoyer(paragraphes[0]);
  if (!b.erreur) return resume;
  const alerte = paragraphes.find((t) => t.trim().startsWith("⚠️"));
  if (alerte) return `${resume}\n${nettoyer(alerte)}`;
  return `${resume}\n${cle === "ranger" ? "Certains créneaux sont incomplets : voir le module." : "Certains fichiers n'ont pas pu être traités : voir le module."}`;
}

export default function App() {
  const [page, setPage] = useState<Page>("accueil");
  const [theme, setThemeState] = useState<Theme>(themeInitial);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const contenu = useRef<HTMLElement>(null);
  const prochainId = useRef(1);
  // Page courante lisible depuis la fin d'un traitement (qui arrive bien après le clic).
  const pageRef = useRef<Page>(page);
  pageRef.current = page;

  /* ---------- Notifications ---------- */
  const notifier = useCallback((t: Omit<Toast, "id">) => {
    const id = prochainId.current++;
    setToasts((l) => [...l.slice(-2), { ...t, id }]);
  }, []);
  const info = useCallback((titre: string, texte: string) => notifier({ type: "info", titre, texte: fr(texte), duree: 4000 }), [notifier]);
  const erreur = useCallback(
    (titre: string, e: unknown) => notifier({ type: "erreur", titre, texte: fr(messageErreur(e)), duree: 8000 }),
    [notifier],
  );
  const fermerToast = useCallback((id: number) => setToasts((l) => l.filter((t) => t.id !== id)), []);

  /* ---------- Moteur et licence ---------- */
  // Journal « sans propriétaire » (plantage dur du moteur) : dans le journal du module qui travaille.
  const versJournalActif = useRef<(ev: EvLog) => void>(() => {});
  const logLibre = useCallback((ev: EvLog) => versJournalActif.current(ev), []);
  const m = useMoteur(logLibre);
  const moteur = m.moteur;
  const lic = useLicence(moteur, m.connexion);

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

  /* ---------- Thème ---------- */
  const moteurRef = useRef(moteur);
  moteurRef.current = moteur;
  const setTheme = useCallback((t: Theme) => {
    document.documentElement.dataset.theme = t;
    memoriserTheme(t);
    themeFenetre(t); // barre de titre Windows assortie (dans Tauri seulement)
    setThemeState(t);
    // Aussi dans parametres.json (comme l'ancienne app). Sans moteur : tant pis, c'est un confort.
    moteurRef.current.parametresEcrire({ theme: t }).catch(() => {});
  }, []);
  useEffect(() => themeFenetre(themeInitial()), []);
  // Premier lancement de la nouvelle interface : on reprend le thème choisi dans l'ancienne app.
  const themeRepris = useRef(false);
  useEffect(() => {
    if (themeRepris.current || !m.parametres) return;
    themeRepris.current = true;
    const t = m.parametres.theme;
    if (!themeMemorise() && (t === "light" || t === "dark") && t !== themeInitial()) setTheme(t);
  }, [m.parametres, setTheme]);

  /* ---------- Navigation ---------- */
  const aller = useCallback((p: Page) => {
    setPage(p);
    contenu.current?.scrollTo({ top: 0 });
  }, []);

  /* ---------- Les 4 modules ---------- */
  // Fin d'un traitement : la carte de résultat suffit si l'utilisateur est sur l'écran du module ;
  // sinon, une notification avec « Ouvrir le dossier ».
  const surFin = useCallback(
    (cle: CleModule) => (res: { arrete: boolean; bilan: Bilan; sortie: string }) => {
      const p = pageRef.current;
      if (typeof p === "object" && p.module === cle) return;
      const titreModule = moduleParCle(cle).titre;
      if (res.arrete) {
        notifier({ type: "arret", titre: "Interrompu", texte: fr(`${titreModule} : ${resumeBilan(res.bilan, cle)}`) });
        return;
      }
      notifier({
        type: res.bilan.erreur ? "erreur" : "succes",
        titre: cle === "ranger" ? "Rangement terminé" : res.bilan.titre,
        texte: fr(resumeBilan(res.bilan, cle)),
        action: { libelle: "Ouvrir le dossier", onClick: () => void ouvrir(res.sortie) },
        duree: 8000,
      });
    },
    [notifier, ouvrir],
  );

  // Le module qui travaille (calculé plus bas, après les crochets) : lu juste avant chaque lancement.
  const actifRef = useRef<CleModule | null>(null);
  const autreQue = (cle: CleModule) => () => {
    const a = actifRef.current;
    return a && a !== cle ? moduleParCle(a).titre : null;
  };

  // Options gardées quand on change d'écran (comme les sources).
  const [formatImages, setFormatImages] = useState<FormatImage>("jpg");
  const [renommer, setRenommer] = useState(true);

  const mp4 = useTraitement({
    moteur,
    commande: "conversion_mp4",
    options: {},
    titreDossier: "Choisir le dossier de vidéos",
    titreFichiers: "Choisir des vidéos",
    filtre: "videos",
    erreur,
    surFin: surFin("mp4"),
    occupeAilleurs: autreQue("mp4"),
  });
  const images = useTraitement({
    moteur,
    commande: "conversion_images",
    options: { format: formatImages },
    titreDossier: "Choisir le dossier d'images",
    titreFichiers: "Choisir des images",
    filtre: "images",
    erreur,
    surFin: surFin("images"),
    occupeAilleurs: autreQue("images"),
  });
  const meta = useTraitement({
    moteur,
    commande: "metadonnees",
    options: { renommer },
    titreDossier: "Choisir le dossier (images ou vidéos)",
    titreFichiers: "Choisir des images / vidéos",
    filtre: "medias",
    erreur,
    surFin: surFin("metadonnees"),
    occupeAilleurs: autreQue("metadonnees"),
  });
  const ranger = useRanger({
    moteur,
    connexion: m.connexion,
    parametres: m.parametres,
    ecrireParametres: m.ecrireParametres,
    erreur,
    surFin: surFin("ranger"),
    occupeAilleurs: autreQue("ranger"),
  });

  const suivis = { mp4, images, metadonnees: meta, ranger };
  const actif = MODULES.map((x) => x.cle).find((cle) => suivis[cle].occupe) ?? null;
  actifRef.current = actif;
  const activite: Activite = actif ? { module: actif, pct: Math.round((suivis[actif].progression?.fraction ?? 0) * 100) } : null;
  const occupeAilleurs = (cle: CleModule) => (actif && actif !== cle ? moduleParCle(actif).titre : null);

  versJournalActif.current = (ev: EvLog) => {
    const cible = actif ?? (typeof pageRef.current === "object" ? pageRef.current.module : null);
    if (cible) suivis[cible].ajouter(ligneDepuisLog(ev));
  };

  /* ---------- Dossier de sortie ---------- */
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
      const vue = await m.ecrireParametres({ dossier_sortie: d });
      info("Dossier de sortie", `Vos fichiers arriveront dans : ${vue.dossier_sortie}`);
    } catch (e) {
      erreur("Dossier de sortie", e);
    }
  }, [moteur, m, info, erreur]);

  const reinitialiserSortie = useCallback(async () => {
    try {
      const vue = await m.ecrireParametres({ dossier_sortie: "" });
      info("Dossier de sortie", `Retour au dossier par défaut : ${vue.dossier_sortie}`);
    } catch (e) {
      erreur("Dossier de sortie", e);
    }
  }, [m, info, erreur]);

  /* ---------- Licence : écrans du portail ---------- */
  // DEV : pont lancé avec --sans-licence → la licence n'est pas exigée (badge visible). Jamais livré.
  // « ?avec-licence » dans l'adresse : on voit quand même les vrais écrans de licence (tests).
  const contournee =
    import.meta.env.DEV && !!m.info?.licence_contournee_dev && !new URLSearchParams(location.search).has("avec-licence");
  const premierLancement = m.parametres === null ? null : m.parametres.deja_demarre !== true;
  const [bienvenueVue, setBienvenueVue] = useState(false);
  const ecranL = ecranLicence({
    statut: lic.statut,
    erreur: lic.erreur,
    enCours: lic.enCours,
    connexion: m.connexion,
    premierLancement: premierLancement === null ? null : premierLancement && !bienvenueVue,
    contournee,
    infoPrete: !import.meta.env.DEV || m.connexion !== "connecte" || m.info !== null,
  });
  const ecranLRef = useRef(ecranL);
  ecranLRef.current = ecranL;

  const ouvrirLienExterne = useCallback(
    (url: string) => {
      ouvrirLien(url).catch((e) => erreur("Lien impossible à ouvrir", e));
    },
    [erreur],
  );

  // « Commencer » (écran Bienvenue) : on retient que l'app a déjà démarré, puis on entre.
  // Si l'enregistrement échoue, on entre quand même (l'écran reviendra au prochain lancement).
  const commencer = useCallback(async () => {
    try {
      await m.ecrireParametres({ deja_demarre: true });
    } catch (e) {
      erreur("Préférence non enregistrée", e);
    }
    setBienvenueVue(true);
    aller("accueil");
  }, [m, erreur, aller]);

  // Panne au démarrage : moteur absent → on se reconnecte ; moteur là → on revérifie.
  const reessayerLicence = useCallback(() => {
    if (m.connexion === "non_connecte") m.reconnecter();
    else void lic.verifier();
  }, [m, lic]);

  /* ---------- Échap annule l'action en cours (sur l'écran de son module) ---------- */
  useEffect(() => {
    if (!actif) return;
    const touche = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || ecranLRef.current !== "app") return;
      if ((e.target as Element | null)?.closest?.("dialog")) return; // Échap ferme d'abord la fenêtre ouverte
      const p = pageRef.current;
      if (typeof p === "object" && p.module === actif) suivis[actif].annuler();
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  });

  /* ---------- Crochets de DÉVELOPPEMENT (captures d'écran, tests automatiques) ----------
     Dans la console :  __demo("theme", "light")  ·  __demo("page", "images")
                        __helpvaTest.source("images", { type: "dossier", chemin: "C:\\…" })  (sans fenêtre de choix)
                        __helpvaTest.rangerDossier("reel", "C:\\…")  (dossier d'un type de post, Ranger)
     Absents de l'app livrée (import.meta.env.DEV vaut false au build). */
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const w = window as unknown as {
      __demo?: (scenario: string, arg?: unknown) => void;
      __helpvaTest?: {
        source: (cle: "mp4" | "images" | "metadonnees", s: Source) => Promise<void>;
        connexion: () => string;
        activer: (code: string) => Promise<unknown>;
        rangerDossier: (type: TypePost, chemin: string) => void;
      };
    };
    w.__demo = (scenario, arg) => {
      if (scenario === "theme") setTheme(arg === "light" ? "light" : "dark");
      else if (scenario === "page") {
        const cle = MODULES.find((x) => x.cle === arg)?.cle;
        aller(cle ? { module: cle } : arg === "parametres" ? "parametres" : "accueil");
      }
    };
    w.__helpvaTest = {
      source: (cle, s) => ({ mp4, images, metadonnees: meta })[cle].utiliserSource(s),
      connexion: () => m.connexion,
      activer: lic.activer,
      rangerDossier: ranger.definirDossier,
    };
    return () => {
      delete w.__demo;
      delete w.__helpvaTest;
    };
  });

  const nom = nomLicence(lic.statut);
  const formule = contournee && !lic.statut?.ok ? "Licence non exigée (dev)" : libelleFormule(lic.statut);

  /* ---------- Portail : tant que la licence n'est pas réglée, pas d'application ---------- */
  if (ecranL !== "app") {
    const st = lic.statut;
    const contenuPortail =
      ecranL === "activation" && st ? (
        <Activation key={st.raison} statut={st} activer={lic.activer} verifier={lic.verifier} ouvrirLien={ouvrirLienExterne} />
      ) : ecranL === "connexion" ? (
        <ConnexionRequise verifier={lic.verifier} enCours={lic.enCours} />
      ) : ecranL === "panne" ? (
        <Panne erreur={lic.erreur ?? ""} reessayer={reessayerLicence} enCours={lic.enCours || m.connexion === "connexion"} />
      ) : ecranL === "bienvenue" && st ? (
        <Bienvenue statut={st} commencer={commencer} resume={contournee && !st.ok ? "Mode développement (licence non exigée)" : undefined} />
      ) : (
        <Verification />
      );
    return (
      <>
        <Portail
          ecran={ecranL === "activation" ? `activation-${st?.raison}` : ecranL}
          theme={theme}
          setTheme={setTheme}
          marque={ecranL !== "verification" && ecranL !== "bienvenue"}
        >
          {contenuPortail}
        </Portail>
        <Toasts toasts={toasts} fermer={fermerToast} />
      </>
    );
  }

  /* ---------- L'application ---------- */
  const bandeau = <BandeauMoteur connexion={m.connexion} raison={m.raison} reconnecter={m.reconnecter} />;
  const retour = () => aller("accueil");
  const commun = { bandeau, retour, ouvrirDossier: (c: string) => void ouvrir(c) };

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
          activite={activite}
          bandeau={bandeau}
        />
      );
    if (page === "parametres")
      return (
        <Parametres
          sortie={m.sortie}
          personnalise={!!m.vue?.personnalise}
          licence={lic.statut}
          formule={formule}
          info={m.info}
          transport={moteur.transport}
          changerSortie={changerSortie}
          reinitialiserSortie={reinitialiserSortie}
          ouvrirSortie={ouvrirSortieGenerale}
          resilier={lic.resilier}
          bandeau={bandeau}
        />
      );
    switch (page.module) {
      case "mp4":
        return <ConvertirMp4 t={mp4} occupeAilleurs={occupeAilleurs("mp4")} {...commun} />;
      case "images":
        return <ConvertirImages t={images} format={formatImages} setFormat={setFormatImages} occupeAilleurs={occupeAilleurs("images")} {...commun} />;
      case "metadonnees":
        return <Metadonnees t={meta} renommer={renommer} setRenommer={setRenommer} occupeAilleurs={occupeAilleurs("metadonnees")} {...commun} />;
      case "ranger":
        return (
          <Ranger
            r={ranger}
            moteur={moteur}
            imagesParCarrousel={m.info?.images_par_carrousel ?? 3}
            occupeAilleurs={occupeAilleurs("ranger")}
            erreur={erreur}
            info={info}
            {...commun}
          />
        );
    }
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
        activite={activite}
        nom={nom}
        formule={formule}
        licenceOk={contournee ? true : lic.statut ? lic.statut.ok : null}
        horsLigne={!!lic.statut?.ok && !!lic.statut.hors_ligne}
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
      <Toasts
        toasts={toasts}
        fermer={fermerToast}
        persistants={<RappelsLicence statut={lic.statut} ouvrirLien={ouvrirLienExterne} />}
      />
    </div>
  );
}
