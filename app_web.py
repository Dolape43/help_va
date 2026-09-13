"""
HelpVA — interface web (pywebview).

L'interface est en HTML/CSS/JS (dossier web/), le "cerveau" reste en Python
(modules agent/*). pywebview affiche l'interface dans une fenêtre native et
fait le pont : le JavaScript appelle  window.pywebview.api.<methode>()  qui
exécute la méthode Python correspondante ci-dessous.
"""

import os
import sys
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import webview

from agent import parametres, licence, version


def _chemin(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _licence_js(st: dict) -> dict:
    """Rend le statut de licence sérialisable en JSON (dates -> texte)."""
    exp = st.get("expire_le")
    return {
        "ok": st.get("ok", False),
        "raison": st.get("raison"),
        "type": st.get("type"),
        "expire_le": exp.strftime("%d/%m/%Y") if exp else None,
        "jours_restants": st.get("jours_restants"),
    }


def _abonnement_txt(st: dict) -> str:
    t = st.get("type")
    if t == "vie":
        return "Abonnement : à vie"
    if st.get("expire_le"):
        return f"Abonnement {t or ''} · jusqu'au {st['expire_le'].strftime('%d/%m/%Y')}"
    return ""


class Api:
    """Toutes les méthodes appelables depuis le JavaScript."""

    def __init__(self):
        self.params = parametres.charger()
        self.fenetre = None

    # ---- démarrage / état ----
    def demarrer(self) -> dict:
        self.params = parametres.charger()
        st = licence.verifier()
        return {
            "version": version.VERSION,
            "licence": _licence_js(st),
            "abonnement": _abonnement_txt(st),
            "modele": self.params.get("modele", ""),
            "genre": self.params.get("genre", "feminin"),
            "empreinte": licence.empreinte_machine(),
        }

    def etat(self) -> dict:
        return self.demarrer()

    # ---- licence ----
    def empreinte(self) -> str:
        return licence.empreinte_machine()

    def reverifier_licence(self) -> dict:
        return {"licence": _licence_js(licence.verifier())}

    def activer_licence(self, cle: str) -> dict:
        st = licence.enregistrer_licence(cle or "")
        return {"licence": _licence_js(st), "abonnement": _abonnement_txt(st)}

    # ---- modèle ----
    def definir_modele(self, nom: str, genre: str) -> dict:
        nom = (nom or "").strip()
        for c in '<>:"/\\|?*':
            nom = nom.replace(c, "")
        self.params["modele"] = nom
        self.params["genre"] = genre if genre in ("feminin", "masculin") else "feminin"
        parametres.sauver(self.params)
        return {"modele": self.params["modele"], "genre": self.params["genre"]}


def main():
    api = Api()
    fenetre = webview.create_window(
        f"HelpVA v{version.VERSION}",
        url=_chemin("web/index.html"),
        js_api=api,
        width=1200, height=780,
        min_size=(960, 640),
    )
    api.fenetre = fenetre
    webview.start()


if __name__ == "__main__":
    main()
