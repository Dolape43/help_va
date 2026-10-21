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

`agent/` n'a presque pas été modifié : seulement `agent/comptes.py` (nouveau, les comptes du
module Ranger) et un paramètre **optionnel** `calendrier` dans `agent/ranger.ranger()`. L'ancienne
app ne s'en sert pas : pour elle, rien ne change.

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
- `parametres.json` / `calendrier_utilisateur.json` / `comptes_ranger.json` : lectures et écritures
  du moteur passent par un verrou, et le moteur écrit **d'un coup** (fichier `.tmp` puis
  `os.replace`) : une lecture ne voit jamais un fichier à moitié écrit (sinon : valeurs par défaut,
  donc une autre sortie, ou tous les comptes perdus).
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
  `calendrier_sauver`, `comptes_sauver`) ont droit à **30 s** : coupée au milieu, une activation pourrait consommer
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
| `ARGUMENTS_INVALIDES` | `details.champ` dit lequel (`id` absent → `id: null`). Liste de comptes (`comptes_sauver`, `ranger_*` avec `comptes`) : le message **nomme** le compte fautif (« @marie : … », ou « Compte n°2 : … » si c'est son nom qui pose problème) et `details.compte` = son id |
| `ID_DUPLIQUE` | `id` déjà en cours → **`id: null`**, l'id fautif dans `details.id` (sinon le client croirait que sa requête en cours a échoué) |
| `OCCUPE` | tâche longue déjà active (`details.tache`) |
| `ARRET_EN_COURS` | requête reçue après `quitter` |
| `LICENCE_REQUISE` | tâche longue sans licence valide |
| `SOURCE_INTROUVABLE` | dossier/fichier absent (`details.chemins` ; pour ranger : `details.types` et `details.compte` = id du compte concerné) |
| `SOURCE_VIDE` | aucune vidéo / image utile (vérifié **avant** d'appeler `agent/`) |
| `SOURCE_DANS_SORTIE` | la source est la sortie ou dedans (sinon `rmtree` la détruirait ; pour ranger : `details.types`, `details.compte`) |
| `SORTIE_EXISTE` | la sortie existe et `remplacer` n'est pas **ce chemin-là** (`details.sortie` = le chemin à confirmer) |
| `SORTIE_VERROUILLEE` | un fichier est ouvert dans la sortie à remplacer (visionneuse, Explorateur…) : **rien n'a été effacé** (`details.sortie`) |
| `CHEMIN_TROP_LONG` | chemin trop long pour Windows sans « LongPathsEnabled » (dossier ≥ 248, fichier ≥ 260 caractères ; `details.chemins`) |
| `CALENDRIER_INVALIDE` | `ranger_lancer` : le calendrier enregistré, ou celui d'un compte (`details.compte`), a un nom de dossier impossible (`CON`, `NUL`…), vérifié **avant** de toucher la sortie |
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
| `dossier_existe` | R | `{chemin}` | `{existe, plein}` (dossier absolu existant / non vide ; sert à griser « Ouvrir le dossier du résultat ») |
| `preparer` | R | `{commande, args}` (mêmes args que la commande longue) | `{sortie, existe, remplacement, nb_medias}` (+ `deja_presents` pour `conversion_mp4` : .mp4 qui seront écrasés) — pour poser « Remplacer ? » **avant** |
| `licence_statut` | N | — | statut de `licence.verifier()` (`ok, raison, type, expire_le "AAAA-MM-JJ", debut_le, jours_restants, nom, hors_ligne`) + `empreinte` |
| `licence_activer` | N | `{code}` | `{ok, message, statut}` (`ok:false` = refus, pas une erreur) |
| `licence_resilier` | R | — | `{ok}` |
| `parametres_lire` | R | — | `{parametres, dossier_sortie, dossier_sortie_defaut, personnalise}` |
| `parametres_ecrire` | R | `{valeurs:{theme?, dossier_sortie?, ranger_types?, deja_demarre?, format_images?, renommer_images?, renommer_mp4?, renommer_metadonnees?, ranger_aleatoire?, fin_ouvrir_dossier?, fin_notification?}}` (voir « Paramètres » ci-dessous) | comme `parametres_lire` |
| `activite_lire` | R | — | `{aujourd_hui, semaine, mois, total, depuis, partage}` (voir « Compteur d'activité » ci-dessous) |
| `dossier_sortie` | R | — | `{chemin, defaut, personnalise}` (le dossier est créé, comme avant) |
| `calendrier_lire` | R | — | `{calendrier, semaines, compte{type:n}, creneaux, personnalise}` |
| `calendrier_defaut` | R | — | le calendrier d'origine (bouton « Réinitialiser ») |
| `calendrier_sauver` | R | `{calendrier}` (validé : les noms deviennent des dossiers) | `{…, message}` |
| `comptes_lire` | R | — | `{comptes: [{id, nom, sources, calendrier, vue}], max: 50}` (voir « Ranger : plusieurs comptes ») |
| `comptes_sauver` | R | `{comptes: [{id, nom, sources, calendrier}]}` (la liste COMPLÈTE, tout est vérifié avant d'écrire) | comme `comptes_lire` + `message: "Enregistré."` |
| `ranger_analyser` | R | `{comptes?: [...], sources?:{type:dossier}, types?}` | `{types{…}, actifs, sortie, existe, manquants, source_dans_sortie, doublons, incomplet, calendrier_erreur, pret, message_confirmation, comptes[…], partages[…]}` |
| `conversion_mp4` | L | `{source, renommer?=false}` (1.mp4, 2.mp4… par dossier, à la suite de l'existant) | `{traites, echecs, arrete, dossiers, sortie, duree_s, bilan}` → `<sortie>/media (mp4)` (rien n'est supprimé, comme avant) |
| `conversion_images` | L | `{source, format:"jpg"\|"png" (défaut jpg), renommer?=false (1, 2, 3… à la suite), remplacer?: chemin}` | idem → `images (jpg)` / `images (png)` |
| `metadonnees` | L | `{source, renommer?=true, remplacer?: chemin}` | idem → `<nom> (métadonnées changées)` ou `media (métadonnées changées)` |
| `ranger_lancer` | L | `{comptes?, sources?, types?, aleatoire?=true, remplacer?: chemin}` | résultat de `ranger()` (totaux) + `sortie, duree_s, bilan, comptes[…]` → `ranger` |

Valeurs par défaut (comme les cases de l'ancienne app) : `renommer = true` (« recommandé »),
`aleatoire = true`, `format = "jpg"`.

### Paramètres (`parametres.json`)
| clé | valeurs | défaut | rôle |
|---|---|---|---|
| `theme` | `"light"` \| `"dark"` | `"light"` | thème de l'interface |
| `dossier_sortie` | chemin absolu ou `""` | `""` (Bureau\HelpVA) | dossier de sortie |
| `ranger_types` | `{type: bool}` | tous cochés | types de posts du Ranger |
| `deja_demarre` | bool | absent | 1er démarrage déjà fait |
| `format_images` | `"jpg"` \| `"png"` | `"jpg"` | choix par défaut du module Images |
| `renommer_images` | bool | `false` | Images : « Renommer 1, 2, 3… » |
| `renommer_mp4` | bool | `false` | MP4 : « Renommer 1, 2, 3… » |
| `renommer_metadonnees` | bool | `true` | Métadonnées : « Renommer 1, 2, 3… » |
| `ranger_aleatoire` | bool | `true` | Ranger : « Répartir au hasard » |
| `fin_ouvrir_dossier` | bool | `false` | fin de traitement : ouvrir le dossier du résultat |
| `fin_notification` | bool | `true` | fin de traitement : notification (si HelpVA n'est pas au premier plan) |

Les défauts sont dans `agent/parametres.py` (`_DEFAUT`) : `parametres_lire` renvoie toujours
toutes les clés. Une mauvaise valeur → `ARGUMENTS_INVALIDES` avec `details.champ = "valeurs.<clé>"`.
Ces choix ne changent PAS les défauts des commandes (`renommer`, `aleatoire`, `format`) :
c'est l'interface qui les lit et les passe en arguments.

### Compteur d'activité (`activite.json`, `agent/activite.py`)
Chaque traitement terminé (même arrêté en cours de route) ajoute ce qui a **vraiment** été
traité, au jour LOCAL du PC : `images` (`conversion_images`), `videos` (`conversion_mp4`),
`metadonnees` (`metadonnees`), `ranges` (`ranger_lancer`, somme des `places` de tous les comptes).
```json
{"version": 1,
 "jours":  {"2026-10-22": {"images": 12, "videos": 3, "metadonnees": 40, "ranges": 87}},
 "envoye": {"2026-10-22": {"images": 12, "videos": 3, "metadonnees": 40, "ranges": 87}},
 "anciens": {"images": 0, "videos": 0, "metadonnees": 0, "ranges": 0, "depuis": null}}
```
- 400 jours gardés au plus ; les jours purgés vont dans `anciens` (le total reste juste).
  Fichier illisible : mis de côté (`activite.illisible-AAAAMMJJ-HHMMSS.json`), on repart de zéro.
  Le compteur ne fait **jamais** échouer un traitement.
- `activite_lire` → `aujourd_hui`, `semaine` (7 derniers jours, aujourd'hui compris), `mois`
  (30 derniers jours), `total` : chacun `{images, videos, metadonnees, ranges, total}` ; `depuis`
  = 1er jour compté (`"AAAA-MM-JJ"` ou `null`) ; `partage` = `true` si une licence est
  enregistrée (les compteurs sont alors envoyés à l'agence).
- **Envoi** : dans un fil d'arrière-plan, ~5 s après le démarrage puis après chaque traitement.
  POST `<SUPABASE_URL>/functions/v1/admin` `{action: "activite", licence, jours: [{jour, images,
  videos, metadonnees, ranges}]}` = les jours (30 derniers au plus) qui diffèrent de `envoye`
  (valeurs **absolues** du jour) ; `{ok: true}` → `envoye` mis à jour. Timeout 8 s, aucune erreur
  visible, jamais deux envois en même temps. **Sans licence enregistrée, rien ne part** (aucun
  appel réseau : mode dev, tests).

### Ranger : plusieurs comptes
Chaque compte a **ses propres dossiers sources** et **son calendrier**. Fichier
`comptes_ranger.json` (dans `%APPDATA%\HelpVA`, écrit par `agent/comptes.py`) :
```json
{"version": 1, "comptes": [
  {"id": "c1", "nom": "Compte 1", "sources": {"reel": "C:\\…", "story": "C:\\…"}, "calendrier": null}
]}
```
- `calendrier: null` = le calendrier d'origine (`agent.calendrier.CALENDRIER`). `comptes_sauver`
  enregistre `null` un calendrier identique à celui d'origine. `vue` = le résumé du calendrier
  **effectif** `{calendrier, semaines, compte, creneaux, personnalise}` (`personnalise` = non `null`).
- **1re ouverture** (fichier absent) : un seul compte « Compte 1 », sans dossiers, dont le
  calendrier est celui déjà enregistré (`calendrier_utilisateur.json`), sinon `null`. Rien n'est
  écrit avant le premier `comptes_sauver`. Fichier **illisible** (JSON cassé…) : il est d'abord
  **mis de côté** (`comptes_ranger.illisible-AAAAMMJJ-HHMMSS.json`, jamais écrasé), puis même
  départ. Fichier qu'on ne peut pas ouvrir (verrouillé) : `comptes_lire` échoue, sans repli. Un id
  lu que le moteur refuserait (vide, en double, espaces au bord, plus de 64 caractères) est remplacé.
- `comptes_sauver` vérifie **tout** : 1 à 50 comptes, ids uniques (un id absent ou vide est créé :
  `c1`, `c2`…), noms de 1 à 40 caractères (espaces de bord retirés) valables comme **nom de dossier
  Windows** (noms réservés CON, NUL, COM0-9, LPT0-9, COM¹…, CONIN$… refusés, comme `~` suivi d'un
  chiffre : « COMPTE~1 » est le nom court du dossier « Compte 1 ») et uniques **sans tenir compte de
  la casse**, `sources` = `{type: chemin absolu}` (vide = pas encore choisi), calendrier `null` ou
  valide. Un calendrier **déjà enregistré** (identique à celui d'un compte du fichier, ou repris de
  `calendrier_utilisateur.json`) est gardé tel quel, même invalide : il ne bloque pas un changement
  de nom ou de dossier ; le rangement, lui, reste refusé (`calendrier_erreur`, `CALENDRIER_INVALIDE`).
  Un seul compte fautif → rien n'est enregistré ; `details.compte` = son id, `null` s'il n'en a pas.
- `ranger_analyser` / `ranger_lancer` :
  - **avec `comptes`** : dossiers et calendriers pris **dans les args** (ce que l'interface affiche),
    jamais dans le fichier ;
  - **sans `comptes`** (ancien mode) : un compte implicite (`id: "c1"`) avec `sources` et le
    calendrier enregistré, exactement comme avant.
- Les types cochés (`types`, sinon `ranger_types` des paramètres) sont **communs** à tous les comptes.
  Types actifs d'un compte = cochés **et** présents dans **son** calendrier. Un compte sans type actif
  est **ignoré** (signalé dans le message, `aucun_type: true` dans le résultat).
- Sortie : toujours `<dossier de sortie>/ranger`, remplacé **en entier** (une seule fois) :
  - **1 compte** : arborescence d'avant `ranger/semaine-XX/jour-Y/<ordre>_<heure>_<type>/` + `ranger/surplus/…` ;
  - **2 comptes ou plus** : `ranger/<nom du compte>/semaine-XX/…` et `ranger/<nom du compte>/surplus/…`.
- Bloquant (`pret: false`, puis erreur au lancement, **avant** de toucher la sortie) : aucun type actif
  dans aucun compte, un type actif sans dossier valide, un dossier source **dans** `ranger` (même dans
  le sous-dossier d'un autre compte), un calendrier invalide. **Avertissement seulement** : `partages`
  = dossiers utilisés par au moins 2 comptes pour la même sorte de média (mêmes médias rangés
  plusieurs fois) ; `doublons` = même dossier pour deux types d'images **dans** un compte.
- Réponse de `ranger_analyser` : les champs d'avant sont les **totaux** (`types` additionnés sur les
  comptes où le type est actif, sur tous s'il ne l'est nulle part, avec
  `dossier`/`dossier_valide` du compte s'il n'y en a qu'un, `dossier: null` sinon ; `actifs`,
  `manquants`, `source_dans_sortie` = union ; `calendrier_erreur` = la 1re, préfixée du nom du compte
  s'il y en a plusieurs), plus :
  - `comptes: [{id, nom, sortie, types, actifs, manquants, source_dans_sortie, doublons, incomplet, calendrier_erreur, creneaux}]` (`sortie` = `ranger/<nom>`, ou `ranger` s'il n'y a qu'un compte ; `creneaux` = créneaux à remplir des types actifs) ;
  - `partages: [{dossier, comptes: [{id, nom, type}]}]`.
- `ranger_lancer` range compte par compte. Avec 2 comptes ou plus, chaque texte de progression
  commence par « Compte 2/3 — @marie » (rang parmi les comptes **rangés**), `details.compte =
  {index, total, id, nom}`, et la `fraction` est **globale** (sur les créneaux de tous les comptes).
  L'annulation est respectée dans un compte et entre deux comptes (les suivants ne commencent pas).
  Résultat : totaux d'avant (`creneaux`, `types` = union, `besoins/fournis/places/manques/incomplets/
  surplus/ignores` additionnés) + `comptes: [{id, nom, sortie, types, besoins, fournis, places,
  manques, incomplets, surplus, ignores, creneaux, arrete, aucun_type}]` ; le `bilan.message` a un
  bloc par compte quand il y en a plusieurs.
- `preparer` avec `commande: "ranger_lancer"` accepte les mêmes args (avec ou sans `comptes`) et
  annonce le dossier `ranger` entier.

Déroulé type d'un bouton « Convertir les images » :
1. `preparer` → si `remplacement` est vrai, l'interface demande « Remplacer ? » en montrant `sortie` ;
2. `conversion_images` avec `remplacer: "<sortie>"` (le **moteur** revérifie tout, et ne remplace que ce dossier) ;
3. `progress` / `log` en direct → `result` → popup avec `bilan`.

---

## 4. Le pont de développement (`dev_bridge.py`)

Tant que l'exe du moteur (PyInstaller) n'existe pas, l'interface parle au moteur par ce pont,
**dans le navigateur** (`http://localhost:1420`) comme **dans la fenêtre Tauri** (`npm run tauri:dev`).
Le plus simple : `cd desktop` puis `npm run dev:moteur`, qui lance le pont ET l'interface
(voir `desktop/README.md`). À la main :

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
noms réservés du calendrier, **comptes du Ranger** (migration depuis `calendrier_utilisateur.json`,
persistance, refus qui nomment le compte, noms en double sans tenir compte de la casse, analyse et
rangement à 2-3 comptes dans `ranger/<nom>/…`, 1 compte = arborescence d'avant, `partages`,
`details.compte` des erreurs, annulation pendant le 1er compte), `quitter`, **`quitter` puis EOF
immédiat pendant une conversion**, EOF, Job Windows, signature de `progression.texte`, nouveaux
paramètres (défauts et refus), **compteur d'activité** (comptage après une conversion, `activite_lire`,
purge, fichier illisible, envoi au serveur **simulé** : aucun appel sans licence), et le pont
de dev (jeton, CORS, SSE, données de test). Durée : environ 1 minute.

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
