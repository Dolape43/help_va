/**
 * Ce qui ne sert QUE dans la vraie fenêtre Tauri.
 * Dans le navigateur (npm run dev), isTauri() renvoie false et on ne fait rien :
 * la maquette marche donc dans les deux cas.
 */
import { isTauri } from "@tauri-apps/api/core";
import { getVersion } from "@tauri-apps/api/app";
import { getCurrentWindow } from "@tauri-apps/api/window";

export const DANS_TAURI = isTauri();

/** Version de l'app : celle de tauri.conf.json dans Tauri, celle de package.json sinon (même valeur). */
export async function versionApp(): Promise<string> {
  if (!DANS_TAURI) return __APP_VERSION__;
  try {
    return await getVersion();
  } catch {
    return __APP_VERSION__;
  }
}

/**
 * La barre de titre Windows suit le thème du SYSTÈME, pas celui de l'app.
 * Sans ça : app sombre sous une barre de titre claire. Il faut la permission
 * "core:window:allow-set-theme" (src-tauri/capabilities/default.json).
 */
export function themeFenetre(theme: "light" | "dark") {
  if (!DANS_TAURI) return;
  getCurrentWindow()
    .setTheme(theme)
    .catch(() => {
      /* pas grave : seule la barre de titre garde la couleur du système */
    });
}

/**
 * Fermeture de la fenêtre (Tauri seulement) : on ATTEND que le moteur se soit arrêté proprement.
 *
 * Pourquoi : sans ça, la fenêtre se ferme, l'app quitte et Tauri tue le moteur aussitôt,
 * en pleine conversion : un .mp4 à moitié écrit resterait sur le disque.
 * Déroulé : 1) on cache la fenêtre (l'utilisateur la voit se fermer tout de suite) ;
 *           2) `nettoyer()` envoie « quitter » au moteur et attend sa fin (sidecar.ts) ;
 *           3) au retour du gestionnaire, Tauri détruit la fenêtre (pas de preventDefault).
 * Permissions : core:window:allow-hide et core:window:allow-destroy (capabilities/default.json).
 *
 * Renvoie la fonction qui retire l'écouteur.
 */
export async function avantFermeture(nettoyer: () => Promise<void>): Promise<() => void> {
  if (!DANS_TAURI) return () => {};
  const fenetre = getCurrentWindow();
  let enCours: Promise<void> | null = null;
  return fenetre.onCloseRequested(async () => {
    await fenetre.hide().catch(() => {});
    // Deux clics sur « fermer » : on attend le MÊME arrêt, sans le relancer.
    enCours ??= nettoyer().catch(() => {});
    await enCours;
  });
}

/**
 * Ouvre un lien (Telegram du vendeur…) dans le navigateur de l'utilisateur.
 * Dans Tauri, la fenêtre de l'app n'est PAS un navigateur : un simple lien s'ouvrirait dedans.
 * Le plugin « opener » le confie au navigateur par défaut (permission opener:default = http/https).
 */
export async function ouvrirLien(url: string): Promise<void> {
  if (!DANS_TAURI) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

/**
 * Notification système (Windows) : « HelpVA — Conversion terminée » quand un traitement finit
 * pendant que l'utilisateur est dans une autre fenêtre.
 * Dans Tauri : plugin officiel « notification » (permission notification:default).
 * Dans le navigateur (pont de dev) : l'API Notification du navigateur.
 * La permission est demandée au PREMIER usage seulement. Jamais d'erreur remontée : une
 * notification manquée n'est pas grave (le toast et la carte de résultat sont là).
 */
export async function notifierSysteme(titre: string, texte: string): Promise<void> {
  try {
    if (DANS_TAURI) {
      const { isPermissionGranted, requestPermission, sendNotification } = await import("@tauri-apps/plugin-notification");
      let permis = await isPermissionGranted();
      if (!permis) permis = (await requestPermission()) === "granted";
      if (permis) sendNotification({ title: titre, body: texte });
      return;
    }
    if (typeof Notification === "undefined") return;
    let permission = Notification.permission;
    if (permission === "default") permission = await Notification.requestPermission();
    if (permission === "granted") new Notification(titre, { body: texte });
  } catch {
    /* notifications bloquées ou indisponibles : tant pis */
  }
}

/**
 * Une app de bureau n'a pas le menu clic droit du navigateur (Précédent, Actualiser, Imprimer…).
 * On le garde seulement sur les textes sélectionnables (chemins, journal) pour pouvoir copier.
 */
export function desactiverMenuNavigateur() {
  if (!DANS_TAURI) return;
  document.addEventListener("contextmenu", (e) => {
    const cible = e.target as Element | null;
    if (!cible?.closest?.(".selectable, input, textarea")) e.preventDefault();
  });
}
