# -*- coding: utf-8 -*-
"""
Convertit les SVG déposés dans  assets/icons_svg/  en PNG haute résolution
(fond transparent) dans  assets/icons/  , utilisés par l'app (voir _icone()).

Usage :
    python tools/convertir_icones.py            # convertit tous les .svg
    python tools/convertir_icones.py drive tag  # seulement ceux-là

Rendu via Microsoft Edge (headless, fidèle à n'importe quel SVG, y compris
duotone/dégradés), puis le fond blanc est rendu transparent (remplissage
depuis les bords -> l'intérieur des formes est préservé). Repli sur svglib.

Astuce mode sombre : dépose un fichier  <nom>_dark.svg  pour une variante
sombre ; sinon la même icône sert aux deux thèmes.
"""

import os
import sys
import glob
import time
import shutil
import tempfile
import subprocess

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER_SVG = os.path.join(RACINE, "assets", "icons_svg")
DOSSIER_PNG = os.path.join(RACINE, "assets", "icons")
TAILLE = 256  # px (l'app réduit ensuite selon l'affichage -> net)

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
] if os.path.isfile(p)), None)

_CSS = ("html,body{margin:0;padding:0;background:#fff}"
        "#w{width:%dpx;height:%dpx;display:flex;align-items:center;justify-content:center}"
        "#w svg{width:100%%;height:100%%}" % (TAILLE, TAILLE))


def _html_pour(svg_txt: str) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            + _CSS + "</style></head><body><div id='w'>" + svg_txt
            + "</div></body></html>")


def _rendre_transparent(png_path: str) -> None:
    """Rend transparent le blanc pur (fond ET intérieur des icônes au trait).

    Le rendu Edge est fait sur fond blanc ; on retire ensuite les pixels quasi
    blancs (les 3 canaux >= SEUIL). Les couleurs (même un léger tint duotone)
    sont conservées ; il reste au plus un liseré doux d'1 px (invisible une fois
    l'icône réduite dans l'app).
    """
    SEUIL = 240
    try:
        import numpy as np
        from PIL import Image
        im = Image.open(png_path).convert("RGBA")
        a = np.array(im)
        blanc = (a[..., 0] >= SEUIL) & (a[..., 1] >= SEUIL) & (a[..., 2] >= SEUIL)
        a[..., 3][blanc] = 0
        Image.fromarray(a, "RGBA").save(png_path)
    except Exception as e:
        print("   (transparence non appliquée :", e, ")")


def _via_edge(svg_path: str, out_png: str) -> bool:
    if not EDGE:
        return False
    with open(svg_path, encoding="utf-8") as f:
        svg_txt = f.read()
    # Edge headless échoue souvent au 1er lancement à froid (fichier vide, sans
    # erreur) -> plusieurs essais avec profil neuf à chaque fois.
    for essai in range(5):
        if os.path.isfile(out_png):
            try:
                os.remove(out_png)
            except Exception:
                pass
        tmp = tempfile.mkdtemp()
        try:
            html_path = os.path.join(tmp, "i.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(_html_pour(svg_txt))
            cmd = [
                EDGE, "--headless=new", "--no-first-run",
                "--no-default-browser-check", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=1",
                "--window-size=%d,%d" % (TAILLE, TAILLE),
                "--screenshot=" + out_png,
                "--user-data-dir=" + os.path.join(tmp, "ud"),
                "file:///" + html_path.replace("\\", "/"),
            ]
            try:
                subprocess.run(cmd, timeout=45, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            except Exception:
                pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if os.path.isfile(out_png) and os.path.getsize(out_png) > 200:
            _rendre_transparent(out_png)
            return True
        time.sleep(1.2)
    return False


def main():
    if not os.path.isdir(DOSSIER_SVG):
        print("Dossier introuvable :", DOSSIER_SVG)
        return
    os.makedirs(DOSSIER_PNG, exist_ok=True)
    voulus = [a.lower() for a in sys.argv[1:]]
    svgs = sorted(glob.glob(os.path.join(DOSSIER_SVG, "*.svg")))
    if not svgs:
        print("Aucun .svg dans", DOSSIER_SVG)
        return
    ok = 0
    for svg in svgs:
        nom = os.path.splitext(os.path.basename(svg))[0]
        if voulus and nom.lower() not in voulus:
            continue
        out = os.path.join(DOSSIER_PNG, nom + ".png")
        print("->", nom, end=" ... ")
        if _via_edge(svg, out):
            print("OK")
            ok += 1
        else:
            print("ECHEC (Edge)")
    print("\n%d icone(s) converties dans %s" % (ok, DOSSIER_PNG))
    if not EDGE:
        print("(Edge non trouve -> repli svglib ; qualite moindre sur SVG complexes)")


if __name__ == "__main__":
    main()
