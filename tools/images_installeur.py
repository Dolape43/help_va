"""
Génère les images de l'assistant d'installation (Inno Setup) à partir du logo.

  installer/assistant-*.png : grand panneau à gauche (pages d'accueil et de fin)
  installer/logo-*.png      : petit logo en haut à droite des autres pages

Plusieurs tailles : Inno Setup choisit la meilleure selon le zoom de l'écran
(tailles recommandées par la doc d'Inno Setup, style « modern »).
Lancer : python tools/images_installeur.py
"""

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(RACINE, "assets", "logo.png")
POLICE = os.path.join(RACINE, "assets", "fonts", "Poppins-SemiBold.ttf")
SORTIE = os.path.join(RACINE, "installer")

PANNEAU = [(202, 386), (336, 643), (430, 824)]     # 100 %, 150 %, 200 %
PETIT = [58, 97, 124]                               # 100 %, 150 %, 200 %


def logo_recadre() -> Image.Image:
    im = Image.open(LOGO).convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def panneau(l: int, h: int) -> Image.Image:
    # Fond sombre en dégradé vertical, aux couleurs du site.
    fond = Image.new("RGB", (l, h))
    d = ImageDraw.Draw(fond)
    haut, bas = (16, 20, 44), (9, 9, 11)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (l, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(haut, bas)))
    fond = fond.convert("RGBA")

    # Halo bleu derrière le logo.
    halo = Image.new("RGBA", (l, h), (0, 0, 0, 0))
    r = int(l * 0.62)
    cx, cy = l // 2, int(h * 0.40)
    ImageDraw.Draw(halo).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(76, 111, 255, 95))
    fond = Image.alpha_composite(fond, halo.filter(ImageFilter.GaussianBlur(l * 0.22)))

    # Logo.
    taille = int(l * 0.46)
    logo = logo_recadre()
    logo = logo.resize((taille, round(taille * logo.height / logo.width)), Image.LANCZOS)
    fond.alpha_composite(logo, (cx - logo.width // 2, cy - logo.height // 2))

    # Nom sous le logo.
    d = ImageDraw.Draw(fond)
    police = ImageFont.truetype(POLICE, int(l * 0.135))
    texte = "HelpVA"
    lt = d.textlength(texte, font=police)
    d.text((cx - lt / 2, cy + logo.height // 2 + int(h * 0.035)), texte, font=police, fill=(244, 244, 245))
    return fond.convert("RGB")


def petit(c: int) -> Image.Image:
    logo = logo_recadre()
    marge = round(c * 0.06)
    cote = c - 2 * marge
    logo.thumbnail((cote, cote), Image.LANCZOS)
    im = Image.new("RGBA", (c, c), (0, 0, 0, 0))            # transparent : clair ET sombre
    im.alpha_composite(logo, ((c - logo.width) // 2, (c - logo.height) // 2))
    return im


if __name__ == "__main__":
    os.makedirs(SORTIE, exist_ok=True)
    for l, h in PANNEAU:
        panneau(l, h).save(os.path.join(SORTIE, f"assistant-{l}.png"), optimize=True)
    for c in PETIT:
        petit(c).save(os.path.join(SORTIE, f"logo-{c}.png"), optimize=True)
    print("Images générées dans", SORTIE)
