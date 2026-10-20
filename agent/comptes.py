"""
Comptes du module Ranger, stockés dans `comptes_ranger.json`
(%APPDATA%\\HelpVA sous Windows).

Chaque compte a SES PROPRES dossiers sources (un par type de post) et SON
calendrier :
    {"version": 1, "comptes": [
      {"id": "c1", "nom": "Compte 1",
       "sources": {"reel": "C:\\...", "story": "C:\\..."},
       "calendrier": null}
    ]}

calendrier = null -> le calendrier d'origine (calendrier.CALENDRIER).
Le nom du compte devient le nom de son dossier de sortie (ranger/<nom>/…)
quand il y a au moins 2 comptes.

La VÉRIFICATION des comptes (noms, chemins, calendriers) est faite par le
moteur (engine/commandes.py) : ici, on lit et on écrit seulement.
"""

import copy
import json
import os
import time

FICHIER = "comptes_ranger.json"
VERSION = 1
MAX_COMPTES = 50


def _chemin() -> str:
    # %APPDATA%\HelpVA, comme parametres.json et calendrier_utilisateur.json.
    from . import emplacement
    return emplacement.chemin(FICHIER)


def compte_initial() -> dict:
    """Le compte de départ, quand comptes_ranger.json n'existe pas encore.

    MIGRATION : le calendrier déjà enregistré (calendrier_utilisateur.json, celui de
    l'ancienne app et des versions sans comptes) devient celui du compte 1. Sinon
    null = le calendrier d'origine."""
    from . import calendrier
    cal = None
    chemin = calendrier._chemin_utilisateur()
    if os.path.exists(chemin):
        try:
            with open(chemin, encoding="utf-8") as f:
                lu = json.load(f)
            if isinstance(lu, dict) and lu:
                cal = lu
        except Exception:
            pass
    return {"id": "c1", "nom": "Compte 1", "sources": {}, "calendrier": cal}


def _propre(compte: dict) -> dict:
    """Un compte lu dans le fichier, avec tous ses champs (fichier modifié à la main…)."""
    sources = compte.get("sources")
    cal = compte.get("calendrier")
    return {"id": str(compte.get("id") or ""), "nom": str(compte.get("nom") or ""),
            "sources": dict(sources) if isinstance(sources, dict) else {},
            "calendrier": copy.deepcopy(cal) if isinstance(cal, dict) and cal else None}


def _mettre_de_cote(chemin: str) -> str:
    """Renomme un fichier illisible en « comptes_ranger.illisible-AAAAMMJJ-HHMMSS.json ».

    Pourquoi ne pas simplement l'ignorer ? On repart alors de « Compte 1 », et le prochain
    enregistrement (qui envoie la liste COMPLÈTE) l'écraserait : tous les comptes seraient
    perdus. Mis de côté, le fichier peut être corrigé à la main puis remis à sa place."""
    base, ext = os.path.splitext(chemin)
    horodatage = time.strftime("%Y%m%d-%H%M%S")
    copie, n = f"{base}.illisible-{horodatage}{ext}", 1
    while os.path.exists(copie):
        n += 1
        copie = f"{base}.illisible-{horodatage}-{n}{ext}"
    os.rename(chemin, copie)        # rename (pas replace) : n'écrase jamais rien
    print(f"⚠️ {FICHIER} était illisible : mis de côté sous « {os.path.basename(copie)} ». "
          "Les comptes repartent de « Compte 1 ».")
    return copie


def charger_comptes() -> list:
    """Les comptes enregistrés. Fichier absent -> un seul compte (voir compte_initial),
    sans rien écrire : le fichier n'est créé qu'au premier enregistrement.

    Fichier illisible (JSON cassé après une modification à la main…) -> mis de côté
    (voir _mettre_de_cote), puis un seul compte. Un fichier qu'on ne peut pas OUVRIR
    (verrouillé…) lève OSError : surtout pas de retour silencieux à « Compte 1 », que le
    prochain enregistrement écrirait par-dessus."""
    chemin = _chemin()
    if not os.path.exists(chemin):
        return [compte_initial()]
    with open(chemin, encoding="utf-8") as f:
        try:
            donnees = json.load(f)
        except ValueError:          # JSON invalide, ou fichier qui n'est pas en UTF-8
            donnees = None
    comptes = donnees.get("comptes") if isinstance(donnees, dict) else None
    lus = []
    if isinstance(comptes, list):
        lus = [_propre(c) for c in comptes if isinstance(c, dict)][:MAX_COMPTES]
        # id absent, en double, ou refusé par le moteur (espaces au bord, plus de 64 caractères) :
        # l'interface s'en sert pour reconnaître chaque compte et le renvoie tel quel à chaque
        # enregistrement (un id refusé bloquerait alors toutes les modifications).
        vus = set()
        for c in lus:
            cid = c["id"]
            if not cid or cid.strip() != cid or len(cid) > 64 or cid in vus:
                n = 1
                while f"c{n}" in vus or any(a["id"] == f"c{n}" for a in lus):
                    n += 1
                c["id"] = f"c{n}"
            vus.add(c["id"])
    if lus:
        return lus
    _mettre_de_cote(chemin)         # fichier fermé (fin du « with ») : Windows peut le renommer
    return [compte_initial()]


def sauver_comptes(comptes: list) -> None:
    """Enregistre les comptes, SANS jamais laisser un fichier à moitié écrit.

    On écrit dans un fichier .tmp, puis os.replace() l'échange d'un coup : une
    lecture voit l'ancien OU le nouveau fichier, jamais un mélange (sinon un JSON
    tronqué -> retour à « Compte 1 » seul, et tous les comptes seraient perdus)."""
    chemin = _chemin()
    tmp = f"{chemin}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": VERSION, "comptes": comptes}, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        for essai in range(10):
            try:
                os.replace(tmp, chemin)
                break
            except PermissionError:
                # Windows : le fichier est lu au même instant (antivirus…) -> on réessaie.
                if essai == 9:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
