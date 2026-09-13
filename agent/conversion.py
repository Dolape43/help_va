"""
Conversion de vidéos vers .mp4 (via ffmpeg embarqué).

On NE renomme PAS l'extension (ça casse la vidéo) : on fait une vraie
conversion.
  1) Remux rapide (-c copy) : change juste le conteneur -> instantané, sans
     perte. Marche quand les codecs sont déjà compatibles mp4 (cas fréquent
     des .mov iPhone en H.264/HEVC).
  2) Si le remux échoue (codec incompatible) : ré-encodage H.264/AAC ->
     universel, marche à coup sûr.
"""

import os
import re
import subprocess
import sys

EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".wmv", ".flv"}


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _codec_video(source: str) -> str:
    """Retourne le codec vidéo (ex : 'h264', 'hevc', 'prores'…) ou '' si inconnu.

    On lit la sortie de `ffmpeg -i` (ligne « Video: <codec> »)."""
    exe = _ffmpeg_exe()
    r = subprocess.run([exe, "-hide_banner", "-i", os.path.abspath(source)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=_flags())
    err = r.stderr.decode("utf-8", "ignore")
    m = re.search(r"Video:\s*([A-Za-z0-9_]+)", err)
    return m.group(1).lower() if m else ""


def convertir_mp4(source: str, dest: str) -> str:
    """Convertit une vidéo en .mp4 lisible PARTOUT (H.264). Retourne le chemin.

    - déjà en H.264 -> remux rapide (change juste le conteneur, instantané) ;
    - HEVC / H.265 (iPhone) ou autre -> RÉ-ENCODAGE en H.264 (indispensable pour
      Instagram / Windows, qui ne lisent pas le HEVC).
    """
    if os.path.splitext(dest)[1].lower() != ".mp4":
        dest = os.path.splitext(dest)[0] + ".mp4"
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    exe = _ffmpeg_exe()
    src = os.path.abspath(source)
    out = os.path.abspath(dest)

    # 1) Déjà H.264 : remux rapide (instantané, sans perte).
    if _codec_video(source) == "h264":
        cmd = [exe, "-y", "-i", src, "-c", "copy", "-movflags", "+faststart", out]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=_flags())
        if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
            return dest

    # 2) HEVC / autre / remux échoué -> ré-encodage H.264 (yuv420p = compatible
    #    partout, y compris Instagram et Windows Films & TV).
    cmd = [exe, "-y", "-i", src,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=_flags())
    if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise RuntimeError("Échec conversion : "
                           + r.stderr.decode("utf-8", "ignore")[-300:])
    return dest


def convertir_fichiers(fichiers: list, dossier_sortie: str) -> int:
    """Convertit une liste de vidéos en .mp4 H.264 dans dossier_sortie.

    IMPORTANT : même les fichiers DÉJÀ en .mp4 sont vérifiés (un .mp4 peut être
    en HEVC, refusé par Instagram) et ré-encodés en H.264 si besoin.
    Retourne le nombre traité.
    """
    os.makedirs(dossier_sortie, exist_ok=True)
    vids = [f for f in fichiers
            if os.path.splitext(f)[1].lower() in EXT_VIDEOS]
    ok = 0
    echecs = []
    for i, source in enumerate(vids, 1):
        base = os.path.basename(source)
        print(f"[convert] ({i}/{len(vids)}) {base}…", flush=True)
        # Fichier vide (téléchargement raté) -> on ignore et on continue.
        try:
            if os.path.getsize(source) == 0:
                print(f"[convert] ⏭ ignoré (fichier vide) : {base}", flush=True)
                echecs.append(base)
                continue
        except Exception:
            pass
        nom = os.path.splitext(base)[0] + ".mp4"
        dest = os.path.join(dossier_sortie, nom)
        try:
            convertir_mp4(source, dest)   # gère h264 (remux) ET hevc (ré-encode)
            ok += 1
        except Exception as e:
            print(f"[convert] ❌ non converti (corrompu ?) : {base}", flush=True)
            echecs.append(base)
    if echecs:
        print(f"\n⚠️ {len(echecs)} fichier(s) ignorés (vides/corrompus) :", flush=True)
        for b in echecs[:20]:
            print("   -", b, flush=True)
    return ok, echecs


def convertir_dossier(dossier: str, dossier_sortie: str) -> int:
    """Convertit toutes les vidéos d'un dossier en .mp4. Retourne le nombre."""
    if not os.path.isdir(dossier):
        raise RuntimeError(f"Dossier introuvable : {dossier}")
    fichiers = [os.path.join(dossier, f) for f in sorted(os.listdir(dossier))]
    return convertir_fichiers(fichiers, dossier_sortie)
