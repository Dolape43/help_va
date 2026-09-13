"""
Pilotage d'AdsPower via son API locale.

Rôle de ce module : démarrer un profil, récupérer le point de
connexion du navigateur (pour que Playwright s'y branche), puis
arrêter le profil quand on a fini.

On ne fait AUCUNE action Instagram ici : ce module ne s'occupe
que d'ouvrir/fermer le bon navigateur.

Authentification : la clé API s'envoie dans le header
    Authorization: Bearer <cle>
"""

import os
import glob
import time
import subprocess
import requests
from .config import ADSPOWER_API, DELAI_ENTRE_APPELS_API
from . import parametres


# ======================================================================
#  Ouverture automatique d'AdsPower (pour l'automatisation au démarrage)
# ======================================================================

def api_joignable(timeout: int = 3) -> bool:
    """Vrai si l'API locale d'AdsPower répond (donc AdsPower est ouvert)."""
    try:
        r = requests.get(f"{ADSPOWER_API}/status", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _detecter_adspower() -> str | None:
    """Cherche AdsPower*.exe dans les emplacements d'installation habituels."""
    bases = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("PROGRAMFILES", ""),
             os.environ.get("PROGRAMFILES(X86)", "")]
    motifs = []
    for base in bases:
        if not base:
            continue
        motifs += [
            os.path.join(base, "Programs", "*", "AdsPower*.exe"),
            os.path.join(base, "*", "AdsPower*.exe"),
            os.path.join(base, "AdsPower*", "AdsPower*.exe"),
        ]
    for motif in motifs:
        for chemin in glob.glob(motif):
            if os.path.isfile(chemin):
                return chemin
    return None


def chemin_adspower() -> str | None:
    """Chemin de l'exe AdsPower : celui enregistré (parametres) sinon détecté."""
    enregistre = parametres.charger().get("adspower_exe")
    if enregistre and os.path.isfile(enregistre):
        return enregistre
    return _detecter_adspower()


def lancer_adspower(chemin: str | None = None) -> bool:
    """Lance l'application AdsPower (sans attendre). Retourne True si lancé."""
    chemin = chemin or chemin_adspower()
    if not chemin or not os.path.isfile(chemin):
        return False
    try:
        subprocess.Popen([chemin], close_fds=True)
        return True
    except Exception:
        return False


def assurer_adspower(timeout: int = 120) -> bool:
    """Garantit qu'AdsPower est ouvert et que son API répond.

    Si l'API répond déjà -> True. Sinon on lance AdsPower et on attend
    (jusqu'à `timeout` s) que l'API devienne joignable.
    """
    if api_joignable():
        return True
    if not lancer_adspower():
        return False
    fin = time.time() + timeout
    while time.time() < fin:
        if api_joignable():
            return True
        time.sleep(3)
    return False


def _appel_api(chemin: str, params: dict | None = None) -> dict:
    """Fait un appel GET à l'API AdsPower avec la clé, et gère la réponse.

    On respecte une petite pause avant chaque appel car l'API locale
    n'accepte qu'environ 1 requête par seconde.
    """
    time.sleep(DELAI_ENTRE_APPELS_API)

    url = f"{ADSPOWER_API}{chemin}"
    headers = {"Authorization": f"Bearer {parametres.cle_api()}"}
    reponse = requests.get(url, params=params or {}, headers=headers, timeout=30)
    data = reponse.json()

    if data.get("code") != 0:
        raise RuntimeError(f"AdsPower a répondu une erreur : {data.get('msg')}")

    return data["data"]


def lister_profils() -> list:
    """Retourne la liste des profils AdsPower (nom + user_id, etc.)."""
    data = _appel_api("/api/v1/user/list", {"page": 1, "page_size": 100})
    return data["list"]


def demarrer_profil(user_id: str) -> tuple[str, str]:
    """Démarre un profil et renvoie de quoi s'y brancher avec Selenium.

    Retourne un couple :
      - debugger_address : "127.0.0.1:<port>" (le navigateur ouvert)
      - driver_path      : chemin du chromedriver fourni par AdsPower,
                           exactement adapté à sa version de Chrome.

    On utilise Selenium (et non Playwright) car le Chrome d'AdsPower est
    trop récent pour Playwright, qui bloque à la connexion.
    """
    # headless=0 : le navigateur s'ouvre visiblement (pratique pour déboguer).
    data = _appel_api("/api/v1/browser/start", {"user_id": user_id, "headless": 0})
    debugger_address = data["ws"]["selenium"]   # ex: "127.0.0.1:62899"
    driver_path = data["webdriver"]             # chromedriver.exe adapté
    return debugger_address, driver_path


def arreter_profil(user_id: str) -> None:
    """Ferme le navigateur du profil."""
    _appel_api("/api/v1/browser/stop", {"user_id": user_id})
