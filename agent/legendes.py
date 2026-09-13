"""
Gestion des captions et légendes (par genre + type de contenu).

Vocabulaire :
  - CAPTION = le texte "accroche" à mettre SUR la vidéo/image (overlay).
  - LÉGENDE = le texte de la publication (sous le post).

Les banques sont dans le dossier `legendes/` :
    feminin_reel.json      masculin_reel.json
    feminin_carousel.json  masculin_carousel.json
Chaque fichier = liste de { "caption": "...", "legende": "..." }.

Un bouton dans l'app remplit, pour chaque créneau reel/carousel du dossier
du modèle, un fichier caption.txt + legende.txt (avec hashtags optionnels).
Les stories ne sont PAS concernées.
"""

import os
import sys
import json
import random


def _dossier_legendes() -> str:
    """Dossier des banques de légendes.

    Compatible PyInstaller : dans l'exe, les fichiers sont embarqués et
    accessibles via sys._MEIPASS ; en développement, c'est ./legendes.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, "legendes")
        if os.path.isdir(p):
            return p
    return "legendes"


DOSSIER = _dossier_legendes()
TYPES = ("reel", "carousel")


def _chemin(genre: str, type_contenu: str) -> str:
    return os.path.join(DOSSIER, f"{genre}_{type_contenu}.json")


def charger(genre: str, type_contenu: str) -> list:
    """Charge la banque de légendes d'un genre + type (liste de paires)."""
    p = _chemin(genre, type_contenu)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _hashtags(n: int = 6) -> str:
    """Renvoie n hashtags aléatoires depuis legendes/hashtags.txt."""
    p = os.path.join(DOSSIER, "hashtags.txt")
    if not os.path.exists(p):
        return ""
    tags = [t.strip() for t in open(p, encoding="utf-8") if t.strip().startswith("#")]
    if not tags:
        return ""
    return " ".join(random.sample(tags, min(n, len(tags))))


def generer_pour_dossier(dossier_ranger: str, genre: str,
                         avec_hashtags: bool = True) -> int:
    """Remplit caption.txt + legende.txt pour chaque créneau reel/carousel.

    Retourne le nombre de créneaux remplis. Les stories sont ignorées.
    """
    banques = {t: charger(genre, t) for t in TYPES}
    if not any(banques.values()):
        raise RuntimeError(
            f"Aucune légende pour le genre « {genre} ». Vérifie le dossier « {DOSSIER} ».")

    derniers = {t: None for t in TYPES}   # évite de répéter la même d'affilée
    n = 0
    for racine, _, _ in os.walk(dossier_ranger):
        nom = os.path.basename(racine)
        for typ in TYPES:
            if not nom.endswith("_" + typ):
                continue
            bank = banques[typ]
            if not bank:
                continue
            choix = random.choice(bank)
            if len(bank) > 1:
                while choix is derniers[typ]:
                    choix = random.choice(bank)
            derniers[typ] = choix

            legende = choix.get("legende", "")
            if avec_hashtags:
                tags = _hashtags()
                if tags:
                    legende = (legende + "\n\n" + tags).strip()

            # On ne génère QUE la légende (les captions sont déjà sur les vidéos).
            with open(os.path.join(racine, "legende.txt"), "w", encoding="utf-8") as f:
                f.write(legende)
            n += 1
    return n
