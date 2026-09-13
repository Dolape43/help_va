"""
Démarrage automatique de HelpVA avec Windows.

Ajoute (ou retire) une entrée dans le registre :
    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

Quand l'entrée est présente, Windows lance HelpVA à l'ouverture de la
session. Combiné à la "reprise automatique", l'automatisation repart
toute seule après un redémarrage/extinction du PC.
"""

import os
import sys

CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM = "HelpVA"


def _cible() -> str:
    """Commande à lancer au démarrage (exe empaqueté, ou script en dev)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app_ctk.py"))
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{script}"'


def commande() -> str:
    """La commande qui sera lancée au démarrage (pour diagnostic/affichage)."""
    return _cible()


def activer() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUN, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NOM, 0, winreg.REG_SZ, _cible())
        return True
    except Exception:
        return False


def desactiver() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUN, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOM)
        return True
    except FileNotFoundError:
        return True   # déjà absent
    except Exception:
        return False


def est_actif() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUN, 0,
                            winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, NOM)
        return True
    except Exception:
        return False
