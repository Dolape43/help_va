"""
Compteur d'activité : combien de médias ce PC a traités, jour par jour.

Fichier `activite.json` (%APPDATA%\\HelpVA sous Windows) :
    {"version": 1,
     "jours":  {"2026-10-22": {"images": 12, "videos": 3, "metadonnees": 40, "ranges": 87}},
     "envoye": {"2026-10-22": {...mêmes clés...}},
     "anciens": {"images": 0, "videos": 0, "metadonnees": 0, "ranges": 0, "depuis": null}}

  - images      = images converties (module Images) ;
  - videos      = vidéos converties en MP4 ;
  - metadonnees = médias passés dans Métadonnées ;
  - ranges      = médias copiés par le Ranger.
  - envoye  = dernières valeurs CONFIRMÉES par le serveur des licences, par jour : on ne
              renvoie que les jours qui ont changé depuis.
  - anciens = les totaux des jours purgés (on garde ~400 jours au plus) : le « total depuis
              le début » reste juste même après la purge.

Deux usages :
  1. le VA voit son activité sur son PC (resume()) ;
  2. les compteurs partent au serveur des licences (envoyer()) pour que l'agence voie
     l'activité de chaque VA dans la console d'admin. Sans licence enregistrée : rien
     ne part.

Règle d'or : ce compteur ne doit JAMAIS faire échouer un traitement. Toute erreur est
avalée (au pire un print dans le journal).
"""

import json
import os
import threading
import time
from datetime import date, timedelta

FICHIER = "activite.json"
CATEGORIES = ("images", "videos", "metadonnees", "ranges")
JOURS_GARDES = 400          # au-delà : purgés (leurs totaux vont dans « anciens »)
JOURS_ENVOYES = 30          # on ne renvoie jamais plus de 30 jours au serveur
DELAI_RESEAU_S = 8          # timeout court : l'envoi se fait en arrière-plan

# Lire -> modifier -> écrire activite.json : un ajout (fin de traitement) et la mise à
# jour de « envoye » (fin d'un envoi) ne doivent pas s'écraser.
_VERROU = threading.Lock()
# Jamais deux envois en même temps. Si on en demande un pendant un envoi, on le note
# (_relancer) : l'envoi en cours refait un tour à la fin, rien n'est oublié.
_VERROU_ENVOI = threading.Lock()
_relancer = False


# ----------------------------------------------------------- fichier

def _chemin() -> str:
    from . import emplacement
    return emplacement.chemin(FICHIER)


def _vide() -> dict:
    return {"version": 1, "jours": {}, "envoye": {},
            "anciens": {**{c: 0 for c in CATEGORIES}, "depuis": None}}


def _entier(v) -> int:
    """Compteur propre : entier >= 0 (un fichier modifié à la main ne fait rien planter)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    try:
        return max(0, int(v))
    except (ValueError, OverflowError):
        return 0


def _jour_valide(j) -> bool:
    try:
        date.fromisoformat(j)
        return isinstance(j, str) and len(j) == 10
    except (TypeError, ValueError):
        return False


def _compteurs(d) -> dict:
    d = d if isinstance(d, dict) else {}
    return {c: _entier(d.get(c)) for c in CATEGORIES}


def _nettoyer(brut) -> dict:
    """Données lues -> structure propre. Lève ValueError si ce n'est pas notre format."""
    if not isinstance(brut, dict) or not isinstance(brut.get("jours", {}), dict):
        raise ValueError("format inattendu")
    propre = _vide()
    for cle in ("jours", "envoye"):
        bloc = brut.get(cle) or {}
        if not isinstance(bloc, dict):
            bloc = {}
        propre[cle] = {j: _compteurs(v) for j, v in bloc.items() if _jour_valide(j)}
    anciens = brut.get("anciens")
    if isinstance(anciens, dict):
        propre["anciens"].update(_compteurs(anciens))
        if _jour_valide(anciens.get("depuis")):
            propre["anciens"]["depuis"] = anciens["depuis"]
    return propre


def _mettre_de_cote(chemin: str) -> None:
    """Fichier illisible : on le GARDE à côté (activite.illisible-<horodatage>.json)."""
    horodatage = time.strftime("%Y%m%d-%H%M%S")
    dossier = os.path.dirname(chemin)
    cible, n = os.path.join(dossier, f"activite.illisible-{horodatage}.json"), 1
    while os.path.exists(cible):
        n += 1
        cible = os.path.join(dossier, f"activite.illisible-{horodatage}-{n}.json")
    try:
        os.replace(chemin, cible)
        print(f"⚠️ Compteur d'activité illisible, mis de côté : {cible}")
    except OSError:
        pass


def _charger() -> dict:
    """À appeler EN TENANT _VERROU."""
    chemin = _chemin()
    if not os.path.exists(chemin):
        return _vide()
    try:
        with open(chemin, encoding="utf-8") as f:
            return _nettoyer(json.load(f))
    except Exception:
        _mettre_de_cote(chemin)
        return _vide()


def _sauver(donnees: dict) -> None:
    """Écrit d'un coup (.tmp puis os.replace) : jamais de fichier à moitié écrit.
    À appeler EN TENANT _VERROU."""
    chemin = _chemin()
    tmp = f"{chemin}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        for essai in range(10):
            try:
                os.replace(tmp, chemin)
                break
            except PermissionError:
                # Windows : fichier lu au même instant (antivirus…) -> on réessaie.
                if essai == 9:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _purger(donnees: dict, aujourd_hui: date) -> None:
    """Garde les JOURS_GARDES derniers jours ; les plus anciens vont dans « anciens »."""
    limite = (aujourd_hui - timedelta(days=JOURS_GARDES - 1)).isoformat()
    anciens = donnees["anciens"]
    for j in sorted(donnees["jours"]):
        if j >= limite:
            break
        for c in CATEGORIES:
            anciens[c] += donnees["jours"][j][c]
        if anciens["depuis"] is None or j < anciens["depuis"]:
            anciens["depuis"] = j
        del donnees["jours"][j]
    for j in [j for j in donnees["envoye"] if j < limite]:
        del donnees["envoye"][j]


# ----------------------------------------------------------- comptage

def ajouter(categorie: str, n) -> None:
    """+n médias traités aujourd'hui (date LOCALE du PC). n <= 0 : ignoré.

    Ne lève JAMAIS d'exception : un compteur cassé ne doit pas faire échouer un
    traitement qui, lui, a réussi."""
    try:
        n = _entier(n)
        if n <= 0 or categorie not in CATEGORIES:
            return
        aujourd_hui = date.today()
        with _VERROU:
            donnees = _charger()
            jour = donnees["jours"].setdefault(aujourd_hui.isoformat(), _compteurs({}))
            jour[categorie] += n
            _purger(donnees, aujourd_hui)
            _sauver(donnees)
    except Exception as e:
        print(f"⚠️ Compteur d'activité non mis à jour : {e}")


def _somme(jours: dict, depuis: str = None) -> dict:
    out = {c: 0 for c in CATEGORIES}
    for j, v in jours.items():
        if depuis is None or j >= depuis:
            for c in CATEGORIES:
                out[c] += v[c]
    out["total"] = sum(out[c] for c in CATEGORIES)
    return out


def resume() -> dict:
    """Ce que le VA voit sur l'Accueil :
    {aujourd_hui, semaine (7 derniers jours, aujourd'hui compris), mois (30 derniers jours),
     total, depuis ("AAAA-MM-JJ" du 1er jour compté, ou None)}.
    Chaque bloc = {images, videos, metadonnees, ranges, total}."""
    aujourd_hui = date.today()
    try:
        with _VERROU:
            donnees = _charger()
    except Exception:
        donnees = _vide()
    jours = donnees["jours"]
    total = _somme(jours)
    for c in CATEGORIES:
        total[c] += donnees["anciens"][c]
    total["total"] = sum(total[c] for c in CATEGORIES)
    # « depuis » = le 1er jour où quelque chose a VRAIMENT été compté.
    actifs = [j for j, v in jours.items() if any(v.values())]
    if donnees["anciens"]["depuis"]:
        actifs.append(donnees["anciens"]["depuis"])
    return {"aujourd_hui": _somme(jours, aujourd_hui.isoformat()),
            "semaine": _somme(jours, (aujourd_hui - timedelta(days=6)).isoformat()),
            "mois": _somme(jours, (aujourd_hui - timedelta(days=29)).isoformat()),
            "total": total,
            "depuis": min(actifs) if actifs else None}


# ----------------------------------------------------------- envoi au serveur

def _licence_enregistree():
    """Le texte de la licence enregistrée sur ce PC, ou None (pas de licence = rien n'est envoyé)."""
    try:
        from . import licence
        chemin = licence.chemin_licence()
        if not os.path.isfile(chemin):
            return None
        with open(chemin, encoding="utf-8") as f:
            texte = f.read().strip()
        return texte or None
    except Exception:
        return None


def partage() -> bool:
    """True si les compteurs sont envoyés à l'agence (= une licence est enregistrée)."""
    return _licence_enregistree() is not None


def _a_envoyer(donnees: dict, aujourd_hui: date) -> list:
    """Les jours (30 derniers au plus) dont les valeurs diffèrent de la dernière confirmation."""
    limite = (aujourd_hui - timedelta(days=JOURS_ENVOYES - 1)).isoformat()
    jours = []
    for j in sorted(donnees["jours"]):
        if j < limite:
            continue
        v = donnees["jours"][j]
        if v != donnees["envoye"].get(j):
            jours.append({"jour": j, **v})
    return jours


def _envoyer_une_fois(texte_licence: str) -> bool:
    """Un envoi. True si le serveur a confirmé (ou s'il n'y avait rien à envoyer)."""
    with _VERROU:
        jours = _a_envoyer(_charger(), date.today())
    if not jours:
        return True
    import requests
    from . import config
    r = requests.post(
        f"{config.SUPABASE_URL}/functions/v1/admin",
        headers={"apikey": config.SUPABASE_ANON,
                 "Authorization": f"Bearer {config.SUPABASE_ANON}",
                 "Content-Type": "application/json"},
        json={"action": "activite", "licence": texte_licence, "jours": jours},
        timeout=DELAI_RESEAU_S)
    try:
        ok = bool(r.json().get("ok"))
    except Exception:
        ok = False
    if not ok:
        return False
    # Confirmé : on note les valeurs ENVOYÉES (pas celles d'aujourd'hui : un traitement
    # fini pendant l'envoi a pu en ajouter, elles partiront au prochain envoi).
    with _VERROU:
        donnees = _charger()
        for j in jours:
            donnees["envoye"][j["jour"]] = {c: j[c] for c in CATEGORIES}
        _sauver(donnees)
    return True


def envoyer() -> bool:
    """Envoie au serveur des licences les jours qui ont changé. Ne lève JAMAIS d'exception.

    Renvoie True si tout est à jour côté serveur, False sinon (pas de licence, pas de
    connexion, refus…). À appeler dans un fil d'arrière-plan : jusqu'à ~8 s hors-ligne."""
    global _relancer
    texte = _licence_enregistree()
    if texte is None:
        return False            # pas de licence : rien ne part (mode dev, tests…)
    if not _VERROU_ENVOI.acquire(blocking=False):
        _relancer = True        # un envoi tourne déjà : il refera un tour à la fin
        return False
    try:
        ok = False
        for _tour in range(3):
            _relancer = False
            try:
                ok = _envoyer_une_fois(texte)
            except Exception:
                ok = False      # hors-ligne, serveur absent… on réessaiera au prochain envoi
            if not (ok and _relancer):
                break
        return ok
    finally:
        _VERROU_ENVOI.release()
