# HelpVA

**HelpVA** est une application de bureau (Windows / macOS) pour les
assistants virtuels (VA) qui gèrent le contenu Instagram de modèles. Elle
**prépare** les médias : les convertir au bon format, les rendre uniques et
les ranger selon un calendrier de posts.

Vendue aux agences de VA sous forme de licence (activation par code).

- Interface : Python + CustomTkinter, police Poppins embarquée
- Thème clair / sombre (bouton en bas de la barre latérale)
- Version : voir [`agent/version.py`](agent/version.py)

---

## Les 4 modules

### 1. Convertir les images — [`agent/unicite.py`](agent/unicite.py)
Convertit un dossier ou une sélection d'images en **.jpg** (plus léger,
recommandé pour Instagram) ou en **.png** (sans perte, garde la transparence).
Les photos iPhone **HEIC / HEIF**, qui ne s'affichent pas sur Instagram,
deviennent lisibles. Traitement en parallèle.

Sortie : `images (jpg)` ou `images (png)`.

### 2. Convertir en MP4 — [`agent/conversion.py`](agent/conversion.py)
Transforme `.mov`, `.avi`, `.mkv`… en `.mp4` compatible partout :
1. **remux** instantané (`-c copy`) quand c'est possible ;
2. sinon **ré-encodage** H.264 / AAC (y compris les vidéos iPhone HEVC,
   refusées par Instagram et Windows).

Sortie : `media (mp4)`.

### 3. Changer les métadonnées — [`agent/unicite.py`](agent/unicite.py)
Rend chaque photo / vidéo **unique** pour éviter la détection de doublon
quand le même média est posté sur plusieurs comptes, **sans changement
visible** :

| Images | Vidéos |
|---|---|
| Réduction à la taille Instagram (max 1080 × 1920) | Suppression de toutes les métadonnées |
| Recadrage de quelques pixels | Micro-variation de luminosité / contraste |
| Micro-variations de couleurs (± 3 %) + léger bruit | Ré-encodage H.264 (qualité aléatoire, preset `ultrafast`) |
| Nouvel encodage JPEG (qualité aléatoire), EXIF supprimé | |
| HEIC converti en .jpg, PNG transparent posé sur fond blanc | |

- Accepte un dossier (avec **ses sous-dossiers** : l'arborescence est
  reproduite) ou des fichiers précis.
- Images traitées **en parallèle** (~0,1 s par image), progression en direct,
  annulable.
- Chaque passage produit un résultat différent : on peut relancer pour
  obtenir une nouvelle version unique.
- Sortie : `<nom du dossier> (métadonnées changées)`.

Document de démonstration : `HelpVA - Preuve unicite images.pdf`.

### 4. Ranger les médias — [`agent/ranger.py`](agent/ranger.py) · [`agent/calendrier.py`](agent/calendrier.py)
Range les médias dans un dossier par **semaine / jour / créneau**, selon le
calendrier de posts. La page se fait en **3 étapes** :

1. **Régler le calendrier** : jusqu'à 4 semaines, créneaux horaires éditables,
   puis choix des types de posts à ranger.
2. **Choisir les dossiers** : un onglet et **un dossier source par type** :

   | Type | Médias acceptés | Par créneau |
   |---|---|---|
   | Réels | vidéos uniquement | 1 |
   | Stories | images uniquement | 1 |
   | Stories CTA | images uniquement | 1 |
   | Carrousels | images nommées 1, 2, 3… | 3, **dans l'ordre** |

   Chaque onglet indique le nombre de fichiers trouvés par rapport au nombre
   requis.
3. **Lancer** : un seul rangement pour tous les types (copie, les originaux ne
   sont pas touchés). Réels et stories peuvent être répartis au hasard ; les
   carrousels gardent toujours l'ordre numérique.

Résultat (dossier `ranger`) :

```
ranger/
├── semaine-01/
│   └── jour-1/
│       ├── legendes.txt              ← notes / légendes du jour (vide)
│       ├── 1_10h00_reel/             ← vidéo + legende.txt
│       ├── 2_11h00_story/            ← image
│       ├── 3_12h00_story-cta/        ← image
│       └── 4_19h00_carousel/         ← 3 images + legende.txt
└── surplus/                          ← médias en trop, classés par type
```

Le calendrier par défaut est défini dans `agent/calendrier.py` ; les
modifications faites dans l'app sont enregistrées dans
`calendrier_utilisateur.json`.

---

## Dossier de sortie & données

- **Dossier de sortie** : `Bureau\HelpVA` par défaut, modifiable dans
  **Paramètres** (ex. un autre disque). Un raccourci sur l'accueil permet de
  l'ouvrir.
- **Données de l'utilisateur** (stables entre les mises à jour) :
  - Windows : `%APPDATA%\HelpVA`
  - macOS : `~/Library/Application Support/HelpVA`

  On y trouve `parametres.json` (thème, dossier de sortie, types rangés),
  `calendrier_utilisateur.json` et la licence. Voir
  [`agent/emplacement.py`](agent/emplacement.py).

---

## Licences & activation

Licences **signées (Ed25519)** + back-office **Supabase** :

- le client saisit un **code d'activation** ; l'app envoie l'empreinte de la
  machine, le serveur renvoie une licence signée **liée à ce PC / Mac** ;
- types : **à vie**, **mensuel**, **annuel**, **essai** ;
- l'app revérifie l'abonnement **toutes les heures** : une licence résiliée ou
  expirée est bloquée automatiquement ;
- **hors connexion** : l'app continue de fonctionner pendant **3 jours**
  (bandeau discret « Hors-ligne »), puis demande une connexion.

Fichiers :
- app : [`agent/licence.py`](agent/licence.py)
- fonction serveur : [`supabase/functions/admin/index.ts`](supabase/functions/admin/index.ts)
- tableau de bord vendeur (création de codes, suivi et résiliation des
  licences) : [`web/admin.html`](web/admin.html)

---

## Structure du projet

```
app_ctk.py              Interface (pages, navigation, popups)
agent/
├── unicite.py          Métadonnées + conversion d'images
├── conversion.py       Conversion vidéo en MP4 (ffmpeg)
├── ranger.py           Rangement par type de post
├── calendrier.py       Calendrier par défaut + sauvegarde
├── licence.py          Licences, vérification en ligne, tolérance hors-ligne
├── horloge.py          Date réelle via internet (anti-triche sur la date)
├── parametres.py       Préférences de l'utilisateur
├── emplacement.py      Dossier des données (AppData / Application Support)
├── polices.py          Chargement de la police Poppins
├── config.py           Réglages (carrousels, Supabase…)
├── drive.py            Ancien module Google Drive (masqué dans l'interface)
└── version.py
assets/                 Logo, icônes, polices, images du tutoriel
web/admin.html          Tableau de bord vendeur
supabase/functions/     Fonction serveur des licences
HelpVA.spec             Build Windows (PyInstaller)
HelpVA_mac.spec         Build macOS
BUILD_MAC.md            Guide de build sur Mac
```

---

## Développement

Prérequis : **Python 3.11+**

```bash
pip install -r requirements.txt
python app_ctk.py
```

## Construction (exe / .app)

- **Windows** : `pyinstaller --noconfirm --clean HelpVA.spec` → `dist/HelpVA.exe`
- **macOS** (à faire sur un Mac) : voir [`BUILD_MAC.md`](BUILD_MAC.md)

## Sécurité

Ne sont **jamais** publiés (voir [`.gitignore`](.gitignore)) : la clé privée
Ed25519 du vendeur (`outils/`, `admin-prive/`), les licences clients, les
paramètres et calendriers locaux, les médias de test et les journaux.
Les clés embarquées dans l'app (clé publique Ed25519, clé « anon » Supabase)
sont publiques par nature.
