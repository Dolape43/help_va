"""
Calendrier de publication.

Chaque semaine -> chaque jour -> liste de créneaux.
Un créneau = {"heure": "12h15",
              "type": "reel" | "story" | "story_cta" | "carousel"}.

Pour modifier le planning, tu édites simplement ce fichier.
Les heures sont au format "HHhMM".
"""

import json
import os
import sys
import copy

# Fichier où sont enregistrés les ajustements faits depuis l'interface.
# S'il existe, il remplace le calendrier par défaut ci-dessous.
FICHIER_UTILISATEUR = "calendrier_utilisateur.json"


def _chemin_utilisateur() -> str:
    """Chemin du calendrier utilisateur dans %APPDATA%\\HelpVA.

    Stockage STABLE : le calendrier enregistré survit aux mises à jour /
    rebuilds / changements de licence (migration auto depuis l'ancien
    emplacement à côté de l'exe)."""
    from . import emplacement
    return emplacement.chemin(FICHIER_UTILISATEUR)


def charger_calendrier() -> dict:
    """Retourne le calendrier à utiliser (ajusté par l'utilisateur si présent)."""
    chemin = _chemin_utilisateur()
    if os.path.exists(chemin):
        try:
            with open(chemin, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return copy.deepcopy(CALENDRIER)


def sauver_calendrier(cal: dict) -> None:
    """Enregistre les ajustements du calendrier."""
    with open(_chemin_utilisateur(), "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2, ensure_ascii=False)


CALENDRIER = {
    # --- SEMAINE 1 : démarrage doux ---
    "semaine-01": {
        "jour-1": [
            {"heure": "12h15", "type": "carousel"},
            {"heure": "21h00", "type": "story"},
        ],
        "jour-2": [
            {"heure": "11h45", "type": "carousel"},
            {"heure": "20h30", "type": "story"},
        ],
        "jour-3": [
            {"heure": "12h00", "type": "carousel"},
            {"heure": "21h30", "type": "story"},
        ],
        "jour-4": [
            {"heure": "19h10", "type": "reel"},
            {"heure": "21h00", "type": "story"},
        ],
        "jour-5": [
            {"heure": "18h45", "type": "reel"},
            {"heure": "20h45", "type": "story"},
        ],
        "jour-6": [
            {"heure": "12h00", "type": "carousel"},
            {"heure": "19h20", "type": "reel"},
            {"heure": "21h15", "type": "story"},
        ],
        "jour-7": [
            {"heure": "19h05", "type": "reel"},
            {"heure": "21h00", "type": "story"},
        ],
    },

    # --- SEMAINE 2 : montée en charge ---
    "semaine-02": {
        "jour-1": [  # Lundi
            {"heure": "10h10", "type": "reel"},
            {"heure": "11h00", "type": "story"},
            {"heure": "12h30", "type": "carousel"},
            {"heure": "19h15", "type": "reel"},
            {"heure": "21h00", "type": "story"},
        ],
        "jour-2": [  # Mardi
            {"heure": "10h00", "type": "reel"},
            {"heure": "11h15", "type": "story"},
            {"heure": "19h00", "type": "reel"},
            {"heure": "20h45", "type": "story"},
        ],
        "jour-3": [  # Mercredi
            {"heure": "10h20", "type": "reel"},
            {"heure": "11h00", "type": "story"},
            {"heure": "12h00", "type": "carousel"},
            {"heure": "19h30", "type": "reel"},
            {"heure": "21h15", "type": "story"},
        ],
        "jour-4": [  # Jeudi
            {"heure": "10h05", "type": "reel"},
            {"heure": "11h30", "type": "story"},
            {"heure": "19h00", "type": "reel"},
            {"heure": "21h00", "type": "story"},
        ],
        "jour-5": [  # Vendredi
            {"heure": "10h15", "type": "reel"},
            {"heure": "11h00", "type": "story"},
            {"heure": "12h20", "type": "carousel"},
            {"heure": "19h10", "type": "reel"},
            {"heure": "20h30", "type": "story"},
        ],
        "jour-6": [  # Samedi
            {"heure": "10h00", "type": "reel"},
            {"heure": "11h20", "type": "story"},
            {"heure": "19h20", "type": "reel"},
            {"heure": "21h00", "type": "story"},
        ],
        "jour-7": [  # Dimanche
            {"heure": "10h30", "type": "reel"},
            {"heure": "11h00", "type": "story"},
            {"heure": "19h00", "type": "reel"},
            {"heure": "21h30", "type": "story"},
        ],
    },

    # --- SEMAINE 3 et + : régime croisière ---
    "semaine-03": {
        "jour-1": [  # Lundi
            {"heure": "09h05", "type": "reel"},
            {"heure": "10h00", "type": "story"},
            {"heure": "12h20", "type": "reel"},
            {"heure": "15h00", "type": "story"},
            {"heure": "19h00", "type": "carousel"},
            {"heure": "21h30", "type": "story"},
        ],
        "jour-2": [  # Mardi
            {"heure": "09h30", "type": "reel"},
            {"heure": "10h00", "type": "story"},
            {"heure": "14h00", "type": "story"},
            {"heure": "19h15", "type": "reel"},
            {"heure": "21h00", "type": "story"},
        ],
        "jour-3": [  # Mercredi
            {"heure": "09h10", "type": "reel"},
            {"heure": "10h00", "type": "story"},
            {"heure": "12h00", "type": "reel"},
            {"heure": "15h30", "type": "story"},
            {"heure": "19h25", "type": "reel"},
            {"heure": "22h00", "type": "story"},
        ],
        "jour-4": [  # Jeudi
            {"heure": "09h45", "type": "reel"},
            {"heure": "11h00", "type": "story"},
            {"heure": "12h10", "type": "carousel"},
            {"heure": "16h00", "type": "story"},
            {"heure": "19h00", "type": "reel"},
            {"heure": "21h15", "type": "story"},
        ],
        "jour-5": [  # Vendredi
            {"heure": "09h00", "type": "reel"},
            {"heure": "10h00", "type": "story"},
            {"heure": "12h30", "type": "reel"},
            {"heure": "13h00", "type": "story"},
            {"heure": "17h00", "type": "story"},
            {"heure": "19h40", "type": "reel"},
            {"heure": "22h00", "type": "story"},
        ],
        "jour-6": [  # Samedi
            {"heure": "09h20", "type": "reel"},
            {"heure": "10h30", "type": "story"},
            {"heure": "12h00", "type": "carousel"},
            {"heure": "15h00", "type": "story"},
            {"heure": "19h30", "type": "reel"},
            {"heure": "21h45", "type": "story"},
        ],
        "jour-7": [  # Dimanche
            {"heure": "09h15", "type": "reel"},
            {"heure": "11h00", "type": "story"},
            {"heure": "14h30", "type": "story"},
            {"heure": "19h10", "type": "reel"},
            {"heure": "21h00", "type": "story"},
        ],
    },
}
