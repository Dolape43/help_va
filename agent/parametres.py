"""
Paramètres de l'utilisateur, stockés dans `parametres.json` À CÔTÉ de l'exe.

C'est ici que chaque ami met SA propre clé API AdsPower et choisit son
profil — rien n'est codé en dur, donc l'exe est distribuable tel quel.
"""

import json
import os
import sys

FICHIER = "parametres.json"

_DEFAUT = {
    "api_key": "",     # clé API AdsPower de l'utilisateur
    "profil": "",      # user_id du profil AdsPower sélectionné
    "modele": "",      # nom du modèle en cours (dossier de rangement)
}


def _chemin() -> str:
    # %APPDATA%\HelpVA (stable entre versions, migration auto depuis l'ancien
    # emplacement). Chemin ABSOLU -> marche même lancé depuis System32.
    from . import emplacement
    return emplacement.chemin(FICHIER)


def charger() -> dict:
    """Charge les paramètres (ou des valeurs par défaut si absent/illisible)."""
    chemin = _chemin()
    if os.path.exists(chemin):
        try:
            with open(chemin, encoding="utf-8") as f:
                return {**_DEFAUT, **json.load(f)}
        except Exception:
            pass
    return dict(_DEFAUT)


def sauver(params: dict) -> None:
    """Enregistre les paramètres dans parametres.json (à côté de l'exe)."""
    with open(_chemin(), "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
