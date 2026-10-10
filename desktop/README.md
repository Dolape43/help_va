# HelpVA — interface de bureau (Tauri v2 + React)

La nouvelle interface de HelpVA, branchée sur le **vrai moteur Python** (dossier `engine/`, qui
utilise `agent/`). Tous les écrans de l'ancienne app sont là, avec les mêmes textes et les mêmes règles.

```
 desktop/ (ce dossier)                        engine/ + agent/ (Python)
 ─────────────────────                        ─────────────────────────
 Écrans React  ──▶  src/engine/  ──tuyau──▶   helpva_engine.py  ──▶  agent/conversion.py …
                     (client JSON)            (sidecar : stdin/stdout, une ligne JSON par message)
```

L'ancienne application (`app_ctk.py`) continue de marcher à côté, sur le même `agent/`,
jusqu'à la bascule.

## Les écrans

| Écran | Ce qu'il fait (commandes du moteur) |
|---|---|
| **Licence** (portail) | Vérification, activation par code, licence bloquée (expirée, résiliée, suspendue, autre PC, illisible), connexion requise avec nouvel essai automatique, bienvenue au premier lancement, rappels de fin d'abonnement, bandeau « Hors-ligne », contrôle toutes les heures (`licence_statut`, `licence_activer`, `licence_resilier`) |
| **Accueil** | Dossier de sortie, les 4 modules, pastille « En cours · 43 % » sur le module qui travaille |
| **Convertir les images** | Source (dossier ou images) → format JPG / PNG → « Remplacer ? » si `images (jpg)` existe → conversion (`preparer`, `conversion_images`) |
| **Convertir en MP4** | Source (dossier ou vidéos) → conversion, avertissement si des .mp4 seront écrasés (`preparer`, `conversion_mp4`) |
| **Changer les métadonnées** | Source (dossier ou médias) → « Renommer 1, 2, 3… » → « Remplacer ? » → traitement (`preparer`, `metadonnees`) |
| **Ranger les médias** | 1. calendrier + types cochés (mémorisés), 2. un dossier par type avec l'analyse du moteur (trouvés, manquants, ignorés), 3. aléatoire → récapitulatif « Confirmer le rangement » → rangement (`calendrier_lire`, `ranger_analyser`, `ranger_lancer`) |
| **Éditeur de calendrier** | Semaines (dupliquer, supprimer), créneaux de chaque jour (heure + type), « Vidéos uniquement », Réinitialiser, Enregistrer (`calendrier_lire`, `calendrier_defaut`, `calendrier_sauver`) |
| **Paramètres** | Dossier de sortie (Changer / Ouvrir / Réinitialiser), licence (détenteur, formule, dates), résiliation avec confirmation |

Pour les 4 modules : progression en direct au format de l'ancienne app (`Dossier 2/3 — Modèle A` /
`Vidéo 1/4 · clip.mov — 43 %`), journal détaillé, « Annuler l'opération » (ou Échap), carte de résultat
avec « Ouvrir le dossier ». **Une seule action à la fois** (comme le moteur) : les autres modules
attendent, et une notification prévient de la fin si vous êtes sur un autre écran.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `src/engine/protocole.ts` | Types des messages (requête, `pret`, `progress`, `log`, `result`, `error`) et découpage des lignes JSON |
| `src/engine/transport.ts` | Le contrat d'un « tuyau » vers le moteur |
| `src/engine/pontDev.ts` | Tuyau de **dev** : `fetch POST /cmd` + `EventSource /events` vers `engine/dev_bridge.py` |
| `src/engine/sidecar.ts` | Tuyau **final** : `Command.sidecar("binaries/helpva-engine")` (plugin shell de Tauri) |
| `src/engine/client.ts` | Ids des requêtes, distribution des événements, poignée de main, délais |
| `src/engine/api.ts` | **Le contrat** : tout ce que les écrans peuvent demander au moteur, avec des types |
| `src/engine/indisponible.ts` | Moteur absent : chaque action échoue avec un message clair (jamais de faux résultat) |
| `src/engine/connexion.ts` | Choisit le tuyau : sidecar dans Tauri, pont en dev, sinon « indisponible » |
| `src/engine/useMoteur.ts` | Crochet : connexion, infos, paramètres, reconnexion |
| `src/engine/useLicence.ts` | Crochet : vérification, activation, résiliation, contrôle périodique |
| `src/engine/useSuivi.ts` | Crochet générique : état, progression, journal et résultat d'UNE tâche longue |
| `src/engine/useTraitement.ts` | Crochet des modules MP4 / images / métadonnées : source → `preparer` → « Remplacer ? » → tâche |
| `src/engine/useRanger.ts` | Crochet du module Ranger : calendrier, types, dossiers, analyse, confirmation |
| `src/engine/affichage.ts` | Événements bruts → lignes de journal / textes de progression |
| `src/screens/ModuleTraitement.tsx` | L'écran commun des 3 modules « source → options → lancer » (chaque module ne donne que ses textes et options) |
| `src/components/module/` | Étape numérotée, journal, carte de progression, carte de résultat |
| `src/components/ranger/EditeurCalendrier.tsx` | L'éditeur de calendrier |
| `src/licence.ts` | Textes et règles de la licence (quel écran montrer, rappels) |
| `src/icones3d.ts` + `src/assets/icons/3d/` | Les icônes 3D des grandes icônes (3dicons.co, licence CC0, et images générées) ; les petites icônes de boutons restent au trait (Phosphor) |

**Pourquoi ce découpage ?** Les écrans ne parlent qu'à `api.ts`, et la logique vit dans les crochets
(`use…`). On passe du pont de dev au sidecar Tauri **sans toucher aux écrans**, et les 4 modules
partagent le même code pour la progression, le journal et l'annulation.

---

## 1. Développer : une seule commande

```powershell
cd desktop
npm install          # la première fois seulement
npm run dev:moteur   # moteur Python (pont) + interface : http://localhost:1420
```

`tools/dev.mjs` lance le pont du moteur (`python engine/dev_bridge.py --sans-licence`) puis Vite, et les
arrête ensemble avec Ctrl+C. Si l'un des deux tourne déjà (autre terminal), il est réutilisé.

- `--sans-licence` : le moteur accepte les tâches sans licence activée, et l'interface saute les écrans
  de licence (« Licence non exigée (dev) » dans la barre latérale). C'est réservé au dev : l'app livrée l'ignore.
  Pour voir les vrais écrans de licence : ouvrez `http://localhost:1420/?avec-licence` (l'interface
  ignore alors le contournement), ou relancez le moteur avec `node tools/dev.mjs --avec-licence`.
- Si Python n'est pas dans le PATH : `$env:HELPVA_PYTHON = "C:\…\python.exe"` avant la commande.
- Ouvrez bien **http://localhost:1420** et pas `127.0.0.1` : le pont n'accepte que cette origine.
- En bas de la barre latérale, le point vert « Moteur » indique que le vrai moteur est connecté ; rouge
  « Arrêté » : le moteur ne répond pas (le survol en donne la raison, le bandeau propose « Réessayer »).

Le pont utilise **des données de TEST** : `engine\.donnees_dev` (ignoré par git). Paramètres, calendrier,
licence et « Bureau » du moteur y sont rangés : vos vraies données (`%APPDATA%\HelpVA`) et votre vrai
Bureau ne sont jamais touchés. Les fichiers produits arrivent dans `engine\.donnees_dev\Profil\Desktop\HelpVA`.

### Dans la vraie fenêtre Tauri

```powershell
npm run tauri:dev
```

`src-tauri/tauri.dev.conf.json` complète la configuration pour le dev : il lance `npm run dev:moteur`
avant la fenêtre, et retire l'exe du moteur (`externalBin`), qui n'est pas encore construit. La fenêtre
essaie alors le sidecar, puis se rabat sur le pont. Les compilations Rust vont dans `D:\DevRust\target`
(variable `CARGO_TARGET_DIR`). La première compilation prend quelques minutes, les suivantes quelques secondes.

### Le jeton du pont (comment c'est sécurisé)

Le pont écrit un jeton secret dans `engine/.dev_token`, un nouveau à chaque démarrage.
`vite.config.ts` ajoute une petite route **de dev seulement**, `/__helpva/jeton`, qui relit ce fichier :

- pas de variable `VITE_…`, car elle serait figée au lancement de Vite et fausse dès qu'on relance le pont ;
- la route n'existe pas dans le build (`apply: "serve"`) et refuse les demandes venant d'un autre site ;
- le pont n'écoute que sur 127.0.0.1 et n'accepte que l'origine `http://localhost:1420`.

### Crochets de test (dev seulement)

Dans la console du navigateur :

```js
__demo("theme", "light")                       // ou "dark"
__demo("page", "images")                       // "accueil", "parametres", "mp4", "metadonnees", "ranger"
await __helpvaTest.source("images", { type: "dossier", chemin: "C:\\…\\photos" })   // sans fenêtre de choix
__helpvaTest.rangerDossier("reel", "C:\\…\\réels")                                   // dossier d'un type (Ranger)
__helpvaTest.connexion()                       // "connecte" | "non_connecte" | "connexion"
```

Ils servent aux captures automatiques (`node tools/capture.mjs`, Edge headless) et n'existent pas dans l'app livrée.

### Vérifier le code

```powershell
node_modules\.bin\tsc.cmd -p tsconfig.json --noEmit   # vérification TypeScript
```

---

## 2. Plus tard : l'app livrée (moteur intégré)

Ce qui est **déjà prêt** :

- `src-tauri/tauri.conf.json` : `productName` « HelpVA », `identifier` `app.helpva.desktop`,
  `bundle.externalBin = ["binaries/helpva-engine"]` ;
- `src-tauri/capabilities/default.json` : seulement le nécessaire. `shell:allow-spawn` est limité au
  sidecar `binaries/helpva-engine`, sans arguments. S'y ajoutent `shell:allow-stdin-write`,
  `shell:allow-kill`, `dialog:allow-open`, `opener:default` (liens http/https, pour Telegram), et
  `core:window:allow-hide` / `allow-destroy` (fermeture propre, voir plus bas) ;
- `src-tauri/src/lib.rs` + `Cargo.toml` : plugins `shell`, `dialog`, `opener`.

Étapes restantes, dans l'ordre :

1. **Construire l'exe du moteur** avec PyInstaller (point d'entrée `engine/helpva_engine.py`, en
   **application console**, sinon pas de stdin/stdout ; voir `engine/README.md` section 6).
2. **Le copier** sous le nom exact attendu par Tauri, qui ajoute le « triplet » de la plateforme :
   `desktop/src-tauri/binaries/helpva-engine-x86_64-pc-windows-msvc.exe` (triplet : `rustc -vV`, ligne `host:`).
3. `npm run tauri build` : installeur dans `D:\DevRust\target\release\bundle`.

Dans Tauri, l'interface lance elle-même le moteur. À la fermeture de la fenêtre (`onCloseRequested`,
voir `src/plateforme.ts`), elle cache d'abord la fenêtre, envoie `quitter` au moteur puis **attend qu'il
se soit arrêté** avant de laisser l'app quitter. Pourquoi : sinon Tauri tuerait le moteur en pleine
conversion, et un `.mp4` à moitié écrit resterait sur le disque. D'habitude c'est immédiat ; le moteur
peut attendre jusqu'à 30 s une activation de licence en cours. Au-delà de 40 s, l'interface le tue.
Le « Job Windows » du moteur emporte aussi ses ffmpeg.

Garde-fou des tâches longues : une conversion n'a pas de délai maximum, mais si aucune nouvelle n'arrive
pendant 20 s, le client demande `etat` au moteur. S'il ne connaît plus la tâche deux fois de suite,
l'écran sort de « En cours » avec l'erreur `TACHE_PERDUE` au lieu d'attendre pour toujours.

> `src-tauri/binaries/*` est ignoré par git : l'exe est un **artefact de build**, jamais versionné.
