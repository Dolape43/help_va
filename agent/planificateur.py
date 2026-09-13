"""
Automatisation horaire des publications.

Le calendrier range les médias dans :
    <ranger>/semaine-XX/jour-Y/<ordre>_<heure>_<type>/  (+ médias + legende.txt)

Mais "semaine-01/jour-1" est ABSTRAIT : il faut une DATE DE DÉBUT pour savoir
quand jour-1 tombe réellement. On calcule alors, pour chaque créneau, sa vraie
date/heure :

    date réelle = date_debut + ((semaine - 1) * 7 + (jour - 1)) jours,  à HHhMM

Ce module ne fait QUE de la logique (aucune interface, aucun navigateur) :
lister les créneaux datés, savoir lesquels sont à publier maintenant, et garder
la trace de ce qui est déjà publié (fichier d'état, pour survivre à un
redémarrage de l'app).

⚠️ Les STORIES ne sont pas automatisées (elles se postent à la main via Inssist).
"""

import os
import json
from datetime import datetime, timedelta, time as dt_time

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
EXT_MEDIAS = EXT_IMAGES | EXT_VIDEOS

FICHIER_ETAT = "_etat_planif.json"


# ---------------------------------------------------------------- petits outils

def _parse_heure(txt: str) -> dt_time:
    """'12h15' -> time(12, 15). Tolère '9h', '09h05'."""
    txt = txt.lower().replace(" ", "")
    if "h" in txt:
        h, m = txt.split("h", 1)
    else:
        h, m = txt, "0"
    return dt_time(int(h or 0), int(m or 0))


def _num(txt: str) -> int:
    """'semaine-01' -> 1 ; 'jour-3' -> 3."""
    return int(txt.split("-")[-1])


def _medias_du_slot(dossier: str) -> list:
    """Liste triée des médias (images + vidéos) d'un dossier créneau."""
    if not os.path.isdir(dossier):
        return []
    return [
        os.path.join(dossier, f)
        for f in sorted(os.listdir(dossier))
        if os.path.splitext(f)[1].lower() in EXT_MEDIAS
    ]


def _lire_legende(dossier: str) -> str:
    """Contenu de legende.txt (vide si absent)."""
    chemin = os.path.join(dossier, "legende.txt")
    if os.path.isfile(chemin):
        try:
            with open(chemin, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""
    return ""


# ---------------------------------------------------------------- lecture planning

def lister_creneaux(dossier_ranger: str, date_debut) -> list:
    """Retourne tous les créneaux datés, triés par date/heure croissante.

    date_debut : datetime.date (le jour-1 de la semaine-01).
    Chaque créneau = {
        "id": "semaine-01/jour-1/1_12h15_carousel",
        "quand": datetime,      # date + heure réelles
        "type": "reel"|"carousel"|"story",
        "medias": [chemins...],
        "legende": str,
        "dossier": chemin absolu,
    }
    """
    creneaux = []
    if not os.path.isdir(dossier_ranger):
        return creneaux

    for nom_sem in sorted(os.listdir(dossier_ranger)):
        chemin_sem = os.path.join(dossier_ranger, nom_sem)
        if not (nom_sem.startswith("semaine-") and os.path.isdir(chemin_sem)):
            continue
        for nom_jour in sorted(os.listdir(chemin_sem)):
            chemin_jour = os.path.join(chemin_sem, nom_jour)
            if not (nom_jour.startswith("jour-") and os.path.isdir(chemin_jour)):
                continue
            for slot in sorted(os.listdir(chemin_jour)):
                chemin_slot = os.path.join(chemin_jour, slot)
                if not os.path.isdir(chemin_slot):
                    continue
                parts = slot.split("_")
                if len(parts) < 3:
                    continue
                heure_txt, typ = parts[1], "_".join(parts[2:])
                try:
                    offset = (_num(nom_sem) - 1) * 7 + (_num(nom_jour) - 1)
                    quand = datetime.combine(
                        date_debut + timedelta(days=offset), _parse_heure(heure_txt))
                except Exception:
                    continue
                creneaux.append({
                    "id": f"{nom_sem}/{nom_jour}/{slot}",
                    "quand": quand,
                    "type": typ,
                    "medias": _medias_du_slot(chemin_slot),
                    "legende": _lire_legende(chemin_slot),
                    "dossier": chemin_slot,
                })

    creneaux.sort(key=lambda c: c["quand"])
    return creneaux


# ---------------------------------------------------------------- état (déjà publié)

def _chemin_etat(dossier_ranger: str) -> str:
    return os.path.join(dossier_ranger, FICHIER_ETAT)


def charger_etat(dossier_ranger: str) -> dict:
    chemin = _chemin_etat(dossier_ranger)
    if os.path.isfile(chemin):
        try:
            with open(chemin, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def sauver_etat(dossier_ranger: str, etat: dict) -> None:
    try:
        with open(_chemin_etat(dossier_ranger), "w", encoding="utf-8") as f:
            json.dump(etat, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def marquer(dossier_ranger: str, etat: dict, creneau_id: str, statut: str) -> None:
    """Enregistre le résultat d'un créneau ('publie' ou 'echec')."""
    etat[creneau_id] = {"statut": statut, "quand": datetime.now().isoformat(timespec="seconds")}
    sauver_etat(dossier_ranger, etat)


def _deja_publie(etat: dict, creneau_id: str) -> bool:
    return etat.get(creneau_id, {}).get("statut") == "publie"


# ---------------------------------------------------------------- sélection

def est_automatisable(creneau: dict) -> bool:
    """Vrai si le créneau peut être publié automatiquement (pas une story,
    et il a bien des médias)."""
    return creneau["type"] != "story" and bool(creneau["medias"])


def a_publier_maintenant(creneaux: list, etat: dict, maintenant: datetime,
                         rattrapage: bool, debut: datetime) -> list:
    """Créneaux dont l'heure est atteinte et qui restent à publier.

    rattrapage=False : on ignore le passé antérieur au démarrage (debut),
    on ne publie que les créneaux prévus À PARTIR du lancement de l'auto.
    rattrapage=True  : on publie aussi les créneaux en retard (déjà passés).
    Triés du plus ancien au plus récent.
    """
    dus = []
    for c in creneaux:
        if not est_automatisable(c):
            continue
        if c["id"] in etat:          # déjà tenté (publié OU échoué) -> on ne rejoue pas
            continue
        if c["quand"] > maintenant:
            continue
        if not rattrapage and c["quand"] < debut:
            continue
        dus.append(c)
    dus.sort(key=lambda c: c["quand"])
    return dus


def prochain(creneaux: list, etat: dict, maintenant: datetime):
    """Le prochain créneau automatisable à venir (ou None)."""
    futurs = [c for c in creneaux
              if est_automatisable(c) and not _deja_publie(etat, c["id"])
              and c["quand"] > maintenant]
    return futurs[0] if futurs else None


def resume(creneaux: list, etat: dict, maintenant: datetime) -> dict:
    """Petit bilan pour l'affichage."""
    auto = [c for c in creneaux if est_automatisable(c)]
    publies = [c for c in auto if _deja_publie(etat, c["id"])]
    a_venir = [c for c in auto if not _deja_publie(etat, c["id"]) and c["quand"] > maintenant]
    en_retard = [c for c in auto if not _deja_publie(etat, c["id"]) and c["quand"] <= maintenant]
    stories = [c for c in creneaux if c["type"] == "story"]
    en_retard.sort(key=lambda c: c["quand"])
    return {
        "total_auto": len(auto),
        "publies": len(publies),
        "a_venir": len(a_venir),
        "en_retard": len(en_retard),
        "en_retard_liste": en_retard,   # détail des créneaux en retard
        "stories": len(stories),
        "prochain": prochain(creneaux, etat, maintenant),
    }
