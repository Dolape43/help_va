"""
Paramètres de l'utilisateur, stockés dans `parametres.json`
(%APPDATA%\\HelpVA sous Windows).

Contient uniquement les préférences de l'interface (thème, dossier de sortie…).
"""

import json
import os

FICHIER = "parametres.json"

_DEFAUT = {
    "theme": "light",        # "light" | "dark"
    "dossier_sortie": "",    # vide = dossier par défaut (Bureau\HelpVA)
}

# Clés héritées des anciennes versions (automatisation, AdsPower, modèles) :
# supprimées au chargement pour ne plus rien garder de ces données.
_OBSOLETES = ("api_key", "profil", "modele", "genre", "modeles", "auto_actif",
              "auto_comptes", "auto_rattrapage", "methode_pub")


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
                lus = json.load(f)
            params = {**_DEFAUT, **lus}
            if any(k in params for k in _OBSOLETES):
                for k in _OBSOLETES:
                    params.pop(k, None)
                try:
                    sauver(params)
                except OSError:
                    pass
            return params
        except Exception:
            pass
    return dict(_DEFAUT)


def sauver(params: dict) -> None:
    """Enregistre les paramètres dans parametres.json."""
    with open(_chemin(), "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
