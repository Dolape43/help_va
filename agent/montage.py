"""
Montage vidéo léger via ffmpeg (embarqué par imageio-ffmpeg) :
  - incruster une caption (texte) EN BAS d'un reel
  - extraire une vignette (1re image) pour l'aperçu dans l'interface

Note : ffmpeg (police classique) ne sait pas dessiner les emojis en
couleur — on les retire du texte incrusté sur la vidéo (ils resteraient
en carrés). Les emojis restent bien sûr dans la légende du post.
"""

import os
import re
import textwrap
import tempfile
import subprocess
import sys

# Emojis / symboles non rendables par une police classique.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\u2190-\u21FF\u2B00-\u2BFF\u2300-\u23FF\uFE0F\u200D\u20E3]",
    flags=re.UNICODE,
)

# Police Windows (présente sur toutes les machines Windows).
POLICE_TTF = r"C:\Windows\Fonts\arialbd.ttf"


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _sans_emoji(texte: str) -> str:
    return _EMOJI.sub("", texte).strip()


def _echapper_chemin(p: str) -> str:
    """Échappe un chemin Windows pour un filtre ffmpeg (: et \\)."""
    return p.replace("\\", "/").replace(":", "\\:")


def _run(cmd):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError("Échec ffmpeg : " + r.stderr.decode("utf-8", "ignore")[-300:])


def incruster_caption(video_source: str, caption: str, dest: str,
                      largeur_ligne: int = 34) -> str:
    """Incruste la caption EN BAS de la vidéo. Retourne le chemin de sortie."""
    texte = _sans_emoji(caption)
    lignes = []
    for para in texte.split("\n"):
        lignes.extend(textwrap.wrap(para, width=largeur_ligne) or [""])
    texte_final = "\n".join(lignes).strip() or " "

    # On passe le texte par un fichier (évite tout souci d'échappement du contenu).
    fd, tmptxt = tempfile.mkstemp(suffix=".txt", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texte_final)

    try:
        vf = (
            f"drawtext=textfile='{_echapper_chemin(tmptxt)}':"
            f"fontfile='{_echapper_chemin(POLICE_TTF)}':"
            "fontcolor=white:fontsize=34:"
            "box=1:boxcolor=black@0.45:boxborderw=10:"
            "line_spacing=6:x=(w-text_w)/2:y=h-text_h-70"
        )
        _run([
            _ffmpeg(), "-y", "-i", video_source, "-vf", vf,
            "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            dest,
        ])
    finally:
        try:
            os.remove(tmptxt)
        except Exception:
            pass
    return dest


def vignette(media_source: str, dest_png: str, taille: int = 240) -> str:
    """Extrait une image d'aperçu (1re frame) d'une vidéo, redimensionnée."""
    _run([
        _ffmpeg(), "-y", "-i", media_source,
        "-vf", f"scale={taille}:-1", "-frames:v", "1", dest_png,
    ])
    return dest_png
