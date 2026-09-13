# Agent Insta

Agent qui publie automatiquement sur Instagram (publications, carrousels, réels)
en pilotant les profils **AdsPower** via son API locale, puis en automatisant
l'interface web d'Instagram avec **Playwright**.

## Principe

```
Ton script (Python)
  1. démarre le profil AdsPower via l'API locale
  2. Playwright se branche sur le navigateur ouvert (session Insta déjà connectée)
  3. clique "Créer" -> upload média -> légende -> publie
```

On ne touche jamais aux mots de passe : chaque profil AdsPower reste connecté
manuellement à Instagram, et l'agent réutilise la session.

## Prérequis

- **AdsPower** installé, avec l'**API locale** activée (plan payant requis).
- Au moins **1 profil** créé, connecté manuellement à Instagram.
- **Python 3.11+** et les dépendances : `pip install -r requirements.txt`

## Configuration

Tout se règle dans [`agent/config.py`](agent/config.py) :
- `ADSPOWER_API_KEY` : la clé générée dans AdsPower.
- délais "humains", dossier des contenus, etc.

## Commandes

```bash
# Lister les profils AdsPower (retrouver les user_id)
python -m agent.main list

# Vérifier qu'un profil est bien connecté à Instagram
python -m agent.main check <user_id>

# Publier une photo
python -m agent.main post <user_id> publication image.jpg --legende "Ma légende"

# Publier un carrousel (slides)
python -m agent.main post <user_id> carrousel img1.jpg img2.jpg --legende "Slides"

# Publier un réel
python -m agent.main post <user_id> reel video.mp4 --legende "Mon reel"
```

## Ranger les médias selon le calendrier

Tu déposes tes médias bruts dans :
- `sources/videos/` -> serviront aux **Reels**
- `sources/images/` -> l'agent y pioche pour les **Carousels** (plusieurs images) et **Stories** (1 image)

Puis :

```bash
# Voir la répartition sans rien écrire
python -m agent.main ranger --simuler

# Ranger réellement dans planning/
python -m agent.main ranger
```

Résultat : `planning/semaine-XX/jour-Y/<ordre>_<heure>_<type>/` contenant les médias
du créneau + un `legende.txt` à remplir. Le planning est défini dans
[`agent/calendrier.py`](agent/calendrier.py) ; les réglages (images par carousel,
copier/déplacer) dans [`agent/config.py`](agent/config.py).

## Limites connues

- L'API locale AdsPower est limitée à ~1 requête/seconde (géré automatiquement).
- Les sélecteurs de l'interface Instagram peuvent changer : voir
  [`agent/instagram.py`](agent/instagram.py) si un clic ne fonctionne plus.
- Le PC doit être allumé au moment de la publication.
```
