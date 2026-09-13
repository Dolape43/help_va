"""
Range les médias dans une arborescence de dossiers selon le calendrier.

Toi tu déposes :
  sources/videos/  -> tes vidéos (serviront aux Reels)
  sources/images/  -> tes images (l'agent y pioche pour Carousels + Stories)

L'agent crée :
  planning/semaine-XX/jour-Y/<ordre>_<heure>_<type>/  + les médias + legende.txt

Règles :
  - Reel     -> 1 vidéo
  - Carousel -> IMAGES_PAR_CAROUSEL images
  - Story    -> 1 image
On consomme les médias dans l'ordre (tri par nom de fichier).
"""

import os
import random
import shutil

from .calendrier import charger_calendrier
from .config import (
    DOSSIER_SOURCE_VIDEOS,
    DOSSIER_SOURCE_IMAGES,
    DOSSIER_PLANNING,
    IMAGES_PAR_CAROUSEL,
    MODE_RANGEMENT,
)

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def _lister(dossier: str, extensions: set) -> list:
    """Liste triée des fichiers d'un dossier ayant une de ces extensions."""
    if not os.path.isdir(dossier):
        return []
    fichiers = [
        os.path.join(dossier, f)
        for f in sorted(os.listdir(dossier))
        if os.path.splitext(f)[1].lower() in extensions
    ]
    return fichiers


def _besoins(calendrier: dict) -> dict:
    """Compte combien de reels / carousels / stories le calendrier demande."""
    n = {"reel": 0, "carousel": 0, "story": 0}
    for semaine in calendrier.values():
        for jour in semaine.values():
            for creneau in jour:
                n[creneau["type"]] += 1
    return n


def verifier_dossiers(dossier_videos: str, dossier_images: str) -> dict:
    """Vérifie que chaque dossier contient le bon type de fichiers.

    Retourne les fichiers mal placés (images dans videos/, vidéos dans images/)
    et les comptes de fichiers valides.
    """
    def contenu(d):
        return os.listdir(d) if os.path.isdir(d) else []

    v, i = contenu(dossier_videos), contenu(dossier_images)
    ext = lambda f: os.path.splitext(f)[1].lower()
    return {
        "img_dans_videos": [f for f in v if ext(f) in EXT_IMAGES],
        "vid_dans_images": [f for f in i if ext(f) in EXT_VIDEOS],
        "nb_videos": len([f for f in v if ext(f) in EXT_VIDEOS]),
        "nb_images": len([f for f in i if ext(f) in EXT_IMAGES]),
    }


def _txt_du_jour(jour_dir: str):
    """Dépose un fichier legendes.txt VIDE dans le dossier d'un JOUR (si absent).

    L'utilisateur s'en sert pour écrire lui-même ses légendes/notes du jour."""
    try:
        os.makedirs(jour_dir, exist_ok=True)
        chemin = os.path.join(jour_dir, "legendes.txt")
        if not os.path.exists(chemin):
            open(chemin, "a", encoding="utf-8").close()
    except Exception:
        pass


def _placer(fichier_source: str, dossier_dest: str, simuler: bool):
    """Copie (ou déplace) un fichier vers un dossier destination."""
    if simuler:
        return
    os.makedirs(dossier_dest, exist_ok=True)
    dest = os.path.join(dossier_dest, os.path.basename(fichier_source))
    if MODE_RANGEMENT == "deplacer":
        shutil.move(fichier_source, dest)
    else:
        shutil.copy2(fichier_source, dest)


def ranger(dossier_videos: str = None, dossier_images: str = None,
           dossier_sortie: str = None, simuler: bool = False,
           aleatoire: bool = True) -> dict:
    """Range les médias selon le calendrier. Retourne un résumé.

    dossier_videos / dossier_images : où lire les médias (défaut = config).
    dossier_sortie : où écrire le planning (défaut = config).
    simuler=True : n'écrit rien, montre seulement ce qui serait fait.
    aleatoire=True (défaut) : mélange les médias au hasard avant de les répartir
        (au lieu de suivre l'ordre 1, 2, 3…). Le carrousel garde des images
        cohérentes entre elles seulement si tu ne mélanges pas — ici c'est du
        hasard total, demandé par l'utilisateur.
    """
    dossier_videos = dossier_videos or DOSSIER_SOURCE_VIDEOS
    dossier_images = dossier_images or DOSSIER_SOURCE_IMAGES
    dossier_sortie = dossier_sortie or DOSSIER_PLANNING

    videos = _lister(dossier_videos, EXT_VIDEOS)
    images = _lister(dossier_images, EXT_IMAGES)

    if aleatoire:
        random.shuffle(videos)
        random.shuffle(images)

    calendrier = charger_calendrier()
    besoins = _besoins(calendrier)
    # Les carrousels sont rangés SÉPARÉMENT -> ici les images ne servent qu'aux
    # stories.
    images_requises = besoins["story"]

    print("=== Rangement des médias ===", flush=True)
    print(f"Sortie : {os.path.abspath(dossier_sortie)}", flush=True)
    print(f"Mode : {'SIMULATION (rien écrit)' if simuler else MODE_RANGEMENT}", flush=True)
    print(f"Vidéos disponibles : {len(videos)}  | requises (reels) : {besoins['reel']}", flush=True)
    print(f"Images disponibles : {len(images)}  | requises (stories) : {images_requises}", flush=True)
    print(f"(Carrousels : {besoins['carousel']} — rangés séparément)", flush=True)
    print("-" * 50, flush=True)

    # Itérateurs consommables
    i_video = iter(videos)
    i_image = iter(images)
    manques = []

    for nom_semaine, jours in calendrier.items():
        for nom_jour, creneaux in jours.items():
            for ordre, creneau in enumerate(creneaux, start=1):
                heure = creneau["heure"]
                typ = creneau["type"]
                slot = f"{ordre}_{heure}_{typ}"
                dossier_slot = os.path.join(dossier_sortie, nom_semaine, nom_jour, slot)

                if not simuler:
                    os.makedirs(dossier_slot, exist_ok=True)
                    # legende.txt pour reel/carousel ; rien pour les stories.
                    if typ in ("reel", "carousel"):
                        open(os.path.join(dossier_slot, "legende.txt"), "a", encoding="utf-8").close()
                    # .txt VIDE au niveau du JOUR : l'utilisateur y écrit ce qu'il
                    # veut (légendes, notes…). Créé une seule fois par jour.
                    _txt_du_jour(os.path.dirname(dossier_slot))

                if typ == "reel":
                    fichier = next(i_video, None)
                    if fichier is None:
                        manques.append(f"{nom_semaine}/{nom_jour}/{slot} : vidéo manquante")
                    else:
                        _placer(fichier, dossier_slot, simuler)

                elif typ == "carousel":
                    # Carrousels gérés SÉPARÉMENT (ranger_carrousels) : ici on
                    # crée juste l'emplacement vide, on ne consomme pas d'images.
                    pass

                elif typ == "story":
                    fichier = next(i_image, None)
                    if fichier is None:
                        manques.append(f"{nom_semaine}/{nom_jour}/{slot} : image manquante")
                    else:
                        _placer(fichier, dossier_slot, simuler)

    # Surplus : médias non consommés -> dossier "surplus"
    surplus = list(i_video) + list(i_image)
    if surplus and not simuler:
        dossier_surplus = os.path.join(dossier_sortie, "surplus")
        os.makedirs(dossier_surplus, exist_ok=True)
        for f in surplus:
            _placer(f, dossier_surplus, simuler=False)

    # Manques (combien de médias en trop peu)
    manque_videos = max(0, besoins["reel"] - len(videos))
    manque_images = max(0, images_requises - len(images))

    print(f"Créneaux : {besoins['reel']} reels, {besoins['carousel']} carousels, "
          f"{besoins['story']} stories", flush=True)
    if manques:
        print(f"\n⚠️  {len(manques)} créneau(x) incomplet(s) (pas assez de médias) :", flush=True)
        for m in manques[:15]:
            print("   -", m, flush=True)
        if len(manques) > 15:
            print(f"   ... et {len(manques) - 15} autres", flush=True)
    else:
        print("\n✅ Tous les créneaux ont reçu leurs médias.", flush=True)
    if surplus:
        print(f"\n📦 {len(surplus)} média(s) en surplus -> dossier 'surplus'.", flush=True)

    return {"besoins": besoins, "videos": len(videos), "images": len(images),
            "images_requises": images_requises, "manques": manques,
            "surplus": len(surplus), "manque_videos": manque_videos,
            "manque_images": manque_images}


# ======================================================================
#  Rangement SÉPARÉ des carrousels (dossier dédié, ordre respecté)
# ======================================================================

def _cle_numerique(chemin: str):
    """Clé de tri NUMÉRIQUE : 1, 2, …, 9, 10, 11 (et non 1, 10, 11, 2…).

    L'utilisateur nomme ses photos 1, 2, 3… ; on doit respecter cet ordre
    exact pour que les carrousels soient cohérents (3 photos qui se suivent).
    """
    import re
    nom = os.path.splitext(os.path.basename(chemin))[0]
    m = re.match(r"\s*(\d+)", nom)
    return (0, int(m.group(1))) if m else (1, nom.lower())


def ranger_carrousels(dossier_carrousel: str, dossier_sortie: str = None,
                      simuler: bool = False) -> dict:
    """Remplit UNIQUEMENT les créneaux 'carousel' du calendrier, DANS L'ORDRE.

    Les photos du dossier (nommées 1, 2, 3…) sont prises par groupes de
    IMAGES_PAR_CAROUSEL consécutifs : 1-2-3 -> 1er carrousel, 4-5-6 -> 2e, etc.
    Copie (ne déplace pas) pour pouvoir relancer. Retourne un résumé.
    """
    dossier_sortie = dossier_sortie or DOSSIER_PLANNING
    if not os.path.isdir(dossier_carrousel):
        raise RuntimeError(f"Dossier carrousel introuvable : {dossier_carrousel}")

    images = _lister(dossier_carrousel, EXT_IMAGES)
    images.sort(key=_cle_numerique)      # ORDRE numérique (1,2,3,…,10,11)

    calendrier = charger_calendrier()
    besoins = _besoins(calendrier)
    n_carrousels = besoins["carousel"]

    print("=== Rangement des carrousels (ordre respecté) ===", flush=True)
    print(f"Photos disponibles : {len(images)}  | requises : "
          f"{n_carrousels}×{IMAGES_PAR_CAROUSEL} = {n_carrousels * IMAGES_PAR_CAROUSEL}", flush=True)
    print("-" * 50, flush=True)

    i_image = iter(images)
    manques = []
    faits = 0

    for nom_semaine, jours in calendrier.items():
        for nom_jour, creneaux in jours.items():
            for ordre, creneau in enumerate(creneaux, start=1):
                if creneau["type"] != "carousel":
                    continue
                heure = creneau["heure"]
                slot = f"{ordre}_{heure}_carousel"
                dossier_slot = os.path.join(dossier_sortie, nom_semaine, nom_jour, slot)

                if not simuler:
                    os.makedirs(dossier_slot, exist_ok=True)
                    # nettoie les images déjà présentes (relance propre)
                    for f in os.listdir(dossier_slot):
                        if os.path.splitext(f)[1].lower() in EXT_IMAGES:
                            try:
                                os.remove(os.path.join(dossier_slot, f))
                            except Exception:
                                pass
                    lg = os.path.join(dossier_slot, "legende.txt")
                    if not os.path.exists(lg):
                        open(lg, "a", encoding="utf-8").close()
                    _txt_du_jour(os.path.dirname(dossier_slot))   # .txt vide du jour

                pris = 0
                for _ in range(IMAGES_PAR_CAROUSEL):
                    fichier = next(i_image, None)
                    if fichier is None:
                        break
                    if not simuler:
                        os.makedirs(dossier_slot, exist_ok=True)
                        shutil.copy2(fichier, os.path.join(dossier_slot,
                                                           os.path.basename(fichier)))
                    pris += 1
                faits += 1
                if pris < IMAGES_PAR_CAROUSEL:
                    manques.append(f"{nom_semaine}/{nom_jour}/{slot} : "
                                   f"{pris}/{IMAGES_PAR_CAROUSEL} photos")

    if manques:
        print(f"\n⚠️  {len(manques)} carrousel(s) incomplet(s) (pas assez de photos) :", flush=True)
        for m in manques[:15]:
            print("   -", m, flush=True)
    else:
        print(f"\n✅ {faits} carrousel(s) remplis dans l'ordre.", flush=True)

    return {"carrousels": faits, "photos": len(images),
            "requises": n_carrousels * IMAGES_PAR_CAROUSEL, "manques": manques}
