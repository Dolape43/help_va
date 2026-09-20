"""
Rend chaque image "unique" pour éviter la détection de doublon par Instagram.

Rappel important : Instagram SUPPRIME l'EXIF à l'upload et détecte les
doublons via un hash du CONTENU (les pixels). Changer seulement les
métadonnées ne suffit donc pas — on modifie aussi légèrement les pixels,
de façon imperceptible à l'œil.

Transformations appliquées (toutes subtiles) :
  - nettoyage de l'EXIF
  - micro-ajustements luminosité / contraste / saturation (±2-3 %)
  - micro-recadrage de quelques pixels (puis remise à la taille d'origine)
  - bruit très léger
  - ré-encodage JPEG avec une qualité légèrement variable
  - nouvelle date de fichier
  - (option) miroir horizontal — plus efficace mais VISIBLE

Chaque appel produit une variation différente (aléatoire).
"""

import os
import random
import subprocess
import sys

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

# Active la lecture des photos iPhone (.heic/.heif) dans PIL, si dispo.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIC_OK = True
except Exception:
    _HEIC_OK = False

from .config import UNICITE_FLIP_HORIZONTAL

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def _filtre_leger(img: "Image.Image") -> "Image.Image":
    """Filtre UNIQUE : un léger ton FROID (bleuté/cinéma), discret.

    Le même rendu pour TOUTES les images (plus de styles chaud/vif/doux ni de
    vignette). Léger : on baisse un peu le rouge et on remonte un peu le bleu.
    De petites variations aléatoires (imperceptibles) suffisent à garder chaque
    copie unique côté pixels.
    """
    r, g, b = img.split()
    r = r.point(lambda p: int(p * random.uniform(0.95, 0.98)))          # un peu moins de rouge
    b = b.point(lambda p: min(255, int(p * random.uniform(1.02, 1.05))))  # un peu plus de bleu
    img = Image.merge("RGB", (r, g, b))
    img = ImageEnhance.Contrast(img).enhance(random.uniform(1.00, 1.02))
    return img


def uniquiser_image(source: str, dest: str | None = None, filtre: bool = False) -> str:
    """Crée une version unique de l'image. dest=None -> remplace l'original.

    filtre=True : applique en plus un filtre photo léger (chaud/froid/vif/doux).
    Retourne le chemin du fichier écrit.
    """
    if dest is None:
        dest = source

    # 1) Ouverture. draft() demande au décodeur JPEG de décoder DIRECTEMENT à une
    #    échelle réduite (il saute des coefficients) : énorme gain sur les grosses
    #    photos. Sans effet sur les autres formats.
    MAX_L, MAX_H = 1080, 1920
    img = Image.open(source)
    try:
        img.draft("RGB", (MAX_L, MAX_H))
    except Exception:
        pass
    # Redresser selon l'orientation EXIF AVANT de retirer l'EXIF, sinon les photos
    # de téléphone sortiraient couchées.
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    # Réduction à la taille utile pour Instagram (max 1080 x 1920) : plus rapide,
    # fichiers plus légers, sans perte visible (Instagram plafonne à ~1080 px).
    w0, h0 = img.size
    if w0 > MAX_L or h0 > MAX_H:
        ratio = min(MAX_L / w0, MAX_H / h0)
        img = img.resize((max(1, round(w0 * ratio)), max(1, round(h0 * ratio))), Image.LANCZOS)

    # 2) Miroir horizontal (optionnel, visible)
    if UNICITE_FLIP_HORIZONTAL:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    # 3) Micro-recadrage (1 à 4 px par bord) : décale les pixels et change la
    #    taille -> hash cassé. On ne redimensionne PAS pour revenir à la taille
    #    d'origine (gain de temps ; quelques pixels de moins sont invisibles).
    L, H = img.size
    g = random.randint(1, 4); h = random.randint(1, 4)
    d = random.randint(1, 4); b = random.randint(1, 4)
    img = img.crop((g, h, L - d, H - b))

    # 4) UNE SEULE passe numpy : saturation + luminosité + contraste + bruit.
    #    (remplace 3 passes PIL + une passe bruit -> beaucoup plus rapide)
    rng = np.random.default_rng()          # instance locale => sûr en multi-thread
    f_sat = random.uniform(0.97, 1.03)
    f_lum = random.uniform(0.97, 1.03)
    f_con = random.uniform(0.97, 1.03)
    arr = np.asarray(img, dtype=np.float32)
    lum = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2])[..., None]
    arr = arr * f_sat + lum * (1.0 - f_sat)            # saturation
    if filtre:                                          # ton légèrement froid
        arr[..., 0] *= random.uniform(0.95, 0.98)
        arr[..., 2] *= random.uniform(1.02, 1.05)
    bruit = rng.integers(-2, 3, arr.shape, dtype=np.int16).astype(np.float32)
    arr = arr * (f_lum * f_con) + (128.0 * (1.0 - f_con) * f_lum) + bruit
    np.clip(arr, 0, 255, out=arr)
    img = Image.fromarray(arr.astype(np.uint8), "RGB")

    # 5) Ré-encodage JPEG, qualité variable, SANS EXIF (optimize off = plus rapide).
    if os.path.splitext(dest)[1].lower() not in {".jpg", ".jpeg"}:
        dest = os.path.splitext(dest)[0] + ".jpg"
    img.save(dest, "JPEG", quality=random.randint(90, 96))

    # 6) Nouvelle date de fichier (modifie une métadonnée du fichier).
    #    Décalage aléatoire dans les ~30 derniers jours.
    decalage = random.randint(0, 30 * 24 * 3600)
    t = os.path.getmtime(dest) - decalage
    os.utime(dest, (t, t))

    return dest


def _ffmpeg_exe() -> str:
    """Chemin du binaire ffmpeg (embarqué via imageio-ffmpeg)."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def uniquiser_video(source: str, dest: str | None = None) -> str:
    """Crée une version unique d'une vidéo (métadonnées + ré-encodage léger).

    On nettoie toutes les métadonnées et on ré-encode avec de micro-variations
    (luminosité/contraste imperceptibles, qualité variable) : la vidéo reste
    identique à l'œil mais son empreinte (hash) change.
    """
    if dest is None:
        dest = source
    if os.path.splitext(dest)[1].lower() != ".mp4":
        dest = os.path.splitext(dest)[0] + ".mp4"

    # ffmpeg ne peut pas lire et écrire le même fichier : passe par un temporaire.
    sur_place = os.path.abspath(dest) == os.path.abspath(source)
    sortie = dest + ".tmp.mp4" if sur_place else dest

    b = round(random.uniform(-0.02, 0.02), 3)     # luminosité
    c = round(random.uniform(0.98, 1.02), 3)      # contraste
    crf = random.randint(23, 28)                  # qualité (plus haut = + compressé)

    cmd = [
        _ffmpeg_exe(), "-y", "-i", source,
        "-map_metadata", "-1",                    # supprime toutes les métadonnées
        "-vf", f"eq=brightness={b}:contrast={c}",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        sortie,
    ]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError("Échec ffmpeg : " + r.stderr.decode("utf-8", "ignore")[-300:])

    if sur_place:
        os.replace(sortie, dest)

    # Nouvelle date de fichier (métadonnée du fichier).
    t = os.path.getmtime(dest) - random.randint(0, 30 * 24 * 3600)
    os.utime(dest, (t, t))
    return dest


def uniquiser_dossier(dossier: str, dossier_sortie: str = None,
                      renommer: bool = False, filtre: bool = False) -> int:
    """Uniquise images ET vidéos d'un dossier. Retourne le nombre traité.

    dossier_sortie=None : modifie les fichiers sur place.
    dossier_sortie fourni : écrit des COPIES uniques dans deux sous-dossiers :
        <dossier_sortie>/images/  (images uniquifiées)
        <dossier_sortie>/videos/  (vidéos uniquifiées)
    renommer=True : images -> 1.jpg, 2.jpg… ; vidéos -> 1.mp4, 2.mp4…
    filtre=True  : applique un filtre léger sur les images.
    """
    if not os.path.isdir(dossier):
        raise RuntimeError(f"Dossier introuvable : {dossier}")

    fichiers = []
    for racine, _, noms in os.walk(dossier):
        for f in sorted(noms):
            fichiers.append(os.path.join(racine, f))
    return uniquiser_fichiers(fichiers, dossier_sortie, renommer, filtre)


def uniquiser_fichiers(fichiers: list, dossier_sortie: str = None,
                       renommer: bool = False, filtre: bool = False) -> int:
    """Uniquise une LISTE de fichiers (images/vidéos) choisis. Retourne le nb traité.

    Mêmes règles que uniquiser_dossier (sortie en images\\ et videos\\).
    """
    images = [f for f in fichiers if os.path.splitext(f)[1].lower() in EXT_IMAGES]
    videos = [f for f in fichiers if os.path.splitext(f)[1].lower() in EXT_VIDEOS]

    # Modification SUR PLACE (pas de dossier de sortie) : séquentiel.
    if not dossier_sortie:
        n = 0
        for source in images + videos:
            try:
                if source in images:
                    uniquiser_image(source, filtre=filtre)
                else:
                    uniquiser_video(source)
                n += 1
            except Exception as e:
                print(f"   [!] {os.path.basename(source)} ignoré : {e}", flush=True)
        return n

    sortie_images = os.path.join(dossier_sortie, "images")
    sortie_videos = os.path.join(dossier_sortie, "videos")
    n_img = n_vid = 0
    if images:
        os.makedirs(sortie_images, exist_ok=True)
        n_img = _traiter_parallele(
            _planifier(sortie_images, images, renommer, ".jpg"),
            lambda s, d: uniquiser_image(s, d, filtre=filtre))
    if videos:
        os.makedirs(sortie_videos, exist_ok=True)
        for source, dest in _planifier(sortie_videos, videos, renommer, ".mp4"):
            try:
                uniquiser_video(source, dest)
                n_vid += 1
            except Exception as e:
                print(f"   [!] {os.path.basename(source)} ignoré : {e}", flush=True)
    return n_img + n_vid


def _nb_travailleurs() -> int:
    """Nombre de threads pour traiter les images (1 par cœur, plafonné)."""
    try:
        n = os.cpu_count() or 2
    except Exception:
        n = 2
    return max(1, min(n, 8))


def _planifier(cible: str, sources: list, renommer: bool, ext: str) -> list:
    """Attribue À L'AVANCE un chemin de sortie unique à chaque source.

    Fait en séquentiel : garantit zéro collision de noms même quand le
    traitement est ensuite lancé en parallèle.
    """
    plans, pris = [], set()
    for i, src in enumerate(sources, 1):
        base = f"{i}{ext}" if renommer else os.path.splitext(os.path.basename(src))[0] + ext
        stem, e = os.path.splitext(base)
        nom, k = base, 2
        while nom.lower() in pris or os.path.exists(os.path.join(cible, nom)):
            nom = f"{stem}_{k}{e}"
            k += 1
        pris.add(nom.lower())
        plans.append((src, os.path.join(cible, nom)))
    return plans


def _traiter_parallele(plans: list, fn, doit_arreter=None) -> int:
    """Applique fn(source, dest) à tous les plans, en parallèle sur les cœurs.

    Un fichier en erreur est ignoré (il n'arrête pas le lot). Renvoie le nombre
    de fichiers réellement traités.
    """
    if not plans:
        return 0
    travailleurs = _nb_travailleurs()

    def _un(plan):
        src, dest = plan
        if doit_arreter and doit_arreter():
            return 0
        try:
            fn(src, dest)
            return 1
        except Exception as e:
            print(f"   [!] {os.path.basename(src)} ignoré : {e}", flush=True)
            return 0

    if travailleurs == 1 or len(plans) == 1:
        return sum(_un(p) for p in plans)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=travailleurs) as ex:
        return sum(ex.map(_un, plans))


def _dest_libre(cible: str, base: str) -> str:
    """Chemin de sortie qui n'écrase pas un fichier existant (ajoute _2, _3…)."""
    dest = os.path.join(cible, base)
    stem, ext = os.path.splitext(base)
    k = 2
    while os.path.exists(dest):
        dest = os.path.join(cible, f"{stem}_{k}{ext}")
        k += 1
    return dest


def uniquiser_arbre(dossier: str, dossier_sortie: str, renommer: bool = False,
                    filtre: bool = False, progress=None, doit_arreter=None) -> dict:
    """Uniquise un dossier EN CONSERVANT son arborescence (sous-dossiers inclus).

    Reproduit, sous <dossier_sortie>, la même structure que <dossier> mais avec
    chaque image/vidéo uniquifiée. Les fichiers non-médias sont ignorés ; un
    sous-dossier sans média n'est pas recréé.

    progress(texte) : appelé (thread-safe côté appelant) à l'entrée et à la fin
        de chaque sous-dossier, pour un affichage vivant (« Dossier i/N … »).
    doit_arreter() : si fourni et renvoie True, on s'arrête proprement.
    Retourne {"medias": int, "dossiers": int, "arrete": bool}.
    """
    if not os.path.isdir(dossier):
        raise RuntimeError(f"Dossier introuvable : {dossier}")

    # Recense les sous-dossiers CONTENANT au moins un média (racine incluse).
    groupes = []
    for racine, _sous, noms in os.walk(dossier):
        medias = [os.path.join(racine, f) for f in sorted(noms)
                  if os.path.splitext(f)[1].lower() in (EXT_IMAGES | EXT_VIDEOS)]
        if medias:
            groupes.append((racine, medias))
    groupes.sort(key=lambda g: g[0].lower())
    total_d = len(groupes)
    if total_d == 0:
        raise RuntimeError("Aucune image ni vidéo trouvée dans ce dossier.")

    n_total = 0
    arrete = False
    for i, (racine, medias) in enumerate(groupes, 1):
        if doit_arreter and doit_arreter():
            arrete = True
            break
        rel = os.path.relpath(racine, dossier)
        nom_aff = "(dossier principal)" if rel == "." else rel
        cible = dossier_sortie if rel == "." else os.path.join(dossier_sortie, rel)
        os.makedirs(cible, exist_ok=True)
        if progress:
            try:
                progress(f"Dossier {i}/{total_d} : {nom_aff} — en cours…")
            except Exception:
                pass
        images = [f for f in medias if os.path.splitext(f)[1].lower() in EXT_IMAGES]
        videos = [f for f in medias if os.path.splitext(f)[1].lower() in EXT_VIDEOS]
        # Images : en parallèle (plusieurs cœurs). Noms attribués avant -> pas de collision.
        n_img = _traiter_parallele(
            _planifier(cible, images, renommer, ".jpg"),
            lambda s, d: uniquiser_image(s, d, filtre=filtre),
            doit_arreter)
        # Vidéos : en séquentiel (ffmpeg sature déjà tous les cœurs à lui seul).
        n_vid = 0
        for source, dest in _planifier(cible, videos, renommer, ".mp4"):
            if doit_arreter and doit_arreter():
                arrete = True
                break
            try:
                uniquiser_video(source, dest)
                n_vid += 1
            except Exception as e:
                print(f"   [!] {os.path.basename(source)} ignoré : {e}", flush=True)
        if doit_arreter and doit_arreter():
            arrete = True
        n_total += n_img + n_vid
        print(f"[{i}/{total_d}] {nom_aff} : {n_img} image(s), {n_vid} vidéo(s)", flush=True)
        if progress and not arrete:
            try:
                progress(f"Dossier {i}/{total_d} : {nom_aff} — terminé "
                         f"({n_img + n_vid} média(s))")
            except Exception:
                pass
        if arrete:
            break
    return {"medias": n_total, "dossiers": total_d, "arrete": arrete}


# ======================================================================
#  Conversion de format d'images (JPG / PNG) — SANS uniquisation.
#  Convertit n'importe quelle image (y compris HEIC/HEIF iPhone, webp…) au
#  format choisi. Corrige juste l'orientation ; ne modifie pas les pixels.
# ======================================================================
def _convertir_vers(source: str, dest: str, fmt: str = "jpg") -> str:
    """Convertit UNE image vers le chemin dest (pas de redimensionnement)."""
    fmt = "png" if str(fmt).lower() == "png" else "jpg"
    img = Image.open(source)
    img = ImageOps.exif_transpose(img)           # redresse selon l'EXIF
    if fmt == "png":
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.save(dest, "PNG")
    else:
        img.convert("RGB").save(dest, "JPEG", quality=95)
    return dest


def convertir_image_format(source: str, dossier_sortie: str, fmt: str = "jpg") -> str:
    """Convertit UNE image vers dossier_sortie au format fmt ('jpg' ou 'png')."""
    ext = ".png" if str(fmt).lower() == "png" else ".jpg"
    base = os.path.splitext(os.path.basename(source))[0] + ext
    return _convertir_vers(source, _dest_libre(dossier_sortie, base), fmt)


def convertir_images_fichiers(fichiers: list, dossier_sortie: str, fmt: str = "jpg",
                              progress=None, doit_arreter=None) -> int:
    """Convertit une liste d'images vers dossier_sortie (en parallèle)."""
    import threading
    imgs = [f for f in fichiers if os.path.splitext(f)[1].lower() in EXT_IMAGES]
    os.makedirs(dossier_sortie, exist_ok=True)
    ext = ".png" if str(fmt).lower() == "png" else ".jpg"
    plans = _planifier(dossier_sortie, imgs, False, ext)
    total = len(plans)
    verrou = threading.Lock()
    fait = [0]

    def _conv(src, dest):
        _convertir_vers(src, dest, fmt)
        if progress:
            with verrou:
                fait[0] += 1
                k = fait[0]
            try:
                progress(f"{k}/{total} — {os.path.basename(src)}")
            except Exception:
                pass

    return _traiter_parallele(plans, _conv, doit_arreter)


def convertir_images_dossier(dossier: str, dossier_sortie: str, fmt: str = "jpg",
                             progress=None, doit_arreter=None) -> int:
    """Convertit toutes les images d'un dossier (et sous-dossiers) vers dossier_sortie."""
    if not os.path.isdir(dossier):
        raise RuntimeError(f"Dossier introuvable : {dossier}")
    fichiers = []
    for racine, _sous, noms in os.walk(dossier):
        for f in sorted(noms):
            if os.path.splitext(f)[1].lower() in EXT_IMAGES:
                fichiers.append(os.path.join(racine, f))
    if not fichiers:
        raise RuntimeError("Aucune image trouvée dans ce dossier.")
    return convertir_images_fichiers(fichiers, dossier_sortie, fmt, progress, doit_arreter)
