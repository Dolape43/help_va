"""
Téléchargement depuis Google Drive (dossier PARTAGÉ « tous avec le lien »).

Utilise l'API Google Drive v3 avec une clé API (lecture publique).
On liste les fichiers du dossier, puis on télécharge les médias en les
triant dans  <sortie>/images/  et  <sortie>/videos/  (prêt pour « Ranger »).
"""

import os
import re
import json
import requests

# Clé API Google Drive du vendeur (lecture publique, restreinte à Drive API).
CLE_API = "AIzaSyB_8mJJMF1jcbstSj9VtT6EuVt5LCpSt5s"
API = "https://www.googleapis.com/drive/v3"

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
# Formats iPhone (HEIC/HEIF) : téléchargés PUIS convertis en JPG (Instagram et
# PIL/OpenCV ne savent pas les gérer tels quels).
EXT_HEIC = {".heic", ".heif"}
# Ensemble des extensions considérées comme « image » à télécharger.
EXT_IMAGES_DL = EXT_IMAGES | EXT_HEIC


def extraire_id(lien: str):
    """Récupère l'ID du dossier depuis un lien Google Drive (ou un ID direct)."""
    lien = (lien or "").strip()
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", lien)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", lien)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", lien):
        return lien
    return None


def lister_fichiers(folder_id: str) -> list:
    """Liste tous les fichiers d'un dossier public (gère la pagination)."""
    fichiers = []
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "key": CLE_API,
            "fields": "nextPageToken, files(id,name,mimeType,createdTime,modifiedTime)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(f"{API}/files", params=params, timeout=30)
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "Erreur API Drive"))
        fichiers.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return fichiers


def url_vignette(file_id: str, taille: int = 220) -> str:
    """URL de la vignette d'un fichier public (marche aussi pour les vidéos)."""
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{taille}"


def telecharger_vignette(file_id: str, dest: str, taille: int = 220) -> bool:
    """Télécharge la petite vignette d'aperçu. Retourne True si OK."""
    try:
        r = requests.get(url_vignette(file_id, taille), timeout=20)
        if r.status_code == 200 and r.content and len(r.content) > 100:
            with open(dest, "wb") as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False


def lister_apercu(lien: str, prendre=("images", "videos"), limite=None,
                  tri: str = "recent") -> list:
    """Liste (filtrée/triée) des médias du dossier, pour l'aperçu.
    tri='recent' (défaut) -> les plus récemment ajoutés d'abord.
    Retourne [{id, nom, est_video}]."""
    prendre = set(prendre)
    fid = extraire_id(lien)
    if not fid:
        raise RuntimeError("Lien Google Drive invalide (attendu un lien de DOSSIER partagé).")
    fichiers = lister_fichiers(fid)
    if not fichiers:
        raise RuntimeError("Aucun fichier trouvé. Vérifie que le dossier est PARTAGÉ.")

    def voulu(nom):
        ext = os.path.splitext(nom)[1].lower()
        if ext in EXT_IMAGES_DL:
            return "images" in prendre
        if ext in EXT_VIDEOS:
            return "videos" in prendre
        return False

    medias = _trier([f for f in fichiers if voulu(f["name"])], tri)
    if limite and limite > 0:
        medias = medias[:limite]
    return [{"id": f["id"], "nom": f["name"],
             "est_video": os.path.splitext(f["name"])[1].lower() in EXT_VIDEOS}
            for f in medias]


class BlocageGoogleError(Exception):
    """Google bloque TEMPORAIREMENT les téléchargements depuis cette IP/ce
    réseau (« trop de requêtes automatisées »). Rien à corriger dans le code :
    il faut changer de réseau (partage 4G / VPN) ou attendre."""
    pass


def _est_blocage_google(texte: str) -> bool:
    """Détecte la page anti-robot de Google (blocage IP temporaire)."""
    t = (texte or "").lower()
    return ("automated queries" in t or "sending automated" in t
            or "we're sorry" in t or "we&#39;re sorry" in t)


def _ecrire_flux(r, dest: str):
    """Écrit un flux HTTP (streaming) dans un fichier."""
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 20):   # 1 Mo
            if chunk:
                f.write(chunk)


def _telecharger_api(file_id: str, dest: str) -> bool:
    """Télécharge le contenu via l'API Drive (alt=media). True si réussi.

    Lève BlocageGoogleError si Google bloque le réseau (anti-robot).
    """
    url = f"{API}/files/{file_id}"
    params = {"alt": "media", "key": CLE_API, "supportsAllDrives": "true"}
    try:
        with requests.get(url, params=params, stream=True, timeout=300) as r:
            if r.status_code == 200:
                _ecrire_flux(r, dest)
            elif r.status_code == 403:
                corps = ""
                try:
                    corps = r.text[:2000]
                except Exception:
                    pass
                if _est_blocage_google(corps):
                    raise BlocageGoogleError()
                # Sinon : gros fichier signalé « abusif » -> on acquitte.
                params["acknowledgeAbuse"] = "true"
                with requests.get(url, params=params, stream=True, timeout=300) as r2:
                    if r2.status_code != 200:
                        if _est_blocage_google(getattr(r2, "text", "")[:2000]):
                            raise BlocageGoogleError()
                        return False
                    _ecrire_flux(r2, dest)
            else:
                return False
    except BlocageGoogleError:
        raise
    except Exception:
        return False
    return os.path.isfile(dest) and os.path.getsize(dest) > 0


def telecharger_fichier(file_id: str, dest: str):
    """Télécharge un fichier Drive vers `dest`.

    1) API Drive (alt=media) : fiable, pas de blocage anti-abus de gdown.
    2) Repli gdown : seulement si l'API échoue (cas rares).
    """
    if _telecharger_api(file_id, dest):
        return
    # Repli gdown.
    import gdown
    res = gdown.download(id=file_id, output=dest, quiet=True)
    if not res or not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError("téléchargement échoué (fichier vide ou refusé)")


def telecharger_et_convertir_heic(file_id: str, dest_jpg: str):
    """Télécharge un HEIC/HEIF puis le convertit en JPG (utilisable partout).

    Instagram et PIL ne gèrent pas le HEIC : on le convertit à la volée
    pour que le reste de l'app (métadonnées, rangement) fonctionne.
    """
    tmp = dest_jpg + ".heic.tmp"
    telecharger_fichier(file_id, tmp)
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()      # active la lecture HEIC dans PIL
        from PIL import Image, ImageOps
        img = Image.open(tmp)
        img = ImageOps.exif_transpose(img)      # respecte l'orientation iPhone
        img.convert("RGB").save(dest_jpg, "JPEG", quality=95)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    if not os.path.isfile(dest_jpg) or os.path.getsize(dest_jpg) == 0:
        raise RuntimeError("conversion HEIC→JPG échouée")


def _trier(medias: list, tri: str) -> list:
    """Trie les médias. tri='recent' -> les plus récemment ajoutés d'abord ;
    tri='nom' -> ordre alphabétique."""
    if tri == "recent":
        # createdTime est une date ISO (2025-09-22T...), le tri texte suffit.
        return sorted(medias,
                      key=lambda f: f.get("createdTime") or f.get("modifiedTime") or "",
                      reverse=True)
    return sorted(medias, key=lambda f: f["name"].lower())


def _nom_nettoye(nom: str) -> str:
    """Nom de fichier sans caractères interdits."""
    base = os.path.basename(nom or "media")
    for c in '<>:"/\\|?*\n\r\t':
        base = base.replace(c, "_")
    return base


def _nom_sur(nom: str, dossier: str) -> str:
    """Nettoie le nom de fichier et évite les collisions dans `dossier`."""
    base = _nom_nettoye(nom)
    racine, ext = os.path.splitext(base)
    candidat = base
    i = 2
    while os.path.exists(os.path.join(dossier, candidat)):
        candidat = f"{racine}_{i}{ext}"
        i += 1
    return candidat


def telecharger_dossier(lien: str, dossier_sortie: str, prendre=("images", "videos"),
                        limite=None, progress=None, renommer: bool = False,
                        tri: str = "recent", doit_arreter=None) -> tuple:
    """Télécharge les médias d'un dossier Drive partagé.

    prendre : quels types récupérer -> {"images"} , {"videos"} , ou les deux.
    limite  : nombre max de médias à télécharger (None = tout).
    tri='recent' (défaut) : prend les plus récemment ajoutés ; 'nom' : alphabétique.
    renommer=False (défaut) : garde les NOMS D'ORIGINE (nettoyés).
    renommer=True  : renomme 1, 2, 3… par type.
    Trie en <sortie>/images/ et <sortie>/videos/.
    Retourne (nb_images, nb_videos, nb_erreurs).
    `progress(i, total, nom)` : appelé à chaque fichier (optionnel).
    """
    prendre = set(prendre)
    fid = extraire_id(lien)
    if not fid:
        raise RuntimeError("Lien Google Drive invalide (attendu un lien de DOSSIER partagé).")

    fichiers = lister_fichiers(fid)
    if not fichiers:
        raise RuntimeError(
            "Aucun fichier trouvé. Vérifie que le dossier est bien PARTAGÉ "
            "(« Tous les utilisateurs disposant du lien »).")

    def voulu(nom):
        ext = os.path.splitext(nom)[1].lower()
        if ext in EXT_IMAGES_DL:
            return "images" in prendre
        if ext in EXT_VIDEOS:
            return "videos" in prendre
        return False

    medias = [f for f in fichiers if voulu(f["name"])]
    if not medias:
        raise RuntimeError("Aucun média correspondant à votre choix dans ce dossier.")
    medias = _trier(medias, tri)   # 'recent' (défaut) ou 'nom'

    # Les dossiers images/ et videos/ sont créés À LA DEMANDE (seulement si un
    # média de ce type est réellement téléchargé) -> pas de dossier vide.
    d_img = os.path.join(dossier_sortie, "images")
    d_vid = os.path.join(dossier_sortie, "videos")
    os.makedirs(dossier_sortie, exist_ok=True)

    # Mémoire des médias déjà téléchargés (par ID Drive) : on ne reprend JAMAIS
    # deux fois le même, même sur plusieurs téléchargements successifs — ex :
    # « 50 puis 50 » récupère les 50 SUIVANTS, pas à nouveau les mêmes.
    manifeste = os.path.join(dossier_sortie, "_deja_telecharges.json")
    deja = set()
    if os.path.isfile(manifeste):
        try:
            with open(manifeste, encoding="utf-8") as fp:
                deja = set(json.load(fp))
        except Exception:
            deja = set()

    # Renommage 1,2,3 : on continue APRÈS les fichiers déjà présents.
    compteur_img = len(os.listdir(d_img)) if renommer and os.path.isdir(d_img) else 0
    compteur_vid = len(os.listdir(d_vid)) if renommer and os.path.isdir(d_vid) else 0

    ni = nv = err = saute = 0
    fait = 0
    total = limite if (limite and limite > 0) else len(medias)
    for f in medias:
        if doit_arreter and doit_arreter():
            print("  [drive] arrêt demandé — téléchargement interrompu.", flush=True)
            break
        if limite and limite > 0 and fait >= limite:
            break
        ext = os.path.splitext(f["name"])[1].lower()
        est_video = ext in EXT_VIDEOS
        est_heic = ext in EXT_HEIC
        d_cible = d_vid if est_video else d_img
        # Un HEIC finit en .jpg sur le disque (après conversion).
        ext_finale = ".jpg" if est_heic else ext
        nom_disque = os.path.splitext(_nom_nettoye(f["name"]))[0] + ext_finale
        # Déjà pris ? (par ID, ou fichier de même nom déjà là si pas de renommage)
        deja_pris = f["id"] in deja
        if not deja_pris and not renommer:
            deja_pris = os.path.exists(os.path.join(d_cible, nom_disque))
        if deja_pris:
            deja.add(f["id"])
            saute += 1
            continue

        os.makedirs(d_cible, exist_ok=True)   # crée images/ ou videos/ à la demande
        if renommer:
            if est_video:
                compteur_vid += 1
                nom = f"{compteur_vid}{ext_finale}"
            else:
                compteur_img += 1
                nom = f"{compteur_img}{ext_finale}"
        else:
            nom = _nom_sur(nom_disque, d_cible)   # garde le nom d'origine (nettoyé)
        dest = os.path.join(d_cible, nom)
        bloque = False
        try:
            if est_heic:
                telecharger_et_convertir_heic(f["id"], dest)
            else:
                telecharger_fichier(f["id"], dest)
            deja.add(f["id"])
            fait += 1
            if est_video:
                nv += 1
            else:
                ni += 1
        except BlocageGoogleError:
            bloque = True
        except Exception as e:
            err += 1
            print(f"  [drive] échec {f['name']} : {e}", flush=True)
        if bloque:
            # Google bloque le réseau : inutile de continuer, tout échouera.
            try:
                with open(manifeste, "w", encoding="utf-8") as fp:
                    json.dump(sorted(deja), fp)
            except Exception:
                pass
            raise BlocageGoogleError()
        if progress:
            progress(fait, total, nom)

    # On mémorise ce qui a été téléchargé (pour les prochains lots).
    try:
        with open(manifeste, "w", encoding="utf-8") as fp:
            json.dump(sorted(deja), fp)
    except Exception:
        pass
    if saute:
        print(f"  [drive] {saute} média(s) déjà téléchargé(s) ignoré(s).", flush=True)
    return ni, nv, err
