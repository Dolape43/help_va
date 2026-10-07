# Moteur HelpVA (sidecar Python)

Ce dossier contient le **moteur** de HelpVA : le code d'`agent/` emballé dans un
petit programme **sans interface**, que la future app **Tauri + React** pilote.

```
 Interface Tauri (React)                     Moteur Python (ce dossier)
 ───────────────────────   stdin (requêtes)   ──────────────────────────
  convertir, annuler…   ───────────────────▶   helpva_engine.py  (plomberie)
                        ◀───────────────────     └─ commandes.py (appelle agent/)
  barre, journal, popup     stdout (événements)        └─ agent/  (inchangé)
```

**Pourquoi garder Python ?** Tout le savoir-faire (ffmpeg, uniquisation des images,
rangement, licence Ed25519…) est déjà écrit et testé dans `agent/`. On change
seulement **l'écran**, pas le cerveau. L'ancienne app `app_ctk.py` continue de
marcher en parallèle, sur le même `agent/`, tant que la nouvelle n'a pas tout.

| Fichier | Rôle |
|---|---|
| `helpva_engine.py` | Point d'entrée : lit les requêtes, lance les commandes, écrit les événements |
| `commandes.py` | Les commandes (`conversion_mp4`, `licence_statut`…) : vérifient tout, puis appellent `agent/` |
| `dev_bridge.py` | **Dev seulement** : rend le moteur joignable depuis le navigateur (HTTP + SSE) |
| `tests/test_protocole.py` | Tests (bibliothèque standard) qui lancent le vrai moteur |

`agent/` **n'a pas été modifié**.

---

## 1. Essayer le moteur à la main

Depuis la racine du dépôt (PowerShell) :

```powershell
'{"id":"1","cmd":"info"}' | python engine\helpva_engine.py
```

Le moteur répond `pret`, puis le résultat de `info`, puis s'arrête (fin de l'entrée).

> ⚠️ Lancé ainsi à la main, il lit et écrit vos **vraies** données (`%APPDATA%\HelpVA`).
> Pour jouer sans risque : `$env:APPDATA = "$env:TEMP\helpva-essai"` avant de lancer.
> (Le pont de dev, lui, utilise un dossier de test par défaut : voir section 4.)

---

## 2. Le protocole (JSON-lines)

### Format
- **Une ligne = un objet JSON**, terminée par `\n`, dans les deux sens.
- Le moteur écrit en **ASCII pur** (`json.dumps(..., ensure_ascii=True)`) : `é` devient `\u00e9`.
  Pourquoi : la page de code Windows (cp1252) ne peut plus rien casser, et même un nom
  de fichier Windows « bizarre » (UTF-16 invalide) passe. `JSON.parse` remet tout en clair.
- Le moteur lit des **octets** UTF-8 (jamais `sys.stdin` en mode texte, qui décoderait en cp1252).
- Une ligne fait au plus **16 Mo** (sinon erreur `TROP_GROS`).
- Un **BOM UTF-8** en début de ligne est accepté. `NaN` / `Infinity` (pas du JSON standard) sont
  refusés (`JSON_INVALIDE`), et le moteur n'en écrit jamais (remplacés par `null`).
- Version du protocole : **`1`** (envoyée dans `pret`). Ajouter un champ ou une commande
  ne la change pas ; un changement incompatible la passe à 2.

### Requête (interface → moteur)
```json
{"id":"c-12","cmd":"conversion_mp4","args":{"source":{"type":"dossier","chemin":"C:\\Users\\Agence\\Vidéos\\Shooting juin"}}}
```
- `id` : texte **choisi par l'interface**, unique (`c-1`, `c-2`…). L'interface enregistre
  sa « promesse en attente » **avant** d'envoyer : aucun événement rapide ne peut être perdu.
- `args` : objet (`{}` par défaut). Les clés inconnues sont ignorées.
- Les chemins doivent être **absolus, avec le lecteur** (`C:\…`) ou un partage (`\\serveur\…`).
  `\Users\x` est refusé : il dépend du lecteur courant (et Python 3.13+ ne le dit plus absolu).

### Événements (moteur → interface)
Tous ont `id` (celui de la requête, ou `null`) et `type`.

```json
{"id":null,"type":"pret","nom":"HelpVA","version":"1.0.0","protocole":1,"pid":8124,"python":"3.11.0","frozen":false}
{"id":"c-12","type":"progress","fraction":0.3818,"texte":"Dossier 2/3 — Modèle A\nVidéo 1/4 · clip_07.mov — 43 %",
 "details":{"groupe":{"mot":"Dossier","index":2,"total":3,"nom":"Modèle A"},
            "element":{"mot":"Vidéo","index":1,"total":4,"nom":"clip_07.mov","pct":43}}}
{"id":"c-12","type":"log","flux":"stdout","niveau":"info","texte":"[convert] (1/4) clip_07.mov…"}
{"id":"c-12","type":"result","data":{"traites":4,"echecs":[],"arrete":false,"dossiers":3,"sortie":"…\\media (mp4)","duree_s":41.2,"bilan":{…}}}
{"id":"c-13","type":"error","code":"OCCUPE","message":"Une action est déjà en cours, patientez…","details":{"tache":"c-12","cmd":"conversion_mp4"}}
```

Règles :
- Chaque requête reçoit **exactement un** événement final : `result` **ou** `error`.
  Avant, elle peut recevoir des `progress` et des `log`. Même une ligne illisible (`JSON_INVALIDE`,
  `TROP_GROS`) reçoit son erreur **sous son id** quand il se lit au début de la ligne
  (`{"id":"…"` en premier) ; sinon `id: null`.
- **Une annulation n'est pas une erreur** : la tâche finit par un `result` avec `arrete: true`
  (les fichiers déjà faits restent, le fichier à moitié converti est supprimé).
- `error` = « la commande n'a pas pu s'exécuter » (argument faux, source absente, exception).
  Un **refus métier** (code d'activation refusé…) est un `result` avec `ok: false`.
- `progress.texte` est **exactement** le texte de l'ancienne app. `details` donne les mêmes
  infos avec les **noms complets** : c'est l'interface qui raccourcit (CSS `text-overflow: ellipsis`).
  `details.groupe` vaut `null` quand il n'y a qu'un groupe ; `details` peut valoir `null`.
- `log.niveau` est déduit du texte : `⛔` → `arret`, `[ERREUR]` → `erreur`, `✅` → `succes`,
  `⚠️` / `[!]` / `❌` / `⏭` → `avertissement`, sinon `info`. `flux` vaut `stdout` ou `stderr`.
- Les fins de traitement renvoient `bilan: {titre, message, erreur}` : **le même texte** que
  la popup de l'ancienne app (`_fin_traitement`, `fini_ranger`). L'interface l'affiche tel quel.

### Commandes de contrôle (exécutées tout de suite, jamais en file d'attente)
| cmd | args | result |
|---|---|---|
| `annuler` | `{"cible":"c-12"}` | `{"etat":"annulation_demandee"}` / `"deja_terminee"` / `"non_annulable"` (commande rapide) |
| `etat` | — | `{"occupe":true,"tache":{"id","cmd","depuis_s","annulation_demandee","derniere_progression"},"licence_ok":…}` |
| `ping` | — | `{"pong":true}` |
| `quitter` | `{"delai_s":5}` | `{"ok":true,"tache_terminee":true}` puis le moteur s'arrête (code 0) |

`annuler` est **idempotent** : l'envoyer deux fois ne pose aucun problème. Le journal
« ⛔ Annulation demandée » part sous l'id de la tâche, **avant** son événement final.
Les commandes de contrôle passent aussi le contrôle `ID_DUPLIQUE` (un `ping` avec l'id d'une
conversion en cours est refusé : sinon la conversion aurait deux événements finaux).

### Concurrence
- **Tâches longues** (`L`) : une seule à la fois, dans un fil dédié, annulables
  (comme `self.occupe` de l'ancienne app). Le test « déjà occupé ? » et la réservation se
  font **sous verrou, avant** de lancer le fil : deux clics très rapprochés → un accepté,
  l'autre `OCCUPE`.
- **Commandes rapides** (`R`) : jusqu'à 4 en parallèle, **même pendant** une conversion.
- **Commandes réseau** (`N` : `licence_statut`, `licence_activer`) : comme `R`, mais dans un
  **autre** groupe de 4 fils. Hors-ligne, `licence_statut` peut durer **environ 40 s**
  (6 s Supabase + 3 × 6 s HTTPS + 3 × 5 s NTP pour lire la vraie date) : elle ne bloque donc
  jamais `preparer`, `parametres_lire`… Plusieurs `licence_statut` simultanés (« Réessayer »
  cliqué 3 fois) partagent **une seule** vérification.
- `parametres.json` / `calendrier_utilisateur.json` : lectures et écritures du moteur passent par
  un verrou, et le moteur écrit **d'un coup** (fichier `.tmp` puis `os.replace`) : une lecture ne
  voit jamais un fichier à moitié écrit (sinon : valeurs par défaut, donc une autre sortie).
- **Licence et courses** : une « génération » change à chaque résiliation / activation. Un
  `licence_statut` lent, lancé avant une résiliation, ne peut plus rallumer `licence_ok` après.
- **Licence** : une tâche longue est refusée (`LICENCE_REQUISE`) tant que `licence_statut`
  n'a pas répondu `ok: true` pendant la session. Défense en profondeur : l'écran
  d'activation, lui, reste dans l'interface.

### stdout est réservé au protocole (le point délicat)
Au tout début de `helpva_engine.py`, **avant** d'importer `agent` :
1. on garde une copie **privée** des vrais tubes (entrée et sortie) ;
2. on branche les descripteurs 0 et 1 (et les poignées standard Windows) sur « nul » :
   une écriture parasite part à la poubelle, et **ffmpeg hérite d'une entrée vide**
   (sous Windows il lit stdin pour ses raccourcis `q`/`?` : il pourrait sinon voler
   des octets d'une commande, par exemple un `annuler`) ;
3. `sys.stdout` / `sys.stderr` sont remplacés : chaque **ligne** de `print()` devient un
   événement `log`, rattaché au bon `id` (mémoire **par fil** jusqu'au `\n`) ;
4. le **vrai stderr** reste libre pour les plantages durs (`faulthandler`) : Tauri le garde à part ;
5. toutes les lignes du protocole passent par **un seul verrou** : jamais deux lignes mélangées.

Le test `test_stdout_reste_propre` vérifie tout ça (print, stderr, écriture brute sur le
fd 1, sous-processus qui écrit et qui lit).

### Démarrage et arrêt
- `pret` part **tout de suite** (PIL, numpy, cryptography sont chargés à la première commande
  qui en a besoin). L'interface met en file les requêtes envoyées avant `pret`
  (délai conseillé : 20 s, sinon « Moteur indisponible »).
- Si `pret.protocole` ≠ celui de l'interface : erreur fatale « Réinstallez HelpVA ».
- **`quitter`** : annule la tâche longue, attend au plus `delai_s`, répond, puis s'arrête.
  Les commandes **critiques** en cours (`licence_activer`, `licence_resilier`, `parametres_ecrire`,
  `calendrier_sauver`) ont droit à **30 s** : coupée au milieu, une activation pourrait consommer
  le code sans écrire `licence.key`. Côté Tauri, on attend donc la fin du moteur (40 s maximum,
  fenêtre déjà cachée) avant de quitter.
- **Fin de l'entrée (EOF)** : l'interface est fermée ou a planté → même arrêt, sans réponse.
  C'est **la** garantie qu'aucun moteur ne reste en arrière-plan.
- **`quitter` suivi aussitôt de l'EOF** (le cas normal d'une app qui se ferme) : le second arrêt
  **attend** le premier (réponse à `quitter`, fin de la tâche, fichier partiel supprimé), puis
  le moteur sort avec le code 0 (testé).
- **Ctrl+C est ignoré** par le moteur : seuls `quitter` et l'EOF l'arrêtent, toujours proprement.
- **Job Windows** : le moteur se place lui-même dans un « Job » qui tue ses enfants avec lui.
  Si on le tue brutalement (Gestionnaire des tâches), les **ffmpeg** meurent aussi
  (testé par `test_moteur_tue_brutalement_ffmpeg_meurt_aussi`).

### Codes d'erreur
| code | quand |
|---|---|
| `JSON_INVALIDE` | ligne illisible (son id s'il se lit au début de la ligne, sinon `id: null`) |
| `TROP_GROS` | ligne de plus de 16 Mo (idem) |
| `COMMANDE_INCONNUE` | `cmd` inconnue |
| `ARGUMENTS_INVALIDES` | `details.champ` dit lequel (`id` absent → `id: null`) |
| `ID_DUPLIQUE` | `id` déjà en cours → **`id: null`**, l'id fautif dans `details.id` (sinon le client croirait que sa requête en cours a échoué) |
| `OCCUPE` | tâche longue déjà active (`details.tache`) |
| `ARRET_EN_COURS` | requête reçue après `quitter` |
| `LICENCE_REQUISE` | tâche longue sans licence valide |
| `SOURCE_INTROUVABLE` | dossier/fichier absent (`details.chemins`, `details.types` pour ranger) |
| `SOURCE_VIDE` | aucune vidéo / image utile (vérifié **avant** d'appeler `agent/`) |
| `SOURCE_DANS_SORTIE` | la source est la sortie ou dedans (sinon `rmtree` la détruirait) |
| `SORTIE_EXISTE` | la sortie existe et `remplacer` n'est pas **ce chemin-là** (`details.sortie` = le chemin à confirmer) |
| `SORTIE_VERROUILLEE` | un fichier est ouvert dans la sortie à remplacer (visionneuse, Explorateur…) : **rien n'a été effacé** (`details.sortie`) |
| `CHEMIN_TROP_LONG` | chemin trop long pour Windows sans « LongPathsEnabled » (dossier ≥ 248, fichier ≥ 260 caractères ; `details.chemins`) |
| `CALENDRIER_INVALIDE` | `ranger_lancer` : le calendrier enregistré a un nom de dossier impossible (`CON`, `NUL`…), vérifié **avant** de toucher la sortie |
| `SORTIE_INACCESSIBLE` | impossible de créer le dossier de sortie |
| `FFMPEG_INTROUVABLE` | `imageio_ffmpeg` absent ou cassé |
| `CHEMIN_REFUSE` | `ouvrir_dans_explorateur` sur autre chose qu'un dossier |
| `ERREUR_INTERNE` | exception imprévue : `message = str(e)`, trace complète en `log` niveau `erreur`, `details.titre` = titre de la popup de l'ancienne app |
| *(côté client)* `MOTEUR_ARRETE`, `DELAI_DEPASSE`, `PROTOCOLE_INCOMPATIBLE`, `NON_AUTORISE` (pont), `TACHE_PERDUE` (tâche longue que le moteur ne connaît plus, vérifié par `etat`) | |

---

## 3. Les commandes

`Source = {"type":"dossier","chemin":str} | {"type":"fichiers","chemins":[str]}`
`L` = longue (une à la fois, annulable) · `R` = rapide · `N` = rapide, réseau (groupe de fils à part).

**`remplacer`** = le **chemin exact** renvoyé par `preparer` (champ `sortie`), jamais `true`.
Le moteur ne supprime l'ancienne sortie que si c'est **ce** dossier : si la sortie a changé
entre-temps (paramètre modifié, clé USB retirée → repli sur le Bureau), il répond `SORTIE_EXISTE`
avec le nouveau chemin. Le remplacement **renomme** d'abord le dossier (échec d'un bloc si un
fichier est ouvert → `SORTIE_VERROUILLEE`, rien d'effacé), puis supprime la copie renommée.
Une annulation reçue avant ce moment ne supprime **rien** (`result` avec `arrete: true`).

| cmd | | args | result (principaux champs) |
|---|---|---|---|
| `info` | R | — | `nom, version, protocole, python, plateforme, frozen, pid, dossier_donnees, dossier_sortie, extensions{…}, types_ranger[…], images_par_carrousel, commandes` |
| `ouvrir_dans_explorateur` | R | `{chemin}` (dossier existant) | `{ok}` |
| `preparer` | R | `{commande, args}` (mêmes args que la commande longue) | `{sortie, existe, remplacement, nb_medias}` (+ `deja_presents` pour `conversion_mp4` : .mp4 qui seront écrasés) — pour poser « Remplacer ? » **avant** |
| `licence_statut` | N | — | statut de `licence.verifier()` (`ok, raison, type, expire_le "AAAA-MM-JJ", debut_le, jours_restants, nom, hors_ligne`) + `empreinte` |
| `licence_activer` | N | `{code}` | `{ok, message, statut}` (`ok:false` = refus, pas une erreur) |
| `licence_resilier` | R | — | `{ok}` |
| `parametres_lire` | R | — | `{parametres, dossier_sortie, dossier_sortie_defaut, personnalise}` |
| `parametres_ecrire` | R | `{valeurs:{theme?, dossier_sortie?, ranger_types?, deja_demarre?}}` | comme `parametres_lire` |
| `dossier_sortie` | R | — | `{chemin, defaut, personnalise}` (le dossier est créé, comme avant) |
| `calendrier_lire` | R | — | `{calendrier, semaines, compte{type:n}, creneaux, personnalise}` |
| `calendrier_defaut` | R | — | le calendrier d'origine (bouton « Réinitialiser ») |
| `calendrier_sauver` | R | `{calendrier}` (validé : les noms deviennent des dossiers) | `{…, message}` |
| `ranger_analyser` | R | `{sources:{type:dossier}, types?}` | `{types{…}, actifs, sortie, existe, manquants, source_dans_sortie, doublons, incomplet, calendrier_erreur, pret, message_confirmation}` |
| `conversion_mp4` | L | `{source}` | `{traites, echecs, arrete, dossiers, sortie, duree_s, bilan}` → `<sortie>/media (mp4)` (rien n'est supprimé, comme avant) |
| `conversion_images` | L | `{source, format:"jpg"\|"png" (défaut jpg), remplacer?: chemin}` | idem → `images (jpg)` / `images (png)` |
| `metadonnees` | L | `{source, renommer?=true, remplacer?: chemin}` | idem → `<nom> (métadonnées changées)` ou `media (métadonnées changées)` |
| `ranger_lancer` | L | `{sources, types?, aleatoire?=true, remplacer?: chemin}` | résultat de `ranger()` + `sortie, duree_s, bilan` → `ranger` |

Valeurs par défaut (comme les cases de l'ancienne app) : `renommer = true` (« recommandé »),
`aleatoire = true`, `format = "jpg"`.

Déroulé type d'un bouton « Convertir les images » :
1. `preparer` → si `remplacement` est vrai, l'interface demande « Remplacer ? » en montrant `sortie` ;
2. `conversion_images` avec `remplacer: "<sortie>"` (le **moteur** revérifie tout, et ne remplace que ce dossier) ;
3. `progress` / `log` en direct → `result` → popup avec `bilan`.

---

## 4. Le pont de développement (`dev_bridge.py`)

Tant que Rust n'est pas installé, `tauri dev` ne marche pas. Le pont permet de
développer l'interface React **dans le navigateur** (`npm run dev` → `http://localhost:1420`)
avec le **vrai** moteur.

```powershell
python engine\dev_bridge.py --sans-licence  # http://127.0.0.1:8765, tâches longues sans licence
```

**Données de test par défaut** : le moteur lancé par le pont travaille dans `engine/.donnees_dev`
(ignoré par git). `APPDATA`, `USERPROFILE` et `HOME` du moteur y pointent : ses paramètres, son
calendrier, sa licence et son « Bureau » (`.donnees_dev\Profil\Desktop\HelpVA`, la sortie par
défaut) sont à part. On ne touche donc **jamais** à `%APPDATA%\HelpVA` ni au vrai Bureau.
Le dossier utilisé s'affiche au démarrage.
- `--donnees DOSSIER` : un autre dossier de test ;
- `--vraies-donnees` : le **vrai** profil (à éviter).

Au démarrage il affiche un **jeton** et l'écrit dans `engine/.dev_token` (ignoré par git).
Ctrl+C l'arrête proprement (le moteur aussi) : le moteur tourne dans un **groupe de processus à
part**, le Ctrl+C n'arrive qu'au pont, qui envoie `quitter`.

| Route | Rôle |
|---|---|
| `POST /cmd` | corps `{"id","cmd","args"}` → réponse `202` immédiate ; la suite arrive par `/events` |
| `GET /events?token=…` | flux SSE : chaque événement du moteur en `data: {json}` (`pret` est rejoué à la connexion) |
| `GET /health` | `{ok, moteur_vivant, pret, pid_moteur}` |

Sécurité : écoute **uniquement** sur `127.0.0.1` ; jeton obligatoire (en-tête
`X-HelpVA-Token`, ou `?token=` pour `EventSource` qui ne sait pas envoyer d'en-tête) ;
CORS **seulement** pour `http://localhost:1420` ; en-tête `Host` vérifié.

Commandes **propres au pont** (fenêtres de choix tkinter ; dans Tauri ce sera le
plugin `dialog`) :
- `choisir_dossier` `{titre?}` → `{chemin: str | null}`
- `choisir_fichiers` `{titre?, filtre?: "videos"|"images"|"medias"|"tous"}` → `{chemins: [...]}`

Côté React, en dev (exemple) :
```ts
const JETON = import.meta.env.VITE_HELPVA_TOKEN;      // lu depuis engine/.dev_token par vite.config.ts
const flux = new EventSource(`http://127.0.0.1:8765/events?token=${JETON}`);
flux.onmessage = (m) => recevoir(JSON.parse(m.data));
await fetch("http://127.0.0.1:8765/cmd", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-HelpVA-Token": JETON },
  body: JSON.stringify({ id: "c-1", cmd: "info", args: {} }),
});
```

---

## 5. Les tests

```powershell
cd engine
python -m unittest -v
```

Les tests lancent le **vrai** moteur comme sous-processus, avec `APPDATA`, `USERPROFILE`
et `HOME` dirigés vers un **dossier temporaire** (jamais les vraies données ni le vrai
Bureau). Ils fabriquent de petites vidéos avec le ffmpeg d'`imageio-ffmpeg`, dans des
dossiers avec **espaces et accents**. Ils vérifient : poignée de main, `info`, paramètres
aller-retour, **vraie conversion MP4** (progression texte + fraction, fichiers H.264),
**annulation en moins de 2 s** (sans fichier partiel), `OCCUPE` / `ID_DUPLIQUE` (aussi pour
`ping`), erreurs (BOM, NaN, ligne de 17 Mo avec son id, chemin sans lecteur, chemin trop long),
stdout jamais corrompu, licence requise, images / métadonnées / rangement, **remplacement lié au
chemin confirmé** (refus si autre chemin, `SORTIE_VERROUILLEE` si un fichier est ouvert, repli
USB → même chemin annoncé et remplacé), annulation juste après le lancement (rien supprimé),
noms réservés du calendrier, `quitter`, **`quitter` puis EOF immédiat pendant une conversion**,
EOF, Job Windows, signature de `progression.texte`, et le pont de dev (jeton, CORS, SSE, données
de test). Durée : environ 1 minute.

Variables d'environnement **de développement** (ignorées dans l'exe PyInstaller) :
- `HELPVA_MOTEUR_SANS_LICENCE=1` : autorise les tâches longues sans licence ;
- `HELPVA_MOTEUR_TESTS=1` : active la commande de test `_diagnostic_bruit`.

---

## 6. Plus tard : l'exe du moteur (PyInstaller) pour Tauri

- Point d'entrée : `engine/helpva_engine.py` (avec `agent/` dans les imports cachés si besoin).
- **Application console obligatoire** (`console=True`) : une app « fenêtrée » n'a pas de
  stdin/stdout, le protocole ne marcherait pas. Tauri lance le sidecar sans fenêtre visible.
- Nom attendu par Tauri : `desktop/src-tauri/binaries/helpva-engine-x86_64-pc-windows-msvc.exe`
  (déclaré dans `bundle.externalBin` : `binaries/helpva-engine`).
- Déclarer **`longPathAware`** dans le manifeste de l'exe (en plus du réglage Windows
  « LongPathsEnabled ») pour accepter les chemins de plus de 260 caractères. Sans ça, le moteur
  répond `CHEMIN_TROP_LONG` (message clair) au lieu de « introuvable ».
- Pistes `agent/` (non faites ici, l'ancienne app marche sans) : ajouter `-nostdin` et
  `stdin=subprocess.DEVNULL` aux appels ffmpeg de `conversion.py` (le moteur s'en protège
  déjà de son côté, voir « stdout est réservé »).
