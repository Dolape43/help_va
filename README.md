# HelpVA

**HelpVA** est une application de bureau (Windows / macOS) qui aide les
assistants virtuels à **préparer** le contenu d'un modèle : convertir les
médias, les rendre uniques et les ranger selon un calendrier.

Interface : Python + CustomTkinter, police Poppins embarquée, thème clair/sombre.

## Les 4 modules

| Module | Rôle | Code |
|---|---|---|
| **Convertir les images** | Convertit en `.jpg` ou `.png` (y compris les photos iPhone HEIC). | [`agent/unicite.py`](agent/unicite.py) |
| **Convertir en MP4** | Transforme `.mov`, `.avi`, … en `.mp4` prêt pour Instagram. | [`agent/conversion.py`](agent/conversion.py) |
| **Changer les métadonnées** | Rend chaque photo/vidéo **unique** (métadonnées, taille, pixels) pour éviter la détection de doublon d'Instagram, sans changement visible. | [`agent/unicite.py`](agent/unicite.py) |
| **Ranger les médias** | Organise images et vidéos par semaine/jour/créneau selon le calendrier. | [`agent/ranger.py`](agent/ranger.py) · [`agent/calendrier.py`](agent/calendrier.py) |

## Prérequis

- **Python 3.11+**
- Dépendances : `pip install -r requirements.txt`

## Lancer en développement

```bash
python app_ctk.py
```

## Licences & activation

HelpVA est protégé par un système de licences signées (Ed25519) et un
back-office **Supabase** :

- l'utilisateur saisit un **code d'activation** ; l'app envoie son empreinte
  machine au serveur, qui renvoie une licence signée ;
- une licence peut être **résiliée / suspendue à distance** depuis le tableau
  de bord web (le serveur est la seule source de vérité) ;
- code côté app : [`agent/licence.py`](agent/licence.py) — fonction serveur :
  [`supabase/functions/admin/index.ts`](supabase/functions/admin/index.ts) —
  tableau de bord : [`web/admin.html`](web/admin.html).

## Construction (exe / .app)

- Windows : voir [`HelpVA.spec`](HelpVA.spec) (PyInstaller).
- macOS : voir [`HelpVA_mac.spec`](HelpVA_mac.spec) et [`BUILD_MAC.md`](BUILD_MAC.md).

## Sécurité

Ne sont **jamais** publiés (voir [`.gitignore`](.gitignore)) : la clé privée
Ed25519 du vendeur (`outils/`, `admin-prive/`), les licences clients, les
médias locaux de test et les journaux.
