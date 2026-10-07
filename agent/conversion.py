"""
Conversion de vidéos vers .mp4 (via ffmpeg embarqué).

On NE renomme PAS l'extension (ça casse la vidéo) : on fait une vraie
conversion.
  1) Remux rapide (-c copy) : change juste le conteneur -> instantané, sans
     perte. Marche quand les codecs sont déjà compatibles mp4 (cas fréquent
     des .mov iPhone en H.264/HEVC).
  2) Si le remux échoue (codec incompatible) : ré-encodage H.264/AAC ->
     universel, marche à coup sûr.

ffmpeg est lancé en arrière-plan et SURVEILLÉ : on lit son avancement
(-progress) pour afficher le pourcentage, et on peut l'arrêter à tout moment
(bouton « Annuler l'opération ») — le fichier à moitié écrit est supprimé.
"""

import os
import re
import subprocess
import sys
import threading

from . import progression

EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".wmv", ".flv"}


class Annulee(Exception):
    """L'utilisateur a demandé l'arrêt pendant une conversion."""


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _infos(source: str):
    """(codec vidéo, durée en secondes) lus dans la sortie de `ffmpeg -i`.

    codec : 'h264', 'hevc', 'prores'… ou '' ; durée : float ou None."""
    r = subprocess.run([_ffmpeg_exe(), "-hide_banner", "-i", os.path.abspath(source)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=_flags())
    err = r.stderr.decode("utf-8", "ignore")
    m = re.search(r"Video:\s*([A-Za-z0-9_]+)", err)
    d = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    duree = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else None
    return (m.group(1).lower() if m else ""), duree


def _codec_video(source: str) -> str:
    """Retourne le codec vidéo (ex : 'h264', 'hevc'…) ou '' si inconnu."""
    return _infos(source)[0]


def _executer(cmd: list, duree, doit_arreter=None, sur_pct=None):
    """Lance ffmpeg, suit son avancement, s'arrête net si doit_arreter() devient vrai.

    Renvoie (code_retour, fin_du_stderr). Lève Annulee en cas d'arrêt demandé."""
    cmd = cmd[:1] + ["-hide_banner", "-nostats", "-loglevel", "error", "-progress", "pipe:1"] + cmd[1:]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_flags())
    erreurs, annule = [], threading.Event()

    def _lire_erreurs():                       # vide stderr en parallèle (pas de blocage)
        for ligne in proc.stderr:
            erreurs.append(ligne)
            del erreurs[:-40]

    def _surveiller():                         # arrêt immédiat, même si ffmpeg n'écrit rien
        while proc.poll() is None:
            if doit_arreter and doit_arreter():
                annule.set()
                proc.kill()
                return
            annule.wait(0.2)
    lecteurs = [threading.Thread(target=_lire_erreurs, daemon=True),
                threading.Thread(target=_surveiller, daemon=True)]
    for th in lecteurs:
        th.start()
    dernier = -1
    try:
        for brut in proc.stdout:               # ffmpeg écrit un bloc environ 2 fois par seconde
            ligne = brut.decode("utf-8", "ignore").strip()
            if sur_pct and duree and ligne.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    pct = min(99, max(0, int(ligne.split("=", 1)[1]) / 1e6 / duree * 100))
                except ValueError:
                    continue
                if int(pct) != dernier and not annule.is_set():
                    dernier = int(pct)
                    sur_pct(pct)
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        for th in lecteurs:
            th.join(timeout=2)
    if annule.is_set():
        raise Annulee()
    return proc.returncode, b"".join(erreurs).decode("utf-8", "ignore")


def convertir_mp4(source: str, dest: str, doit_arreter=None, sur_pct=None) -> str:
    """Convertit une vidéo en .mp4 lisible PARTOUT (H.264). Retourne le chemin.

    - déjà en H.264 -> remux rapide (change juste le conteneur, instantané) ;
    - HEVC / H.265 (iPhone) ou autre -> RÉ-ENCODAGE en H.264 (indispensable pour
      Instagram / Windows, qui ne lisent pas le HEVC).
    sur_pct(p) reçoit l'avancement (0–99) ; doit_arreter() permet d'annuler.
    """
    if os.path.splitext(dest)[1].lower() != ".mp4":
        dest = os.path.splitext(dest)[0] + ".mp4"
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    exe = _ffmpeg_exe()
    src = os.path.abspath(source)
    out = os.path.abspath(dest)
    codec, duree = _infos(source)
    try:
        # 1) Déjà H.264 : remux rapide (instantané, sans perte).
        if codec == "h264":
            code, _ = _executer([exe, "-y", "-i", src, "-c", "copy", "-movflags", "+faststart", out],
                                duree, doit_arreter, sur_pct)
            if code == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
                return dest

        # 2) HEVC / autre / remux échoué -> ré-encodage H.264 (yuv420p = compatible
        #    partout, y compris Instagram et Windows Films & TV).
        code, err = _executer([exe, "-y", "-i", src,
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast",
                               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out],
                              duree, doit_arreter, sur_pct)
    except Annulee:
        try:
            if os.path.isfile(out):
                os.remove(out)                 # pas de fichier à moitié converti
        except OSError:
            pass
        raise
    if code != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise RuntimeError("Échec conversion : " + err[-300:])
    return dest


def _videos(liste: list) -> list:
    return [f for f in liste if os.path.splitext(f)[1].lower() in EXT_VIDEOS]


def _convertir_lot(videos: list, cible: str, etat: dict, progress=None, doit_arreter=None,
                   dossier_i=None, dossier_n=None, nom_dossier=None):
    """Convertit une liste de vidéos dans `cible`. Met à jour etat (ok, echecs, fait, arrete).

    etat["total"] = nombre total de vidéos de l'opération (pour la barre globale)."""
    os.makedirs(cible, exist_ok=True)
    n = len(videos)
    for i, source in enumerate(videos, 1):
        if doit_arreter and doit_arreter():
            etat["arrete"] = True
            return
        base = os.path.basename(source)

        def annoncer(pct=None, i=i, base=base):
            if progress:
                frac = (etat["fait"] + (pct or 0) / 100) / max(1, etat["total"])
                try:
                    progress(progression.texte("Vidéo", i, n, dossier_i, dossier_n, nom_dossier,
                                               base, pct), frac)
                except Exception:
                    pass
        annoncer(0)
        print(f"[convert] ({i}/{n}) {base}…", flush=True)
        # Fichier vide (téléchargement raté) -> on ignore et on continue.
        try:
            if os.path.getsize(source) == 0:
                print(f"[convert] ⏭ ignoré (fichier vide) : {base}", flush=True)
                etat["echecs"].append(base)
                etat["fait"] += 1
                continue
        except Exception:
            pass
        dest = os.path.join(cible, os.path.splitext(base)[0] + ".mp4")
        try:
            convertir_mp4(source, dest, doit_arreter, annoncer)   # h264 (remux) ET hevc (ré-encode)
            etat["ok"] += 1
        except Annulee:
            print(f"[convert] ⛔ arrêté pendant : {base}", flush=True)
            etat["arrete"] = True
            return
        except Exception:
            print(f"[convert] ❌ non converti (corrompu ?) : {base}", flush=True)
            etat["echecs"].append(base)
        etat["fait"] += 1


def _bilan(etat: dict) -> dict:
    if etat["echecs"]:
        print(f"\n⚠️ {len(etat['echecs'])} fichier(s) ignorés (vides/corrompus) :", flush=True)
        for b in etat["echecs"][:20]:
            print("   -", b, flush=True)
    return {"medias": etat["ok"], "echecs": etat["echecs"], "arrete": etat["arrete"],
            "dossiers": etat.get("dossiers", 1)}


def convertir_fichiers(fichiers: list, dossier_sortie: str, progress=None, doit_arreter=None) -> dict:
    """Convertit une liste de vidéos en .mp4 H.264 dans dossier_sortie.

    IMPORTANT : même les fichiers DÉJÀ en .mp4 sont vérifiés (un .mp4 peut être
    en HEVC, refusé par Instagram) et ré-encodés en H.264 si besoin.
    progress(texte, fraction) : avancement ; doit_arreter() : annulation.
    Renvoie {"medias", "echecs", "arrete", "dossiers"}.
    """
    vids = _videos(fichiers)
    etat = {"ok": 0, "echecs": [], "fait": 0, "arrete": False, "total": len(vids)}
    _convertir_lot(vids, dossier_sortie, etat, progress, doit_arreter)
    return _bilan(etat)


def convertir_dossier(dossier: str, dossier_sortie: str, progress=None, doit_arreter=None) -> dict:
    """Convertit toutes les vidéos d'un dossier ET de ses sous-dossiers en .mp4.

    L'arborescence est conservée : <dossier>/Modèle A/clip.mov -> <sortie>/Modèle A/clip.mp4.
    """
    if not os.path.isdir(dossier):
        raise RuntimeError(f"Dossier introuvable : {dossier}")
    groupes = []
    for racine, _sous, noms in os.walk(dossier):
        vids = _videos([os.path.join(racine, f) for f in sorted(noms)])
        if vids:
            groupes.append((racine, vids))
    groupes.sort(key=lambda g: (g[0] != dossier, g[0].lower()))   # dossier principal d'abord
    if not groupes:
        raise RuntimeError("Aucune vidéo trouvée dans ce dossier.")
    etat = {"ok": 0, "echecs": [], "fait": 0, "arrete": False,
            "total": sum(len(v) for _, v in groupes), "dossiers": len(groupes)}
    for i, (racine, vids) in enumerate(groupes, 1):
        rel = os.path.relpath(racine, dossier)
        nom = os.path.basename(os.path.abspath(dossier)) if rel == "." else rel
        cible = dossier_sortie if rel == "." else os.path.join(dossier_sortie, rel)
        _convertir_lot(vids, cible, etat, progress, doit_arreter, i, len(groupes), nom)
        if etat["arrete"]:
            break
    return _bilan(etat)
