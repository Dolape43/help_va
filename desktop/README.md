# HelpVA — interface de bureau (Tauri v2 + React)

La nouvelle interface de HelpVA. Elle reprend la maquette (`helpva-tauri-maquette`), avec le
même design, mais elle est maintenant branchée sur le **vrai moteur Python** (dossier `engine/`,
qui utilise `agent/`).

```
 desktop/ (ce dossier)                        engine/ + agent/ (Python)
 ─────────────────────                        ─────────────────────────
 Écrans React  ──▶  src/engine/  ──tuyau──▶   helpva_engine.py  ──▶  agent/conversion.py …
                     (client JSON)            (sidecar : stdin/stdout, une ligne JSON par message)
```

L'ancienne application (`app_ctk.py`) continue de marcher à côté, sur le même `agent/`,
jusqu'à ce que la nouvelle interface sache tout faire.

## Ce qui marche déjà (Phase 0)

- **Accueil** : vrai dossier de sortie (paramètres du moteur), vrai nom et type de licence (`licence_statut`).
- **Convertir en MP4**, de bout en bout avec le vrai moteur :
  - « Importer un dossier… » et « Importer des vidéos… » : fenêtre de choix Windows (via le pont en dev,
    via `@tauri-apps/plugin-dialog` dans Tauri). La source est ensuite **vérifiée par le moteur** (`preparer`) :
    dossier vide ou source placée dans la sortie, et l'erreur s'affiche avant de lancer ;
  - « Convertir » : progression en direct, au même format que l'ancienne app
    (`Dossier 2/3 — Modèle A` / `Vidéo 1/4 · clip_07.mov — 43 %`), avec les noms complets (c'est le CSS qui les coupe) ;
  - le journal est rempli par les événements `log` du moteur ;
  - « Annuler l'opération » (ou Échap) : vraie annulation. ffmpeg s'arrête et le fichier incomplet est supprimé ;
  - la carte de résultat donne les vrais chiffres (vidéos, dossiers, fichiers ignorés), avec « Ouvrir le dossier ».
- **Paramètres** : dossier de sortie (Changer… / Ouvrir), infos de licence, version du moteur.
- **Moteur absent** : bandeau rouge « Moteur non connecté — mode démonstration ». La conversion est alors
  **simulée** (aucun fichier créé). En dev, l'interface se reconnecte toute seule dès que le pont démarre.

Les 3 autres modules (images, métadonnées, ranger) affichent « Bientôt » : ils marchent déjà dans l'ancienne app.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `src/engine/protocole.ts` | Types des messages (requête, `pret`, `progress`, `log`, `result`, `error`) et découpage des lignes JSON |
| `src/engine/transport.ts` | Le contrat d'un « tuyau » vers le moteur |
| `src/engine/pontDev.ts` | Tuyau de **dev** : `fetch POST /cmd` + `EventSource /events` vers `engine/dev_bridge.py` |
| `src/engine/sidecar.ts` | Tuyau **final** : `Command.sidecar("binaries/helpva-engine")` (plugin shell de Tauri) |
| `src/engine/client.ts` | Ids des requêtes, distribution des événements, poignée de main, délais |
| `src/engine/api.ts` | Ce que les écrans peuvent demander (`convertirMp4`, `licenceStatut`…), avec des types |
| `src/engine/simulation.ts` | Moteur de démonstration (l'ancien `engine.ts` de la maquette) |
| `src/engine/connexion.ts` | Choisit le tuyau : sidecar dans Tauri, pont en dev, sinon la démo |
| `src/engine/useMoteur.ts` | Crochet React : connexion, infos, licence, reconnexion |
| `src/engine/affichage.ts` | Événements bruts → lignes de journal / textes de progression |

**Pourquoi ce découpage ?** Les écrans ne parlent qu'à `api.ts`. On peut donc passer du pont de dev
au sidecar Tauri (ou à la démo) **sans toucher aux écrans**.

---

## 1. Développer dans le navigateur (aujourd'hui, sans Rust)

Il faut deux terminaux PowerShell, depuis la racine du dépôt (`Agent Insta`).

**Terminal 1, le moteur** (pont HTTP vers le vrai moteur Python) :

```powershell
python engine\dev_bridge.py --sans-licence
```

`--sans-licence` permet les conversions sans licence activée. C'est réservé au dev : l'exe final l'ignore.

Le pont utilise **des données de TEST** par défaut : `engine\.donnees_dev` (ignoré par git). Paramètres,
calendrier, licence et « Bureau » du moteur y sont rangés, donc vos vraies données (`%APPDATA%\HelpVA`)
et votre vrai Bureau ne sont jamais touchés. Les fichiers convertis arrivent par défaut dans
`engine\.donnees_dev\Profil\Desktop\HelpVA`. Le dossier utilisé est affiché au démarrage du pont.
(`--donnees DOSSIER` pour en choisir un autre ; `--vraies-donnees` pour le vrai profil, à éviter.)

**Terminal 2, l'interface** :

```powershell
cd desktop
npm install      # la première fois seulement
npm run dev      # http://localhost:1420
```

Ouvrez **http://localhost:1420**. Utilisez bien `localhost` et pas `127.0.0.1` : le pont n'accepte que cette origine.
En bas de la barre latérale, le point vert « Moteur » indique que le vrai moteur est connecté.
Le point rouge « Démo » indique le mode démonstration, et le survol en donne la raison.

### Le jeton du pont (comment c'est sécurisé)

Le pont écrit un jeton secret dans `engine/.dev_token`, un nouveau à chaque démarrage.
`vite.config.ts` ajoute une petite route **de dev seulement**, `/__helpva/jeton`, qui relit ce fichier :

- pas de variable `VITE_…`, car elle serait figée au lancement de Vite et fausse dès qu'on relance le pont ;
- la route n'existe pas dans le build (`apply: "serve"`) et refuse les demandes venant d'un autre site ;
- le pont n'écoute que sur 127.0.0.1 et n'accepte que l'origine `http://localhost:1420`.

### Crochets de test (dev seulement)

Dans la console du navigateur :

```js
__demo("theme", "light")           // ou "dark"
__demo("page", "mp4")              // "accueil", "parametres"
await __helpvaTest.source({ type: "dossier", chemin: "C:\\…\\mes vidéos" })  // sans fenêtre de choix
__helpvaTest.connexion()           // "connecte" | "non_connecte" | "connexion"
```

Ils servent aux tests automatiques (Edge headless) et n'existent pas dans l'app livrée.

### Vérifier avant de livrer

```powershell
npm run build    # vérification TypeScript + build de production (dossier dist/)
```

---

## 2. Plus tard : la vraie app Tauri

Ce qui est **déjà prêt** (mais pas encore testable) :

- `src-tauri/tauri.conf.json` : `productName` « HelpVA », `identifier` `app.helpva.desktop`,
  `bundle.externalBin = ["binaries/helpva-engine"]` ;
- `src-tauri/capabilities/default.json` : seulement le nécessaire. `shell:allow-spawn` est limité au
  sidecar `binaries/helpva-engine`, sans arguments. S'y ajoutent `shell:allow-stdin-write`,
  `shell:allow-kill`, `dialog:allow-open`, `opener:default`, et `core:window:allow-hide` /
  `allow-destroy` (fermeture propre, voir plus bas) ;
- `src-tauri/src/lib.rs` + `Cargo.toml` : plugins `shell`, `dialog`, `opener` ;
- côté npm : `@tauri-apps/plugin-shell`, `plugin-dialog`, `plugin-opener`.

Étapes, dans l'ordre :

1. **Installer Rust et les outils MSVC** (Visual Studio Build Tools, charge « Développement Desktop en C++ »).
   Vérifier avec `cargo --version`.
2. **Construire l'exe du moteur** avec PyInstaller (point d'entrée `engine/helpva_engine.py`, en
   **application console**, sinon pas de stdin/stdout ; voir `engine/README.md` section 6).
3. **Le copier** sous le nom exact attendu par Tauri, qui ajoute le « triplet » de la plateforme :
   `desktop/src-tauri/binaries/helpva-engine-x86_64-pc-windows-msvc.exe`.
   Le nom du triplet s'obtient avec `rustc -vV`, ligne `host:`.
   Sans ce fichier, `tauri dev` et `tauri build` refusent de compiler.
4. Lancer :
   ```powershell
   cd desktop
   npm run tauri dev     # fenêtre HelpVA, moteur lancé automatiquement en sidecar
   npm run tauri build   # installeur (dans src-tauri/target/release/bundle)
   ```

Dans Tauri, l'interface lance elle-même le moteur. À la fermeture de la fenêtre (`onCloseRequested`,
voir `src/plateforme.ts`), elle cache d'abord la fenêtre, envoie `quitter` au moteur puis **attend qu'il
se soit arrêté** avant de laisser l'app quitter. Pourquoi : sinon Tauri tuerait le moteur en pleine
conversion, et un `.mp4` à moitié écrit resterait sur le disque. D'habitude c'est immédiat ; le moteur
peut attendre jusqu'à 30 s une activation de licence en cours. Au-delà de 40 s, l'interface le tue.
Le « Job Windows » du moteur emporte aussi ses ffmpeg. (Permissions ajoutées pour ça :
`core:window:allow-hide` et `core:window:allow-destroy`.)

Garde-fou des tâches longues : une conversion n'a pas de délai maximum, mais si aucune nouvelle n'arrive
pendant 20 s, le client demande `etat` au moteur. S'il ne connaît plus la tâche deux fois de suite,
l'écran sort de « En cours » avec l'erreur `TACHE_PERDUE` au lieu d'attendre pour toujours.
En `tauri dev`, si l'exe du moteur ne démarre pas, l'interface essaie le pont de dev (s'il tourne).

> `src-tauri/binaries/*` est ignoré par git : l'exe est un **artefact de build**, jamais versionné.
