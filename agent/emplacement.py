"""
Emplacement STABLE des données utilisateur (licence, paramètres).

Avant : les fichiers étaient à côté de l'exe -> une mise à jour placée dans un
autre dossier « perdait » la licence et les réglages.

Maintenant : tout est dans %APPDATA%\HelpVA (dossier propre à l'utilisateur,
qui NE bouge PAS entre les versions). Une migration automatique récupère les
anciens fichiers laissés à côté de l'exe.
"""

import os
import sys
import shutil

NOM_APP = "HelpVA"


def dossier_donnees() -> str:
    """Dossier stable des données, à l'emplacement standard de chaque OS :
      - Windows : %APPDATA%\\HelpVA
      - macOS   : ~/Library/Application Support/HelpVA
      - Linux   : $XDG_DATA_HOME/HelpVA (ou ~/.local/share/HelpVA)
    Ce dossier NE bouge PAS entre les versions.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    d = os.path.join(base, NOM_APP)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def dossier_exe() -> str:
    """Ancien emplacement (à côté de l'exe, ou racine du projet en dev).

    Sert uniquement à la MIGRATION des anciens fichiers.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def chemin(nom_fichier: str) -> str:
    """Chemin d'un fichier de données dans %APPDATA%\\HelpVA.

    MIGRATION : si le fichier n'existe pas encore là mais existe à l'ancien
    emplacement (à côté de l'exe), on le COPIE (l'ancien exe continue de
    fonctionner pendant la transition).
    """
    cible = os.path.join(dossier_donnees(), nom_fichier)
    if not os.path.exists(cible):
        ancien = os.path.join(dossier_exe(), nom_fichier)
        if os.path.exists(ancien):
            try:
                shutil.copy2(ancien, cible)
            except Exception:
                pass
    return cible


def chemin_ancien(nom_fichier: str) -> str:
    """Chemin d'un fichier à l'ANCIEN emplacement (à côté de l'exe)."""
    return os.path.join(dossier_exe(), nom_fichier)
