"""
Textes de progression affichés dans la fenêtre « Veuillez patienter ».

Exemples :
    Dossier 2/3 — Shooting juin
    Vidéo 1/4 · clip_07.mov — 43 %
"""


def court(nom: str, n: int = 30) -> str:
    """Raccourcit un nom trop long pour la petite fenêtre (… au milieu)."""
    nom = nom or ""
    if len(nom) <= n:
        return nom
    garde = n - 1
    return nom[: garde - garde // 3] + "…" + nom[-(garde // 3):]


def texte(quoi: str, k: int, total: int, dossier_i: int = None, dossier_n: int = None,
          nom_dossier: str = None, fichier: str = None, pct: float = None,
          groupe: str = "Dossier", toujours: bool = False) -> str:
    """Construit le texte : ligne « Dossier i/N » (si plusieurs dossiers) + ligne fichier.

    groupe : mot de la 1re ligne (« Dossier », « Semaine »…) ;
    toujours : afficher la 1re ligne même s'il n'y a qu'un seul groupe."""
    lignes = []
    if dossier_n and (dossier_n > 1 or toujours):
        ligne1 = f"{groupe} {dossier_i}/{dossier_n}"
        if nom_dossier:
            ligne1 += f" — {court(nom_dossier, 26)}"
        lignes.append(ligne1)
    ligne = f"{quoi} {k}/{total}"
    if fichier:
        ligne += f" · {court(fichier, 24)}"
    if pct is not None:
        ligne += f" — {int(pct)} %"
    lignes.append(ligne)
    return "\n".join(lignes)
