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
import threading

import numpy as np
from PIL import Image, ImageFile, ImageOps

# Récupère les JPEG légèrement tronqués au lieu de planter (téléchargements coupés).
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Active la lecture des photos iPhone (.heic/.heif) dans PIL, si dispo.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIC_OK = True
except Exception:
    _HEIC_OK = False

from . import conversion, progression
from .config import UNICITE_FLIP_HORIZONTAL

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def _aplatir_sur_blanc(img: "Image.Image") -> "Image.Image":
    """Passe l'image en RGB en COMPOSANT la transparence sur du blanc.

    Sans ça, un PNG à fond transparent (export Canva, sticker, logo) ressortirait
    avec un rectangle NOIR : convert("RGB") jette le canal alpha et garde les
    valeurs stockées dessous, souvent (0,0,0).
    """
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        fond = Image.new("RGB", img.size, (255, 255, 255))
        fond.paste(img, mask=img.split()[-1])
        return fond
    return img.convert("RGB")


def uniquiser_image(source: str, dest: str | None = None, filtre: bool = False) -> str:
    """Crée une version unique de l'image. dest=None -> remplace l'original.

    filtre=True : applique en plus un filtre photo léger (chaud/froid/vif/doux).
    Retourne le chemin du fichier écrit.
    """
    if dest is None:
        dest = source

    # 1) Ouverture. draft() demande au décodeur JPEG de décoder DIRECTEMENT à une
    #    échelle réduite (il saute des coefficients) : gros gain sur les grosses
    #    photos. On lui donne la taille FINALE visée (calculée sur les dimensions
    #    réelles) : sinon, sur une image PAYSAGE, il ne réduirait rien du tout.
    MAX_L, MAX_H = 1080, 1920
    img = Image.open(source)
    icc = img.info.get("icc_profile")      # profil couleur (photos iPhone P3)
    try:
        w, h = img.size
        r = min(MAX_L / w, MAX_H / h, 1.0)
        img.draft("RGB", (max(1, round(w * r)), max(1, round(h * r))))
    except Exception:
        pass
    # Redresser selon l'orientation EXIF AVANT de retirer l'EXIF, sinon les photos
    # de téléphone sortiraient couchées.
    img = ImageOps.exif_transpose(img)
    # Réduction à la taille utile pour Instagram (max 1080 x 1920) AVANT la
    # conversion RGB : plus rapide, moins de mémoire, sans perte visible.
    w0, h0 = img.size
    if w0 > MAX_L or h0 > MAX_H:
        ratio = min(MAX_L / w0, MAX_H / h0)
        img = img.resize((max(1, round(w0 * ratio)), max(1, round(h0 * ratio))), Image.LANCZOS)
    # Transparence composée sur blanc (sinon fond NOIR sur les PNG/stickers).
    img = _aplatir_sur_blanc(img)

    # 2) Miroir horizontal (optionnel, visible)
    if UNICITE_FLIP_HORIZONTAL:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    # 3) Micro-recadrage (jusqu'à 4 px par bord) : décale les pixels et change la
    #    taille -> hash cassé. Pas de resize retour (gain de temps, invisible).
    #    Marge bornée : une toute petite image ne doit pas être détruite.
    L, H = img.size
    marge = max(0, min(4, (min(L, H) - 1) // 4))
    if marge >= 1 and min(L, H) >= 32:
        g = random.randint(1, marge); h = random.randint(1, marge)
        d = random.randint(1, marge); b = random.randint(1, marge)
        img = img.crop((g, h, L - d, H - b))

    # 4) UNE SEULE passe numpy : saturation + luminosité + contraste + bruit.
    #    (remplace 3 passes PIL + une passe bruit -> beaucoup plus rapide)
    rng = np.random.default_rng()          # instance locale => sûr en multi-thread
    f_sat = random.uniform(0.97, 1.03)
    f_lum = random.uniform(0.97, 1.03)
    f_con = random.uniform(0.97, 1.03)
    arr = np.asarray(img, dtype=np.float32)
    lum = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)   # (H, W)
    moyenne = float(lum.mean())            # pivot du contraste = moyenne réelle
    arr = arr * f_sat + lum[..., None] * (1.0 - f_sat)              # saturation
    if filtre:                                                       # ton froid
        arr[..., 0] *= random.uniform(0.95, 0.98)
        arr[..., 2] *= random.uniform(1.02, 1.05)
    arr = arr * (f_lum * f_con) + (moyenne * (1.0 - f_con) * f_lum)  # lum + contraste
    # On laisse 2 niveaux de marge pour que le bruit ne soit pas avalé par le clip
    # (sinon une image unie ressortirait identique à chaque passage).
    np.clip(arr, 2, 253, out=arr)
    arr += rng.integers(-2, 3, arr.shape, dtype=np.int16)
    np.clip(arr, 0, 255, out=arr)
    np.rint(arr, out=arr)                  # arrondi (sinon biais de -0,5 niveau)
    img = Image.fromarray(arr.astype(np.uint8), "RGB")

    # 5) Ré-encodage JPEG, qualité variable, SANS EXIF (optimize off = plus rapide).
    if os.path.splitext(dest)[1].lower() not in {".jpg", ".jpeg"}:
        dest = os.path.splitext(dest)[0] + ".jpg"
    options = {"quality": random.randint(90, 96)}
    if icc:
        options["icc_profile"] = icc       # garde les couleurs d'origine (P3…)
    img.save(dest, "JPEG", **options)

    # 6) Nouvelle date de fichier (bonus : une métadonnée de plus qui change).
    #    Un échec ici ne doit PAS faire compter le fichier comme raté.
    try:
        decalage = random.randint(0, 30 * 24 * 3600)
        t = os.path.getmtime(dest) - decalage
        os.utime(dest, (t, t))
    except OSError:
        pass

    return dest


def _ffmpeg_exe() -> str:
    """Chemin du binaire ffmpeg (embarqué via imageio-ffmpeg)."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def uniquiser_video(source: str, dest: str | None = None, doit_arreter=None, sur_pct=None) -> str:
    """Crée une version unique d'une vidéo (métadonnées + ré-encodage léger).

    On nettoie toutes les métadonnées et on ré-encode avec de micro-variations
    (luminosité/contraste imperceptibles, qualité variable) : la vidéo reste
    identique à l'œil mais son empreinte (hash) change.
    sur_pct(p) reçoit l'avancement (0–99) ; doit_arreter() arrête net
    (conversion.Annulee est levée et le fichier à moitié écrit est supprimé).
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
    # Lancement surveillé (comme la conversion MP4) : pourcentage + arrêt immédiat.
    try:
        code, err = conversion._executer(cmd, conversion._infos(source)[1], doit_arreter, sur_pct)
    except conversion.Annulee:
        try:
            if os.path.isfile(sortie):
                os.remove(sortie)
        except OSError:
            pass
        raise
    if code != 0:
        raise RuntimeError("Échec ffmpeg : " + err[-300:])

    if sur_place:
        os.replace(sortie, dest)

    # Nouvelle date de fichier (métadonnée du fichier).
    t = os.path.getmtime(dest) - random.randint(0, 30 * 24 * 3600)
    os.utime(dest, (t, t))
    return dest


def uniquiser_dossier(dossier: str, dossier_sortie: str = None,
                      renommer: bool = False, filtre: bool = False) -> dict:
    """Uniquise images ET vidéos d'un dossier. Renvoie {"medias", "echecs"}.

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


def _uniq_lot(images: list, cible_img: str, videos: list, cible_vid: str, renommer: bool,
              filtre: bool, etat: dict, progress=None, doit_arreter=None,
              dossier_i: int = None, dossier_n: int = None, nom: str = None):
    """Uniquise les images (en parallèle) puis les vidéos (une par une) d'un groupe.

    etat = {"ok", "echecs", "fait", "total", "arrete"} est partagé entre les groupes
    pour une barre de progression GLOBALE. progress(texte, fraction) reçoit par ex.
    « Dossier 2/3 — Modèle A » + « Vidéo 1/4 · clip.mov — 43 % ».
    """
    total = max(1, etat["total"])

    def dire(txt, frac):
        if progress:
            try:
                progress(txt, max(0.0, min(1.0, frac)))
            except Exception:
                pass
    if images:
        os.makedirs(cible_img, exist_ok=True)
        debut = etat["fait"]

        def rapport(k, t, fichier=None):
            dire(progression.texte("Image", k, t, dossier_i, dossier_n, nom, fichier), (debut + k) / total)
        rapport(0, len(images))
        n, ech = _traiter_parallele(_planifier(cible_img, images, renommer, ".jpg"),
                                    lambda s_, d_: uniquiser_image(s_, d_, filtre=filtre),
                                    doit_arreter, None, "image(s)", rapport=rapport)
        etat["ok"] += n
        etat["echecs"] += ech
        etat["fait"] += len(images)
    if doit_arreter and doit_arreter():
        etat["arrete"] = True
        return
    if videos:
        os.makedirs(cible_vid, exist_ok=True)
        plans = _planifier(cible_vid, videos, renommer, ".mp4")
        for j, (source, dest) in enumerate(plans, 1):
            if doit_arreter and doit_arreter():
                etat["arrete"] = True
                return
            base = os.path.basename(source)

            def pct(p, j=j, base=base):
                dire(progression.texte("Vidéo", j, len(plans), dossier_i, dossier_n, nom, base, p),
                     (etat["fait"] + p / 100) / total)
            pct(0)
            try:
                uniquiser_video(source, dest, doit_arreter, pct)
                etat["ok"] += 1
            except conversion.Annulee:
                etat["arrete"] = True
                return
            except Exception as e:
                etat["echecs"].append(base)
                sys.stdout.write(f"   [!] {base} ignoré : {e}\n")
            etat["fait"] += 1
    if doit_arreter and doit_arreter():
        etat["arrete"] = True


def uniquiser_fichiers(fichiers: list, dossier_sortie: str = None,
                       renommer: bool = False, filtre: bool = False,
                       progress=None, doit_arreter=None) -> dict:
    """Uniquise une LISTE de fichiers (images/vidéos) choisis.

    Mêmes règles que uniquiser_dossier (sortie en images\\ et videos\\).
    progress(texte, fraction) : avancement ; doit_arreter() : annulation.
    Renvoie {"medias": int, "echecs": [noms], "arrete": bool}.
    """
    images = [f for f in fichiers if os.path.splitext(f)[1].lower() in EXT_IMAGES]
    videos = [f for f in fichiers if os.path.splitext(f)[1].lower() in EXT_VIDEOS]

    # Modification SUR PLACE (pas de dossier de sortie) : séquentiel.
    if not dossier_sortie:
        n, echecs = 0, []
        for source in images:
            if doit_arreter and doit_arreter():
                break
            try:
                uniquiser_image(source, filtre=filtre)
                n += 1
            except Exception as e:
                echecs.append(os.path.basename(source))
                sys.stdout.write(f"   [!] {os.path.basename(source)} ignoré : {e}\n")
        for source in videos:
            if doit_arreter and doit_arreter():
                break
            try:
                uniquiser_video(source, doit_arreter=doit_arreter)
                n += 1
            except conversion.Annulee:
                break
            except Exception as e:
                echecs.append(os.path.basename(source))
                sys.stdout.write(f"   [!] {os.path.basename(source)} ignoré : {e}\n")
        return {"medias": n, "echecs": echecs}

    etat = {"ok": 0, "echecs": [], "fait": 0, "total": len(images) + len(videos), "arrete": False}
    _uniq_lot(images, os.path.join(dossier_sortie, "images"), videos,
              os.path.join(dossier_sortie, "videos"), renommer, filtre, etat, progress, doit_arreter)
    return {"medias": etat["ok"], "echecs": etat["echecs"], "arrete": etat["arrete"]}


def _nb_travailleurs() -> int:
    """Nombre de threads pour traiter les images (1 par cœur, plafonné)."""
    try:
        n = os.cpu_count() or 2
    except Exception:
        n = 2
    return max(1, min(n, 8))


def _planifier(cible: str, sources: list, renommer: bool, ext: str, debut: int = 1) -> list:
    """Attribue À L'AVANCE un chemin de sortie unique à chaque source.

    Fait en séquentiel : garantit zéro collision de noms même quand le
    traitement est ensuite lancé en parallèle.
    """
    plans, pris = [], set()
    for i, src in enumerate(sources, debut):
        base = f"{i}{ext}" if renommer else os.path.splitext(os.path.basename(src))[0] + ext
        stem, e = os.path.splitext(base)
        nom, k = base, 2
        while nom.lower() in pris or os.path.exists(os.path.join(cible, nom)):
            nom = f"{stem}_{k}{e}"
            k += 1
        pris.add(nom.lower())
        plans.append((src, os.path.join(cible, nom)))
    return plans


def _traiter_parallele(plans: list, fn, doit_arreter=None, progress=None,
                       etiquette: str = "fichier(s)", rapport=None):
    """Applique fn(source, dest) à tous les plans, en parallèle sur les cœurs.

    Un fichier en erreur est ignoré (il n'arrête pas le lot) mais il est REMONTÉ.
    progress(texte) est appelé après chaque fichier (compteur protégé par verrou)
    pour que l'utilisateur voie l'avancement en direct.
    rapport(k, total, nom) : variante qui reçoit les compteurs bruts (pour un texte
    et une barre de progression personnalisés).
    Renvoie (nombre_traité, [noms des fichiers en échec]).
    """
    if not plans:
        return 0, []
    total = len(plans)
    verrou = threading.Lock()
    etat = {"fait": 0, "ok": 0}
    echecs = []

    def _un(plan):
        src, dest = plan
        if doit_arreter and doit_arreter():
            return
        ok = True
        try:
            fn(src, dest)
        except Exception as e:
            ok = False
            # une seule écriture -> pas d'entrelacement entre threads
            sys.stdout.write(f"   [!] {os.path.basename(src)} ignoré : {e}\n")
        with verrou:
            etat["fait"] += 1
            k = etat["fait"]
            if ok:
                etat["ok"] += 1
            else:
                echecs.append(os.path.basename(src))
            if progress:
                try:
                    progress(f"{k}/{total} {etiquette}…")
                except Exception:
                    pass
            if rapport:
                try:
                    rapport(k, total, os.path.basename(src))
                except Exception:
                    pass

    travailleurs = _nb_travailleurs()
    if travailleurs == 1 or total == 1:
        for p in plans:
            _un(p)
    else:
        from concurrent.futures import ThreadPoolExecutor
        ex = ThreadPoolExecutor(max_workers=travailleurs)
        try:
            for f in [ex.submit(_un, p) for p in plans]:
                f.result()
        finally:
            # cancel_futures : si on a demandé l'arrêt, on ne traîne pas.
            ex.shutdown(wait=False, cancel_futures=True)
    return etat["ok"], echecs


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

    progress(texte, fraction) : « Dossier 2/3 — nom » + « Image 5/12 · photo.jpg »
        (ou « Vidéo 1/4 · clip.mov — 43 % ») et la progression globale (0 → 1).
    doit_arreter() : si fourni et renvoie True, on s'arrête proprement (même au
        milieu d'une vidéo).
    Retourne {"medias": int, "dossiers": int, "arrete": bool, "echecs": [noms]}.
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
    groupes.sort(key=lambda g: (g[0] != dossier, g[0].lower()))   # dossier principal d'abord
    total_d = len(groupes)
    if total_d == 0:
        raise RuntimeError("Aucune image ni vidéo trouvée dans ce dossier.")

    etat = {"ok": 0, "echecs": [], "fait": 0, "arrete": False,
            "total": sum(len(m) for _, m in groupes)}
    for i, (racine, medias) in enumerate(groupes, 1):
        if doit_arreter and doit_arreter():
            etat["arrete"] = True
            break
        rel = os.path.relpath(racine, dossier)
        nom_aff = os.path.basename(os.path.abspath(dossier)) if rel == "." else rel
        cible = dossier_sortie if rel == "." else os.path.join(dossier_sortie, rel)
        os.makedirs(cible, exist_ok=True)
        images = [f for f in medias if os.path.splitext(f)[1].lower() in EXT_IMAGES]
        videos = [f for f in medias if os.path.splitext(f)[1].lower() in EXT_VIDEOS]
        ok_avant = etat["ok"]
        _uniq_lot(images, cible, videos, cible, renommer, filtre, etat, progress, doit_arreter,
                  i, total_d, nom_aff)
        print(f"[{i}/{total_d}] {nom_aff} : {etat['ok'] - ok_avant} média(s)", flush=True)
        if etat["arrete"]:
            break
    return {"medias": etat["ok"], "dossiers": total_d, "arrete": etat["arrete"],
            "echecs": etat["echecs"]}


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


def _convertir_groupes(groupes: list, dossier_sortie: str, fmt: str, progress=None,
                       doit_arreter=None, renommer: bool = False) -> dict:
    """Convertit des groupes [(nom_dossier, [images])] vers dossier_sortie (à plat).

    progress(texte, fraction) : « Dossier 2/3 — nom » + « Image 5/12 · photo.heic »,
    et la fraction globale (0 → 1) pour la barre de progression."""
    os.makedirs(dossier_sortie, exist_ok=True)
    ext = ".png" if str(fmt).lower() == "png" else ".jpg"
    total = sum(len(imgs) for _, imgs in groupes)
    n_ok, echecs, fait = 0, [], 0
    for i, (nom, imgs) in enumerate(groupes, 1):
        if doit_arreter and doit_arreter():
            break

        def rapport(k, t, fichier=None, i=i, nom=nom, base=fait):
            if progress:
                progress(progression.texte("Image", k, t, i, len(groupes), nom, fichier),
                         (base + k) / max(1, total))
        rapport(0, len(imgs))
        # Noms attribués AVANT le traitement parallèle : aucune collision, y compris
        # avec les groupes précédents (déjà écrits sur le disque).
        # renommer : 1, 2, 3… à la suite d'un groupe à l'autre (la sortie est à plat).
        plans = _planifier(dossier_sortie, imgs, renommer, ext, debut=fait + 1)
        n, ech = _traiter_parallele(plans, lambda s, d: _convertir_vers(s, d, fmt),
                                    doit_arreter, None, "image(s)", rapport=rapport)
        n_ok += n
        echecs += ech
        fait += len(imgs)
    return {"images": n_ok, "echecs": echecs, "dossiers": len(groupes)}


def convertir_images_fichiers(fichiers: list, dossier_sortie: str, fmt: str = "jpg",
                              progress=None, doit_arreter=None, renommer: bool = False) -> dict:
    """Convertit une liste d'images vers dossier_sortie (en parallèle).

    progress(texte, fraction) : avancement. Renvoie {"images": int, "echecs": [noms]}.
    """
    imgs = [f for f in fichiers if os.path.splitext(f)[1].lower() in EXT_IMAGES]
    return _convertir_groupes([("", imgs)], dossier_sortie, fmt, progress, doit_arreter, renommer)


def convertir_images_dossier(dossier: str, dossier_sortie: str, fmt: str = "jpg",
                             progress=None, doit_arreter=None, renommer: bool = False) -> dict:
    """Convertit toutes les images d'un dossier (et sous-dossiers) vers dossier_sortie.

    La progression annonce le sous-dossier en cours (« Dossier 2/3 — nom »)."""
    if not os.path.isdir(dossier):
        raise RuntimeError(f"Dossier introuvable : {dossier}")
    groupes = []
    for racine, _sous, noms in os.walk(dossier):
        imgs = [os.path.join(racine, f) for f in sorted(noms)
                if os.path.splitext(f)[1].lower() in EXT_IMAGES]
        if imgs:
            rel = os.path.relpath(racine, dossier)
            groupes.append((os.path.basename(os.path.abspath(dossier)) if rel == "." else rel, imgs))
    if not groupes:
        raise RuntimeError("Aucune image trouvée dans ce dossier.")
    return _convertir_groupes(groupes, dossier_sortie, fmt, progress, doit_arreter, renommer)
