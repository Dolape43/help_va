"""
Range les médias dans une arborescence de dossiers selon le calendrier.

Chaque TYPE de post a son propre dossier source :
  - Réels        -> uniquement des vidéos (1 par créneau)
  - Stories      -> uniquement des images (1 par créneau)
  - Stories CTA  -> uniquement des images (1 par créneau)
  - Carrousels   -> images nommées 1, 2, 3… prises DANS L'ORDRE par groupes
                    de IMAGES_PAR_CAROUSEL

Résultat :
  <sortie>/semaine-XX/jour-Y/<ordre>_<heure>_<type>/  + les médias
  (+ legende.txt pour les réels et carrousels, + legendes.txt par jour)

L'utilisateur choisit quels types ranger : les créneaux des types décochés
ne sont pas créés. Les originaux ne sont jamais modifiés (copie).
"""

import os
import random
import re
import shutil

from .calendrier import charger_calendrier
from .config import IMAGES_PAR_CAROUSEL

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

# Types de posts, dans l'ordre d'affichage.
TYPES = ("reel", "story", "story_cta", "carousel")
LIBELLES = {"reel": "Réels", "story": "Stories", "story_cta": "Stories CTA",
            "carousel": "Carrousels"}
# Libellé d'UN créneau (éditeur de calendrier).
LIBELLE_CRENEAU = {"reel": "Réel", "story": "Story", "story_cta": "Story CTA",
                   "carousel": "Carrousel"}
# Nom du type dans le dossier du créneau (ex. 3_21h00_story-cta).
NOM_DOSSIER = {"reel": "reel", "story": "story", "story_cta": "story-cta",
               "carousel": "carousel"}


def est_video(typ: str) -> bool:
    return typ == "reel"


def medias_par_creneau(typ: str) -> int:
    return IMAGES_PAR_CAROUSEL if typ == "carousel" else 1


def compter(calendrier: dict = None) -> dict:
    """Nombre de créneaux de chaque type dans le calendrier."""
    cal = charger_calendrier() if calendrier is None else calendrier
    n = {t: 0 for t in TYPES}
    for jours in cal.values():
        for creneaux in jours.values():
            for cr in creneaux:
                if cr.get("type") in n:
                    n[cr["type"]] += 1
    return n


def _cle_numerique(chemin: str):
    """Tri NUMÉRIQUE : 1, 2, …, 9, 10, 11 (et non 1, 10, 11, 2…)."""
    nom = os.path.splitext(os.path.basename(chemin))[0]
    m = re.match(r"\s*(\d+)", nom)
    return (0, int(m.group(1)), nom.lower()) if m else (1, 0, nom.lower())


def analyser_dossier(dossier: str, typ: str) -> dict:
    """Fichiers utilisables pour ce type + nombre de fichiers ignorés
    (ex. une image posée dans le dossier des réels)."""
    ext_ok = EXT_VIDEOS if est_video(typ) else EXT_IMAGES
    valides, ignores = [], 0
    if dossier and os.path.isdir(dossier):
        for f in os.listdir(dossier):
            p = os.path.join(dossier, f)
            if not os.path.isfile(p) or f.startswith("."):
                continue
            if os.path.splitext(f)[1].lower() in ext_ok:
                valides.append(p)
            else:
                ignores += 1
    valides.sort(key=_cle_numerique)
    return {"fichiers": valides, "ignores": ignores}


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


def _copier(source: str, dossier_dest: str):
    os.makedirs(dossier_dest, exist_ok=True)
    shutil.copy2(source, os.path.join(dossier_dest, os.path.basename(source)))


def ranger(sources: dict, dossier_sortie: str, types_actifs=None,
           aleatoire: bool = True, progress=None, doit_arreter=None) -> dict:
    """Range les médias selon le calendrier, type par type.

    sources      : {type: dossier} — un dossier source par type de post.
    types_actifs : types à ranger (les autres créneaux ne sont pas créés).
    aleatoire    : mélange les réels / stories / stories CTA ; les carrousels
                   gardent TOUJOURS l'ordre 1, 2, 3… (photos qui se suivent).
    progress(txt): appelé pendant le rangement (texte d'avancement).
    """
    choisis = TYPES if types_actifs is None else types_actifs
    actifs = [t for t in TYPES if t in choisis]
    calendrier = charger_calendrier()
    besoins = compter(calendrier)

    medias, ignores = {}, {}
    for t in actifs:
        a = analyser_dossier(sources.get(t), t)
        fichiers = a["fichiers"]
        if aleatoire and t != "carousel":
            random.shuffle(fichiers)
        medias[t], ignores[t] = fichiers, a["ignores"]

    print("=== Rangement des médias ===", flush=True)
    print(f"Sortie : {os.path.abspath(dossier_sortie)}", flush=True)
    for t in actifs:
        unite = "vidéo(s)" if est_video(t) else "image(s)"
        requis = besoins[t] * medias_par_creneau(t)
        print(f"{LIBELLES[t]} : {len(medias[t])} {unite} fournie(s) | requises : {requis}",
              flush=True)
    print("-" * 50, flush=True)

    total = sum(besoins[t] for t in actifs)
    iterateurs = {t: iter(medias[t]) for t in actifs}
    places = {t: 0 for t in actifs}
    incomplets = {t: 0 for t in actifs}
    fait = 0
    arrete = False

    for nom_semaine, jours in calendrier.items():
        for nom_jour, creneaux in jours.items():
            du_jour = [cr for cr in creneaux if cr.get("type") in actifs]
            for ordre, cr in enumerate(du_jour, start=1):
                if doit_arreter and doit_arreter():
                    arrete = True
                    break
                t = cr["type"]
                slot = f"{ordre}_{cr.get('heure', '')}_{NOM_DOSSIER[t]}"
                dossier_slot = os.path.join(dossier_sortie, nom_semaine, nom_jour, slot)
                os.makedirs(dossier_slot, exist_ok=True)
                if t in ("reel", "carousel"):
                    open(os.path.join(dossier_slot, "legende.txt"), "a",
                         encoding="utf-8").close()
                _txt_du_jour(os.path.dirname(dossier_slot))

                pris = 0
                for _ in range(medias_par_creneau(t)):
                    f = next(iterateurs[t], None)
                    if f is None:
                        break
                    _copier(f, dossier_slot)
                    pris += 1
                places[t] += pris
                if pris < medias_par_creneau(t):
                    incomplets[t] += 1

                fait += 1
                if progress:
                    progress(f"Rangement : {fait}/{total} créneau(x)")
            if arrete:
                break
        if arrete:
            break

    # Surplus : médias non utilisés -> surplus/<type>
    surplus = {}
    if not arrete:
        for t in actifs:
            reste = list(iterateurs[t])
            if reste:
                d = os.path.join(dossier_sortie, "surplus", LIBELLES[t])
                for f in reste:
                    _copier(f, d)
            surplus[t] = len(reste)

    manques = {t: max(0, besoins[t] * medias_par_creneau(t) - len(medias[t]))
               for t in actifs}
    if arrete:
        print("\n⛔ Rangement arrêté.", flush=True)
    elif any(incomplets.values()):
        print("\n⚠️  Créneaux incomplets (pas assez de médias) :", flush=True)
        for t in actifs:
            if incomplets[t]:
                print(f"   - {LIBELLES[t]} : {incomplets[t]} créneau(x)", flush=True)
    else:
        print("\n✅ Tous les créneaux ont reçu leurs médias.", flush=True)

    return {"types": actifs, "besoins": {t: besoins[t] for t in actifs},
            "fournis": {t: len(medias[t]) for t in actifs}, "places": places,
            "manques": manques, "incomplets": incomplets, "surplus": surplus,
            "ignores": ignores, "creneaux": fait, "arrete": arrete}
