"""
HelpVA — interface CustomTkinter (légère, fluide, design moderne).

Le "cerveau" reste dans agent/* ; ce fichier ne fait que l'interface.
Sidebar (Accueil / Paramètres) + cartes.
"""

import os
import sys
import queue
import shutil
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from agent import parametres, licence, version
from agent import ranger as rangement
from agent import unicite, calendrier, conversion
from agent import drive, raccourci

# Re-contrôle de l'abonnement quand l'app reste ouverte (réglable pour tests).
# Toutes les 1 h : vérifie en ligne l'état de la licence (résiliation/expiration).
try:
    INTERVALLE_VERIF_MS = int(os.environ.get("HELPVA_VERIF_MS", str(60 * 60 * 1000)))
except ValueError:
    INTERVALLE_VERIF_MS = 60 * 60 * 1000
RETRY_VERIF_MS = 5 * 60 * 1000
MAX_ECHECS_VERIF = 3


class FluxVersLog:
    """Redirige les print() vers le journal (via une file d'attente)."""
    def __init__(self, file):
        self.file = file

    def write(self, texte):
        if texte:
            self.file.put(texte)

    def flush(self):
        pass

# ---------------------------------------------------------------- couleurs
# Couleurs (clair, sombre) — CustomTkinter bascule selon le mode d'apparence.
BG = ("#F5F6FB", "#0E0F17")
SIDEBAR = ("#FFFFFF", "#15161F")
CARD = ("#FFFFFF", "#191A24")
ACCENT = ("#6C5CE7", "#8072FF")
ACCENT_HOVER = ("#5B4FE3", "#6F63F5")
ACCENT_SOFT = ("#ECEAFB", "#26243D")
ACCENT_SOFTER = ("#F4F2FE", "#1E1D2E")
TEXT = ("#22243A", "#ECEDF6")
MUTED = ("#8A90A2", "#9EA1B8")
GREEN = ("#16A34A", "#4FD08A")
ORANGE = ("#D97706", "#F5A524")
BORDER = ("#E7E8F2", "#2A2C3C")
from agent import polices as _polices
POLICE = "Poppins" if _polices.charger_poppins() else "Segoe UI"

def chemin_ressource(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def icones_nettes(fenetre):
    """Pose l'icône de la fenêtre via Windows, à la taille EXACTE de l'écran.

    Tk fabrique lui-même une icône floue (visible dans la barre des tâches et la
    barre de titre). Ici Windows charge directement la bonne taille depuis
    logo.ico : 16 px (titre) et 32 px (barre des tâches, Alt+Tab), x zoom écran.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.LoadImageW.restype = ctypes.c_void_p
        u32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_size_t, ctypes.c_void_p]
        u32.GetParent.restype = ctypes.c_void_p
        u32.GetParent.argtypes = [ctypes.c_void_p]
        hwnd = u32.GetParent(fenetre.winfo_id()) or fenetre.winfo_id()
        try:
            dpi = u32.GetDpiForWindow(ctypes.c_void_p(hwnd)) or 96
        except Exception:
            dpi = 96
        ico = chemin_ressource("assets/logo.ico")
        IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x0080
        icones = []
        for quelle, base in ((0, 16), (1, 32)):          # 0 = petite, 1 = grande
            t = round(base * dpi / 96)
            h = u32.LoadImageW(None, ico, IMAGE_ICON, t, t, LR_LOADFROMFILE)
            if h:
                u32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON, quelle, ctypes.c_void_p(h))
                icones.append(h)
        fenetre._icones_win = icones      # garde les icônes en vie
    except Exception:
        pass


def _abonnement_txt(st: dict) -> str:
    return {"vie": "Abonnement à vie",
            "mois": "Abonnement mensuel",
            "an": "Abonnement annuel",
            "essai": "Essai"}.get(st.get("type"), "")


_JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]


def _date_fr(d) -> str:
    """Date lisible en français : 'Lundi 12 octobre 2027'."""
    return f"{_JOURS_FR[d.weekday()].capitalize()} {d.day} {_MOIS_FR[d.month - 1]} {d.year}"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.params = parametres.charger()
        ctk.set_appearance_mode(self.params.get("theme", "light"))
        self.title(f"HelpVA v{version.VERSION}")
        self.geometry("1160x760")
        self.minsize(980, 640)
        self.configure(fg_color=BG)

        # Anti-« app gelée » : si une fenêtre modale (grab) reste cachée derrière
        # la principale, l'app semble bloquée (barre des tâches/Alt+Tab sans
        # effet). Quand la fenêtre principale reçoit le focus, on ramène la
        # modale devant.
        self.bind("<FocusIn>", self._ramener_modale, add="+")

        self.statut = {"ok": False, "raison": "pas_active"}
        self.page = "accueil"

        # Infra jobs : journal + threads + popups.
        self.file_log = queue.Queue()
        self.log = None
        self.occupe = False
        self._loading = None
        self._annule_tache = False     # drapeau : annulation d'une tâche en cours
        self.sources_ranger = {}       # {type de post: dossier source}
        self._onglet_ranger = None
        self._ranger_etape2 = None
        self.ranger_aleatoire = True
        self.dossier_uniq_src = None
        self.fichiers_uniq_src = None
        self.dossier_convert_src = None
        self.fichiers_convert_src = None
        self.dossier_imgconv_src = None
        self.fichiers_imgconv_src = None
        self._timer_verif = None
        self._echecs_verif = 0
        self._bandeau_hl = None   # bandeau discret « hors-ligne »
        sys.stdout = FluxVersLog(self.file_log)
        sys.stderr = FluxVersLog(self.file_log)
        self.after(120, self._pomper_log)

        try:
            self.iconbitmap(chemin_ressource("assets/logo.ico"))
        except Exception:
            pass
        # Remplace l'icône floue fabriquée par Tk par une icône nette (Windows).
        self.after(250, lambda: icones_nettes(self))
        # Fermeture de la fenêtre -> on demande l'arrêt des traitements en cours.
        self.protocol("WM_DELETE_WINDOW", self._fermer_app)

        self._router_licence()

    def _dossier_sortie_defaut(self) -> str:
        bureau = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(bureau):
            bureau = os.path.expanduser("~")
        return os.path.join(bureau, "HelpVA")

    def dossier_sortie(self) -> str:
        """Dossier où les modules enregistrent. Personnalisable (Paramètres),
        par défaut Bureau\\HelpVA."""
        d = self.params.get("dossier_sortie", "").strip() or self._dossier_sortie_defaut()
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            d = self._dossier_sortie_defaut()
            os.makedirs(d, exist_ok=True)
        return d

    def _ouvrir_dossier_sortie(self):
        try:
            os.startfile(self.dossier_sortie())   # ouvre l'explorateur (Windows)
        except Exception as e:
            self._notifier("Dossier de sortie", str(e), erreur=True)

    def _changer_dossier_sortie(self):
        choix = filedialog.askdirectory(title="Choisir le dossier de sortie")
        if not choix:
            return
        self.params["dossier_sortie"] = choix
        parametres.sauver(self.params)
        self._aller("parametres")   # rafraîchit l'affichage

    def _reinit_dossier_sortie(self):
        self.params["dossier_sortie"] = ""
        parametres.sauver(self.params)
        self._aller("parametres")

    # ----------------------------------------------------------- utilitaires
    def _vider(self, widget=None):
        for w in (widget or self).winfo_children():
            w.destroy()

    def _cliquable(self, carte, cmd):
        """Rend une carte (et ses enfants) cliquable + effet survol."""
        def survol(actif):
            carte.configure(border_color=ACCENT if actif else BORDER,
                            fg_color=("#FBFAFF", "#20223A") if actif else CARD)

        def on_leave(_):
            x, y = carte.winfo_pointerxy()
            rx, ry = carte.winfo_rootx(), carte.winfo_rooty()
            if rx <= x <= rx + carte.winfo_width() and ry <= y <= ry + carte.winfo_height():
                return
            survol(False)

        def lier(w):
            w.bind("<Button-1>", lambda e: cmd())
            w.bind("<Enter>", lambda e: survol(True))
            w.bind("<Leave>", on_leave)
            for c in w.winfo_children():
                lier(c)
        lier(carte)

    def _icone(self, nom, size=22):
        """Icône PNG embarquée (assets/icons) ; repli sur dessin PIL.

        Supporte une variante mode sombre optionnelle : si `assets/icons/<nom>_dark.png`
        existe, il est utilisé en thème sombre (sinon la même image sert aux deux).
        """
        try:
            from PIL import Image
            p = chemin_ressource(os.path.join("assets", "icons", f"{nom}.png"))
            if os.path.isfile(p):
                clair = Image.open(p)
                pd = chemin_ressource(os.path.join("assets", "icons", f"{nom}_dark.png"))
                sombre = Image.open(pd) if os.path.isfile(pd) else clair
                return ctk.CTkImage(light_image=clair, dark_image=sombre, size=(size, size))
        except Exception:
            pass
        try:
            from PIL import Image, ImageDraw
            import math
            S = size * 4
            img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            col = (108, 92, 231, 255)
            if nom == "grid":
                g = S * 0.12
                w = (S - 3 * g) / 2
                for rr, cc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
                    x = g + cc * (w + g)
                    y = g + rr * (w + g)
                    d.rounded_rectangle([x, y, x + w, y + w], radius=w * 0.3, fill=col)
            elif nom == "gear":
                cx = cy = S / 2
                ro, ri, teeth = S * 0.46, S * 0.30, 8
                pts = []
                for i in range(teeth * 2):
                    ang = i * math.pi / teeth - math.pi / 2
                    r = ro if i % 2 == 0 else ri
                    pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
                lw = max(2, int(S * 0.06))
                d.line(pts + [pts[0]], fill=col, width=lw, joint="curve")
                rc = S * 0.15
                d.ellipse([cx - rc, cy - rc, cx + rc, cy + rc], outline=col, width=lw)
            else:
                lw = max(2, int(S * 0.065))
                if nom == "folder":
                    d.line([(0.16 * S, 0.42 * S), (0.16 * S, 0.34 * S), (0.42 * S, 0.34 * S),
                            (0.50 * S, 0.42 * S)], fill=col, width=lw, joint="curve")
                    d.rounded_rectangle([0.16 * S, 0.42 * S, 0.84 * S, 0.78 * S],
                                        radius=0.07 * S, outline=col, width=lw)
                elif nom == "tag":
                    pts = [(0.22 * S, 0.30 * S), (0.58 * S, 0.30 * S), (0.80 * S, 0.52 * S),
                           (0.58 * S, 0.74 * S), (0.22 * S, 0.74 * S)]
                    d.line(pts + [pts[0]], fill=col, width=lw, joint="curve")
                    r = 0.05 * S
                    d.ellipse([0.33 * S - r, 0.52 * S - r, 0.33 * S + r, 0.52 * S + r],
                              outline=col, width=lw)
                elif nom == "list":
                    for yy in (0.34, 0.52, 0.70):
                        rr = 0.045 * S
                        d.ellipse([0.20 * S - rr, yy * S - rr, 0.20 * S + rr, yy * S + rr], fill=col)
                        d.line([(0.34 * S, yy * S), (0.82 * S, yy * S)], fill=col, width=lw)
                elif nom == "send":
                    pts = [(0.20 * S, 0.28 * S), (0.82 * S, 0.50 * S), (0.20 * S, 0.72 * S),
                           (0.36 * S, 0.50 * S)]
                    d.line(pts + [pts[0]], fill=col, width=lw, joint="curve")
                elif nom == "clock":
                    d.ellipse([0.16 * S, 0.16 * S, 0.84 * S, 0.84 * S], outline=col, width=lw)
                    d.line([(0.5 * S, 0.5 * S), (0.5 * S, 0.30 * S)], fill=col, width=lw)
                    d.line([(0.5 * S, 0.5 * S), (0.66 * S, 0.56 * S)], fill=col, width=lw)
                elif nom == "bulb":
                    d.ellipse([0.28 * S, 0.18 * S, 0.72 * S, 0.62 * S], outline=col, width=lw)
                    d.line([(0.42 * S, 0.64 * S), (0.58 * S, 0.64 * S)], fill=col, width=lw)
                    d.line([(0.44 * S, 0.72 * S), (0.56 * S, 0.72 * S)], fill=col, width=lw)
                elif nom == "drive":   # téléchargement : flèche bas + bac
                    d.line([(0.5 * S, 0.22 * S), (0.5 * S, 0.58 * S)], fill=col, width=lw)
                    d.line([(0.34 * S, 0.44 * S), (0.5 * S, 0.60 * S), (0.66 * S, 0.44 * S)],
                           fill=col, width=lw, joint="curve")
                    d.line([(0.26 * S, 0.74 * S), (0.74 * S, 0.74 * S)], fill=col, width=lw)
                elif nom == "sun":
                    d.ellipse([0.36 * S, 0.36 * S, 0.64 * S, 0.64 * S], outline=col, width=lw)
                    for i in range(8):
                        a = i * math.pi / 4
                        d.line([(0.5 * S + 0.40 * S * math.cos(a), 0.5 * S + 0.40 * S * math.sin(a)),
                                (0.5 * S + 0.50 * S * math.cos(a), 0.5 * S + 0.50 * S * math.sin(a))],
                               fill=col, width=lw)
                elif nom == "moon":
                    d.ellipse([0.26 * S, 0.22 * S, 0.74 * S, 0.70 * S], fill=col)
                    d.ellipse([0.40 * S, 0.14 * S, 0.86 * S, 0.62 * S], fill=(0, 0, 0, 0))
                else:
                    return None
            img = img.resize((size, size), Image.LANCZOS)
            return ctk.CTkImage(img, size=(size, size))
        except Exception:
            return None

    def _badge(self, parent, nom, taille=52):
        b = ctk.CTkFrame(parent, fg_color=ACCENT_SOFT, corner_radius=taille // 2,
                         width=taille, height=taille)
        b.pack_propagate(False)
        img = self._icone(nom, int(taille * 0.58))
        if img is not None:
            lbl = ctk.CTkLabel(b, image=img, text="")
            self._badge_imgs = getattr(self, "_badge_imgs", [])
            self._badge_imgs.append(img)
        else:
            fallback = {"folder": "🗂", "tag": "🏷", "list": "📝", "send": "🚀",
                        "clock": "⏰", "bulb": "💡", "convertir": "🎬"}
            txt = fallback.get(nom, nom if len(nom) <= 2 else "•")
            lbl = ctk.CTkLabel(b, text=txt, font=(POLICE, int(taille * 0.42)),
                               text_color=ACCENT_HOVER)
        lbl.place(relx=0.5, rely=0.5, anchor="center")
        return b

    # ----------------------------------------------------------- routage licence
    def _router_licence(self):
        self.statut = licence.verifier()
        self._vider()
        if self.statut["ok"]:
            self._apres_licence()
        elif self.statut["raison"] == "pas_internet":
            self._ecran_internet()
        else:
            self._ecran_activation()

    def _apres_licence(self):
        # On ne montre l'écran « Bienvenue » qu'AU TOUT PREMIER lancement.
        # Ensuite (déjà démarré une fois) -> Accueil direct.
        if self.params.get("deja_demarre"):
            self._construire_app()
        else:
            self._ecran_bienvenue()

    def _ecran_bienvenue(self):
        c = self._carte_centre()
        try:
            from PIL import Image
            img = ctk.CTkImage(Image.open(chemin_ressource("assets/logo.png")), size=(92, 92))
            ctk.CTkLabel(c, image=img, text="").pack(pady=(0, 12))
            self._logo_bienv = img
        except Exception:
            pass
        ctk.CTkLabel(c, text="Bienvenue sur HelpVA", font=(POLICE, 26, "bold"),
                     text_color=TEXT).pack(pady=(0, 6))
        ctk.CTkLabel(c, text="Votre assistant pour préparer\nvos contenus Instagram.",
                     font=(POLICE, 15), text_color=MUTED, justify="center").pack(pady=(0, 24))
        ctk.CTkButton(c, text="Commencer", command=self._commencer, height=48, width=220,
                      fg_color=ACCENT_HOVER, hover_color="#4A3FCC", corner_radius=12,
                      font=(POLICE, 16, "bold")).pack()

    def _commencer(self):
        # Mémorise que l'utilisateur a déjà démarré -> plus jamais l'écran Bienvenue.
        self.params["deja_demarre"] = True
        parametres.sauver(self.params)
        self._construire_app()

    def _carte_centre(self):
        wrap = ctk.CTkFrame(self, fg_color=BG)
        wrap.pack(fill="both", expand=True)
        carte = ctk.CTkFrame(wrap, fg_color=CARD, corner_radius=22, border_width=1,
                             border_color=BORDER, width=480)
        carte.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(carte, fg_color="transparent")
        inner.pack(padx=40, pady=36)
        return inner

    def _ecran_internet(self):
        c = self._carte_centre()
        ctk.CTkLabel(c, text="Connexion internet requise",
                     font=(POLICE, 22, "bold"), text_color=TEXT).pack(pady=(0, 8))
        ctk.CTkLabel(c, text="Veuillez vous connecter à internet, puis réessayez.",
                     font=(POLICE, 13), text_color=MUTED, justify="center").pack(pady=(0, 20))
        ctk.CTkButton(c, text="Réessayer", command=self._router_licence,
                      fg_color=ACCENT_HOVER, hover_color="#4A3FCC", height=42,
                      corner_radius=12, font=(POLICE, 14, "bold")).pack()
        # Au démarrage du PC, internet met parfois quelques secondes -> on
        # réessaie tout seul, sans que l'utilisateur ait à cliquer.
        self.after(20000, self._router_licence)

    def _ecran_activation(self):
        raison = self.statut.get("raison", "pas_active")
        titre = "Activer HelpVA"
        sous = "Entrez le code d'activation fourni par le vendeur."
        if raison == "expire":
            titre = "Abonnement expiré"
            sous = "Votre abonnement a expiré.\nEntrez un nouveau code pour le renouveler."
        elif raison == "revoquee":
            titre = "Licence résiliée"
            sous = "Cette licence a été résiliée.\nEntrez un nouveau code fourni par le vendeur."
        elif raison == "suspendu":
            titre = "Licence suspendue"
            sous = "Cette licence est suspendue.\nContactez le vendeur."

        c = self._carte_centre()
        ctk.CTkLabel(c, text=titre, font=(POLICE, 22, "bold"), text_color=TEXT).pack(pady=(0, 6))
        ctk.CTkLabel(c, text=sous, font=(POLICE, 13), text_color=MUTED,
                     justify="center").pack(pady=(0, 22))

        ctk.CTkLabel(c, text="Code d'activation", font=(POLICE, 12, "bold"),
                     text_color=MUTED).pack()
        champ_code = ctk.CTkEntry(c, height=48, font=("Consolas", 16), justify="center",
                                  placeholder_text="HELP-XXXX-XXXX-XXXX")
        champ_code.pack(fill="x", pady=(8, 0))

        def activer_code():
            code = champ_code.get().strip()
            if not code:
                msg.configure(text="Entrez votre code d'activation.", text_color="#E5484D")
                return
            msg.configure(text="Activation en cours…", text_color=MUTED)
            self.update_idletasks()
            lic, info = licence.activer_par_code(code)
            if not lic:
                msg.configure(text=info, text_color="#E5484D")
                return
            st = licence.enregistrer_licence(lic)
            self.statut = st
            if st.get("ok"):
                self.params = parametres.charger()
                self._vider()
                self._apres_licence()
            else:
                msg.configure(text="Code accepté mais activation refusée. Réessayez.",
                              text_color="#E5484D")

        champ_code.bind("<Return>", lambda e: activer_code())
        ctk.CTkButton(c, text="Activer HelpVA", command=activer_code, height=46,
                      fg_color=ACCENT_HOVER, hover_color="#4A3FCC", corner_radius=12,
                      font=(POLICE, 15, "bold")).pack(fill="x", pady=(12, 0))
        msg = ctk.CTkLabel(c, text="", font=(POLICE, 12), text_color="#E5484D")
        msg.pack(pady=(10, 0))

        # Licence déjà présente mais bloquée (expirée/suspendue/résiliée) :
        # après réactivation côté vendeur, on re-vérifie sans nouveau code.
        if raison != "pas_active":
            ctk.CTkButton(c, text="Abonnement réactivé ? Réessayer",
                          command=self._router_licence, height=38, fg_color="transparent",
                          text_color=MUTED, hover_color=ACCENT_SOFT, border_width=1,
                          border_color=BORDER, corner_radius=10,
                          font=(POLICE, 12)).pack(fill="x", pady=(8, 0))

    # ----------------------------------------------------------- app (sidebar + contenu)
    def _construire_app(self):
        self._vider()
        cont = ctk.CTkFrame(self, fg_color="transparent")
        cont.pack(fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(cont, fg_color=SIDEBAR, corner_radius=0, width=244)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._construire_sidebar()

        self.contenu = ctk.CTkScrollableFrame(cont, fg_color=BG, corner_radius=0)
        self.contenu.pack(side="left", fill="both", expand=True)
        self._page_accueil()

        # Re-contrôle de l'abonnement (une fois).
        self._planifier_verif_periodique()
        # Rappel discret si on tourne en mode hors-ligne toléré.
        self._montrer_bandeau_horsligne((self.statut or {}).get("hors_ligne", False))
        # Raccourci sur le Bureau (version installée uniquement).
        if not getattr(self, "_raccourci_verifie", False):
            self._raccourci_verifie = True
            self.after(1500, self._verifier_raccourci)

    # ---- raccourci sur le Bureau ----
    def _verifier_raccourci(self):
        """1er lancement : crée le raccourci sur le Bureau (Windows / Mac).
        Lancements suivants : le met à jour si l'app a été déplacée."""
        app = raccourci.chemin_application()
        if not app:
            return          # mode développement : rien à faire
        action = raccourci.a_faire(app, bool(self.params.get("raccourci_bureau")),
                                   self.params.get("raccourci_cible", ""))
        if action == "temporaire":
            self._toast("Conseil : placez HelpVA dans un dossier fixe avant de l'utiliser\n"
                        + ("(glissez-le dans le dossier Applications)."
                           if sys.platform == "darwin" else
                           "(extrayez-le du fichier zip, par exemple dans Documents)."))
            return
        if action not in ("creer", "maj"):
            return

        self._lancer_creation_raccourci(app, action)

    def _lancer_creation_raccourci(self, app, action):
        """Crée le raccourci dans un thread (PowerShell peut prendre 1-2 s)."""
        if getattr(self, "_raccourci_en_cours", False):
            return
        self._raccourci_en_cours = True

        def job():
            try:
                _lien, deja = raccourci.creer(app, verifier_existant=(action == "creer"))
                self.file_log.put(("raccourci", action, app, "", deja))
            except Exception as e:
                self.file_log.put(("raccourci", action, app, str(e), False))
        threading.Thread(target=job, daemon=True).start()

    def _fin_raccourci(self, action, app, erreur, deja=False):
        self._raccourci_en_cours = False
        self.params["raccourci_bureau"] = True        # ne redemande jamais
        if not erreur and not deja:
            self.params["raccourci_cible"] = app
        try:
            parametres.sauver(self.params)
        except OSError:
            pass
        if action == "manuel":
            if erreur:
                messagebox.showwarning("Raccourci", f"Impossible de créer le raccourci :\n{erreur}")
            else:
                self._toast("✅ Raccourci HelpVA créé sur votre Bureau.")
            return
        if action != "creer" or deja:
            return                 # mise à jour silencieuse / raccourci déjà présent
        if erreur:
            self._toast("Astuce : créez un raccourci pour ouvrir HelpVA plus vite\n"
                        + ("(glissez HelpVA dans le Dock)." if sys.platform == "darwin" else
                           "(clic droit sur HelpVA.exe → Envoyer vers → Bureau)."))
        else:
            self._toast("✅ Un raccourci HelpVA a été ajouté sur votre Bureau.")

    def _creer_raccourci_manuel(self):
        """Bouton des Paramètres : (re)crée le raccourci à la demande."""
        app = raccourci.chemin_application()
        if not app:
            messagebox.showinfo("Raccourci", "Disponible dans la version installée de HelpVA "
                                             "(fichier .exe ou application Mac).")
            return
        situation = raccourci.situation(app)
        if situation == "sur_bureau":
            messagebox.showinfo("Raccourci", "HelpVA est déjà sur votre Bureau.")
            return
        if situation == "temporaire":
            messagebox.showinfo(
                "Raccourci", "HelpVA est lancé depuis un emplacement provisoire.\n\n"
                + ("Glissez d'abord HelpVA dans le dossier Applications, puis relancez-le."
                   if sys.platform == "darwin" else
                   "Extrayez d'abord HelpVA du fichier zip (par exemple dans Documents), "
                   "puis relancez-le."))
            return
        self._lancer_creation_raccourci(app, "manuel")

    def _toast(self, texte, duree=8000):
        """Petit message NON bloquant en bas à droite, qui disparaît tout seul."""
        try:
            ancien = getattr(self, "_toast_w", None)
            if ancien is not None and ancien.winfo_exists():
                ancien.destroy()
            t = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)
            self._toast_w = t
            ctk.CTkLabel(t, text=texte, font=(POLICE, 13), text_color=TEXT,
                         justify="left").pack(side="left", padx=(16, 6), pady=12)
            ctk.CTkButton(t, text="✕", width=28, height=28, corner_radius=8,
                          fg_color="transparent", hover_color=ACCENT_SOFT,
                          text_color=MUTED, command=t.destroy).pack(side="right", padx=(0, 8))
            # Au-dessus de l'éventuel bandeau « Hors-ligne ».
            t.place(relx=0.985, rely=0.97, y=-46, anchor="se")
            t.lift()
            self.after(duree, lambda: t.winfo_exists() and t.destroy())
        except Exception:
            pass

    def _montrer_bandeau_horsligne(self, afficher):
        """Petit bandeau flottant, NON bloquant, en bas à droite quand l'app
        n'arrive pas à confirmer l'abonnement en ligne (dans la tolérance)."""
        if afficher:
            b = getattr(self, "_bandeau_hl", None)
            if b is None or not b.winfo_exists():
                self._bandeau_hl = ctk.CTkLabel(
                    self, text="  Hors-ligne — reconnexion en cours…  ",
                    font=(POLICE, 12, "bold"), corner_radius=8,
                    fg_color=("#FDECEA", "#3A1E1E"), text_color="#E5844D")
            self._bandeau_hl.place(relx=0.985, rely=0.97, anchor="se")
            self._bandeau_hl.lift()
        else:
            b = getattr(self, "_bandeau_hl", None)
            if b is not None and b.winfo_exists():
                b.place_forget()

    def _construire_sidebar(self):
        # Marque
        haut = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        haut.pack(fill="x", padx=18, pady=(20, 20))
        try:
            from PIL import Image
            img = ctk.CTkImage(Image.open(chemin_ressource("assets/logo.png")), size=(38, 38))
            ctk.CTkLabel(haut, image=img, text="").pack(side="left")
            self._logo_ref = img
        except Exception:
            pass
        ctk.CTkLabel(haut, text="  HelpVA", font=(POLICE, 20, "bold"),
                     text_color=TEXT).pack(side="left")

        self._nav_boutons = {}
        self._nav_icones = {}
        nav = [("accueil", "Accueil", "accueil"), ("parametres", "Paramètres", "parametres")]
        for cle, lib, ic in nav:
            img = self._icone(ic, 26)
            self._nav_icones[cle] = img
            kw = dict(text=("   " + lib), anchor="w", height=46, corner_radius=12,
                      font=(POLICE, 15), fg_color="transparent", text_color=MUTED,
                      hover_color=ACCENT_SOFTER, command=lambda c=cle: self._aller(c))
            if img is not None:
                kw["image"] = img
                kw["compound"] = "left"
            else:
                kw["text"] = ("▦   " if ic == "accueil" else "⚙   ") + lib
            b = ctk.CTkButton(self.sidebar, **kw)
            b.pack(fill="x", padx=14, pady=3)
            self._nav_boutons[cle] = b
        self._maj_nav()

        # Carte utilisateur en bas
        bas = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bas.pack(side="bottom", fill="x", padx=14, pady=16)
        uc = ctk.CTkFrame(bas, fg_color=ACCENT_SOFTER, corner_radius=12)
        uc.pack(fill="x")
        av = ctk.CTkFrame(uc, fg_color=ACCENT_SOFT, corner_radius=17, width=34, height=34)
        av.pack_propagate(False)
        av.grid(row=0, column=0, padx=10, pady=10)
        _av_img = self._icone("profil", 20)
        if _av_img is not None:
            self._avatar_img = _av_img
            ctk.CTkLabel(av, image=_av_img, text="").place(relx=0.5, rely=0.5, anchor="center")
        else:
            ctk.CTkLabel(av, text="👤", font=(POLICE, 14)).place(relx=0.5, rely=0.5, anchor="center")
        info = ctk.CTkFrame(uc, fg_color="transparent")
        info.grid(row=0, column=1, sticky="w", pady=10)
        ctk.CTkLabel(info, text=((self.statut or {}).get("nom") or "HelpVA"),
                     font=(POLICE, 13, "bold"), text_color=TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(info, text=_abonnement_txt(self.statut), font=(POLICE, 11),
                     text_color=GREEN, anchor="w").pack(anchor="w")
        pied = ctk.CTkFrame(bas, fg_color="transparent")
        pied.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(pied, text=f"v{version.VERSION}", font=(POLICE, 11),
                     text_color=MUTED).pack(side="left", padx=6)
        _mode = ctk.get_appearance_mode()
        self._theme_img = self._icone("moon" if _mode == "Light" else "sun", 20)
        self._theme_btn = ctk.CTkButton(pied, text="", width=34, height=34, corner_radius=9,
                                        fg_color="transparent", hover_color=ACCENT_SOFTER,
                                        image=self._theme_img, command=self._toggle_theme)
        self._theme_btn.pack(side="right")

    def _toggle_theme(self):
        """Bascule clair/sombre depuis la sidebar."""
        nouveau = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(nouveau)
        self.params["theme"] = nouveau
        parametres.sauver(self.params)
        self._theme_img = self._icone("moon" if nouveau == "light" else "sun", 20)
        if getattr(self, "_theme_btn", None) is not None:
            self._theme_btn.configure(image=self._theme_img)

    def _maj_nav(self):
        for cle, b in self._nav_boutons.items():
            if cle == self.page:
                b.configure(fg_color=ACCENT_SOFT, text_color=ACCENT_HOVER)
            else:
                b.configure(fg_color="transparent", text_color=MUTED)

    def _aller(self, cle):
        self.page = cle
        self.log = None
        self._maj_nav()
        self._vider(self.contenu)
        pages = {"accueil": self._page_accueil,
                 "parametres": self._page_parametres}
        pages.get(cle, self._page_accueil)()

    # ----------------------------------------------------------- page Accueil
    def _entete(self, titre, sous="", icone=None):
        e = ctk.CTkFrame(self.contenu, fg_color="transparent")
        e.pack(fill="x", padx=36, pady=(30, 22))
        g = ctk.CTkFrame(e, fg_color="transparent")
        g.pack(side="left")
        ligne = ctk.CTkFrame(g, fg_color="transparent")
        ligne.pack(anchor="w")
        ctk.CTkLabel(ligne, text=titre, font=(POLICE, 28, "bold"),
                     text_color=TEXT).pack(side="left")
        if icone:
            _im = self._icone(icone, 34)
            if _im is not None:
                self._entete_img = _im
                ctk.CTkLabel(ligne, image=_im, text="").pack(side="left", padx=(10, 0))
        if sous:
            ctk.CTkLabel(g, text=sous, font=(POLICE, 14), text_color=MUTED).pack(anchor="w", pady=(2, 0))
        return e

    def _page_accueil(self):
        nom_det = (self.statut or {}).get("nom")
        self._entete(f"Hello, {nom_det}" if nom_det else "Hello",
                     "Préparez vos contenus en quelques étapes.", icone="hello")

        # Rangée cartes info (dossier de sortie + conseil) — MÊME largeur
        r = ctk.CTkFrame(self.contenu, fg_color="transparent")
        r.pack(fill="x", padx=36)
        r.grid_columnconfigure(0, weight=1, uniform="a")
        r.grid_columnconfigure(1, weight=1, uniform="a")

        _d = self.dossier_sortie()
        mc = ctk.CTkFrame(r, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER)
        mc.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        mci = ctk.CTkFrame(mc, fg_color="transparent")
        mci.pack(fill="x", padx=22, pady=20)
        gm = ctk.CTkFrame(mci, fg_color="transparent")
        gm.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(gm, text="DOSSIER DE SORTIE", font=(POLICE, 11, "bold"),
                     text_color=ACCENT_HOVER).pack(anchor="w")
        ctk.CTkLabel(gm, text=os.path.basename(_d) or _d, font=(POLICE, 20, "bold"),
                     text_color=TEXT).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(gm, text="Vos fichiers préparés sont enregistrés ici.",
                     font=(POLICE, 12), text_color=MUTED).pack(anchor="w")
        # Petites icônes d'action (Ouvrir le dossier / Modifier dans les Paramètres)
        acts = ctk.CTkFrame(mci, fg_color="transparent")
        acts.pack(side="right")
        self._mini_imgs = getattr(self, "_mini_imgs", [])
        for _ic, _cmd in [("ouvrir", self._ouvrir_dossier_sortie),
                          ("parametres", lambda: self._aller("parametres"))]:
            _im = self._icone(_ic, 20)
            if _im is not None:
                self._mini_imgs.append(_im)
            ctk.CTkButton(acts, text="" if _im else ("Ouvrir" if _ic == "ouvrir" else "…"),
                          image=_im, width=40, height=40, corner_radius=10,
                          fg_color=ACCENT_SOFT, hover_color="#E1DDFA",
                          command=_cmd).pack(side="left", padx=(6, 0))

        tc = ctk.CTkFrame(r, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER)
        tc.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        tci = ctk.CTkFrame(tc, fg_color="transparent")
        tci.pack(fill="both", expand=True, padx=20, pady=18)
        self._badge(tci, "bulb", 54).pack(side="left", padx=(0, 12))
        gt = ctk.CTkFrame(tci, fg_color="transparent")
        gt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(gt, text="Conseil", font=(POLICE, 14, "bold"),
                     text_color=ACCENT_HOVER, anchor="w").pack(anchor="w")
        ctk.CTkLabel(gt, text="Changez d'abord les métadonnées, puis rangez\nvos médias selon le calendrier.",
                     font=(POLICE, 13), text_color=MUTED, justify="left", anchor="w").pack(anchor="w")

        # Section : préparer le contenu (2 colonnes)
        self._section("Préparer le contenu")
        g1 = ctk.CTkFrame(self.contenu, fg_color="transparent")
        g1.pack(fill="x", padx=36)
        for i in range(2):
            g1.grid_columnconfigure(i, weight=1, uniform="c")
        feats1 = [("convertir", "Convertir les images", "En .jpg ou .png (HEIC iPhone inclus)", "images_convert"),
                  ("convertir", "Convertir en MP4", "Transforme .mov, .avi… en .mp4", "convertir"),
                  ("tag", "Changer les métadonnées", "Uniquifie vos photos et vidéos", "metadonnees"),
                  ("folder", "Ranger les médias", "Organise vos images et vidéos", "ranger")]
        for i, (emo, t, s, k) in enumerate(feats1):
            self._carte_fonction(g1, emo, t, s, k, row=i // 2, col=i % 2)

    def _section(self, titre):
        ctk.CTkLabel(self.contenu, text=titre, font=(POLICE, 20, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=38, pady=(28, 14))

    def _carte_fonction(self, parent, emoji, titre, sous, cle, col, row=0):
        carte = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16,
                             border_width=1, border_color=BORDER)
        carte.grid(row=row, column=col, sticky="ew", padx=8, pady=8)
        inner = ctk.CTkFrame(carte, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=18)
        self._badge(inner, emoji, 66).pack(side="left", padx=(0, 16))
        body = ctk.CTkFrame(inner, fg_color="transparent")
        body.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(body, text=titre, font=(POLICE, 16, "bold"),
                     text_color=TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(body, text=sous, font=(POLICE, 13), text_color=MUTED,
                     anchor="w").pack(anchor="w", pady=(2, 0))
        _fl = self._icone("arrow", 26)
        if _fl is not None:
            self._fleche_imgs = getattr(self, "_fleche_imgs", [])
            self._fleche_imgs.append(_fl)
            ctk.CTkLabel(inner, image=_fl, text="").pack(side="right")
        else:
            ctk.CTkLabel(inner, text="›", font=(POLICE, 24), text_color="#C7C9D6").pack(side="right")
        self._cliquable(carte, lambda k=cle: self._ouvrir_fonction(k))

    def _ouvrir_fonction(self, cle):
        self.page = ""
        self.log = None
        self._maj_nav()
        self._vider(self.contenu)
        pages = {"images_convert": self._page_convertir_images, "ranger": self._page_ranger,
                 "metadonnees": self._page_metadonnees,
                 "convertir": self._page_convertir}
        pages.get(cle, self._page_accueil)()

    # ==================================================================
    #  Infra : journal, threads, popups, chargement
    # ==================================================================
    def _pomper_log(self):
        try:
            while True:
                item = self.file_log.get_nowait()
                try:
                    if isinstance(item, tuple):
                        self._controle(item)
                    else:
                        self._inserer_log(item)
                except Exception as e:
                    # Une erreur sur UN message ne doit pas bloquer les suivants.
                    self._inserer_log(f"\n[ERREUR] {e}\n")
        except queue.Empty:
            pass
        finally:
            self.after(120, self._pomper_log)

    def _inserer_log(self, texte):
        if self.log is not None:
            try:
                self.log.configure(state="normal")
                self.log.insert("end", texte)
                self.log.see("end")
                self.log.configure(state="disabled")
            except Exception:
                pass

    def _controle(self, item):
        tag = item[0]
        if tag == "loading_fini":
            self._cacher_loading()
        elif tag == "uniq_progres":
            # Met à jour en direct la ligne du popup de chargement.
            try:
                lbl = getattr(self, "_lbl_loading", None)
                if lbl is not None and lbl.winfo_exists():
                    lbl.configure(text=item[1])
            except Exception:
                pass
        elif tag == "raccourci":
            self._fin_raccourci(*item[1:])
        elif tag == "verif_licence":
            self._traiter_verif(item[1])
        elif tag == "drive_apercu":
            self._cacher_loading()
            _, vignettes, total = item
            self._popup_apercu_drive(vignettes, total)
        elif tag == "drive_fini":
            self._cacher_loading()
            _, sortie, ni, nv, err, bloque = item
            if bloque:
                messagebox.showwarning(
                    "Google a bloqué votre réseau",
                    "⛔ Google a TEMPORAIREMENT bloqué les téléchargements depuis "
                    "votre connexion internet.\n\n"
                    "POURQUOI : trop de téléchargements en peu de temps depuis la même "
                    "adresse IP → Google te prend pour un robot (« automated queries »). "
                    "Ce n'est PAS un bug, ni un problème de partage de vos dossiers.\n\n"
                    "SOLUTIONS :\n"
                    "1) Change de connexion : partage 4G du téléphone, ou un VPN "
                    "(nouvelle IP → ça remarche tout de suite).\n"
                    "2) Ou attends (le blocage se lève tout seul, souvent quelques "
                    "heures).\n\n"
                    f"({ni} image(s) et {nv} vidéo(s) déjà récupérées avant le blocage.)")
                return
            msg = (f"✅ Téléchargé : {ni} image(s) et {nv} vidéo(s).\n\n"
                   f"Dossier :\n{sortie}\n(sous-dossiers images\\ et videos\\)\n\n"
                   "Vous pouvez maintenant l'utiliser pour Ranger ou Changer les métadonnées.")
            if err:
                msg += f"\n\n⚠️ {err} fichier(s) en échec."
            messagebox.showinfo("Google Drive", msg)
        elif tag == "popup":
            self._cacher_loading()
            _, titre, msg, err = item
            (messagebox.showwarning if err else messagebox.showinfo)(titre, msg)
        elif tag == "fini_ranger":
            self._cacher_loading()
            _, sortie, res = item
            if res.get("arrete"):
                messagebox.showwarning("Ranger", f"Rangement arrêté.\n\n{res.get('creneaux', 0)} "
                                                 f"créneau(x) déjà rangé(s) dans :\n{sortie}")
                return
            lignes, alerte = [], False
            for t in res.get("types", []):
                unite = "vidéo(s)" if rangement.est_video(t) else "image(s)"
                requis = res["besoins"][t] * rangement.medias_par_creneau(t)
                ligne = f"• {rangement.LIBELLES[t]} : {res['places'][t]}/{requis} {unite}"
                if res["manques"].get(t):
                    ligne += f"  ⚠️ il en manque {res['manques'][t]}"
                    alerte = True
                lignes.append(ligne)
            txt = "Médias rangés !\n\n" + "\n".join(lignes) + f"\n\nDossier :\n{sortie}"
            en_trop = sum(res.get("surplus", {}).values())
            if en_trop:
                txt += f"\n\n📦 {en_trop} média(s) en trop → dossier « surplus »."
            (messagebox.showwarning if alerte else messagebox.showinfo)("Ranger", txt)

    def _tache(self, fn, message="Traitement en cours…", annulable=False):
        if self.occupe:
            print("[!] Une action est déjà en cours, patiente…")
            return
        # Armé SYNCHRONEMENT (avant le thread) : deux clics rapides ne peuvent
        # plus lancer deux fois la même opération.
        self.occupe = True
        self._annule_tache = False
        self._afficher_loading(message, annulable=annulable)

        def envelopper():
            try:
                fn()
            except Exception as e:
                print(f"\n[ERREUR] {e}")
            finally:
                self.occupe = False
                self.file_log.put(("loading_fini",))
        threading.Thread(target=envelopper, daemon=True).start()

    def _fermer_app(self):
        """Fermeture propre : demande l'arrêt des traitements en cours puis quitte.

        Sans ça, un lot d'images lancé en parallèle continuerait en arrière-plan
        (les threads du pool ne sont pas daemon) : fenêtre fermée mais processus
        toujours vivant à 100 % de CPU.
        """
        self._annule_tache = True
        try:
            self.destroy()
        except Exception:
            pass

    def _notifier(self, titre, message, erreur=False):
        self.file_log.put(("popup", titre, message, erreur))

    def _ramener_modale(self, _evt=None):
        """Anti « app gelée » : quand la principale reçoit le focus, on gère un
        éventuel verrou (grab) resté actif.

        - modale valide cachée derrière / réduite -> on la remet devant ;
        - modale « fantôme » (verrou resté actif alors que la fenêtre n'est plus
          affichée) -> on LIBÈRE le verrou et on remet la principale devant
          (sinon la barre des tâches / Alt+Tab restent sans effet)."""
        try:
            g = self.grab_current()
        except Exception:
            g = None
        if g is None or g is self:
            return   # cas normal : rien à forcer

        try:
            top = g.winfo_toplevel()
            vivante = bool(top.winfo_exists())
        except Exception:
            top, vivante = None, False

        if vivante:
            try:
                if str(top.state()) == "iconic":
                    top.deiconify()
                top.lift()
                top.focus_force()
            except Exception:
                pass
        else:
            # verrou fantôme -> on le relâche et on remet l'app principale devant
            for essai in (g, self):
                try:
                    essai.grab_release()
                except Exception:
                    pass
            try:
                if str(self.state()) == "iconic":
                    self.deiconify()
                self.lift()
                self.focus_force()
            except Exception:
                pass

    def _modale_devant(self, top):
        """Force une fenêtre modale à apparaître DEVANT et à prendre le focus."""
        try:
            top.lift()
            top.focus_force()
            top.attributes("-topmost", True)
            top.after(400, lambda: top.winfo_exists() and top.attributes("-topmost", False))
        except Exception:
            pass

    def _afficher_loading(self, message, annulable=False):
        self._loading = ctk.CTkToplevel(self)
        self._loading.title("Veuillez patienter")
        self._loading.geometry("340x190" if annulable else "320x130")
        self._loading.configure(fg_color=BG)
        self._loading.resizable(False, False)
        self._loading.transient(self)
        self._lbl_loading = ctk.CTkLabel(self._loading, text=message, font=(POLICE, 13),
                                         text_color=TEXT, wraplength=300)
        self._lbl_loading.pack(pady=(26, 12))
        pb = ctk.CTkProgressBar(self._loading, mode="indeterminate", width=250,
                                progress_color=ACCENT)
        pb.pack(pady=4)
        pb.start()
        self._pb = pb
        if annulable:
            ctk.CTkButton(self._loading, text="✖ Annuler l'opération", height=36,
                          corner_radius=10, font=(POLICE, 13, "bold"),
                          fg_color=("#FDECEA", "#3A1E1E"), text_color="#E5484D",
                          hover_color="#F8D7D5",
                          command=self._annuler_tache).pack(pady=(16, 8))
        # PAS de grab_set ici : l'écran de chargement d'une opération LONGUE
        # (téléchargement Drive…) ne doit pas verrouiller l'app, sinon réduire
        # puis rouvrir depuis la barre des tâches ne marche plus. `self.occupe`
        # empêche déjà de lancer deux tâches en même temps.
        self._modale_devant(self._loading)

    def _annuler_tache(self):
        """Demande l'arrêt complet de la tâche en cours."""
        self._annule_tache = True
        print("⛔ Annulation demandée — arrêt de l'opération…")
        try:
            if getattr(self, "_lbl_loading", None) and self._lbl_loading.winfo_exists():
                self._lbl_loading.configure(text="Annulation en cours…")
        except Exception:
            pass

    def _cacher_loading(self):
        lo = self._loading
        self._loading = None
        if lo is None:
            return
        try:
            lo.grab_release()
        except Exception:
            pass
        # On DIFFÈRE la destruction : CustomTkinter planifie en interne un
        # after(~200ms) (deiconify) après la création du Toplevel ; le détruire
        # trop vite provoque « bad window path name ». On attend ~260ms.
        def _kill(w=lo):
            try:
                if w.winfo_exists():
                    w.destroy()
            except Exception:
                pass
        try:
            self.after(260, _kill)
        except Exception:
            _kill()

    # ----- briques d'UI réutilisables -----
    def _entete_page(self, titre, sous="", action=None):
        e = ctk.CTkFrame(self.contenu, fg_color="transparent")
        e.pack(fill="x", padx=36, pady=(28, 16))
        barre = ctk.CTkFrame(e, fg_color="transparent")
        barre.pack(fill="x")
        ctk.CTkButton(barre, text="←  Accueil", width=104, height=36,
                      command=lambda: self._aller("accueil"), fg_color=ACCENT_SOFT,
                      text_color=ACCENT_HOVER, hover_color="#E1DDFA", corner_radius=10,
                      font=(POLICE, 14)).pack(side="left")
        if action:
            ctk.CTkButton(barre, text=action[0], command=action[1], height=36,
                          fg_color=ACCENT_HOVER, hover_color="#4A3FCC", corner_radius=10,
                          font=(POLICE, 14, "bold")).pack(side="right")
        ctk.CTkLabel(e, text=titre, font=(POLICE, 30, "bold"),
                     text_color=TEXT).pack(anchor="w", pady=(16, 0))
        if sous:
            ctk.CTkLabel(e, text=sous, font=(POLICE, 15), text_color=MUTED,
                         justify="left").pack(anchor="w", pady=(6, 0))

    def _carte(self, pad=22):
        c = ctk.CTkFrame(self.contenu, fg_color=CARD, corner_radius=16,
                         border_width=1, border_color=BORDER)
        c.pack(fill="x", padx=36, pady=8)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="x", padx=pad, pady=pad)
        return inner

    def _entete_etape(self, parent, num, titre, sous=""):
        """En-tête d'étape : pastille numérotée + titre + sous-titre.
        Utilisé par les pages « en étapes » (design premium homogène)."""
        barre = ctk.CTkFrame(parent, fg_color="transparent")
        barre.pack(fill="x")
        past = ctk.CTkFrame(barre, fg_color=ACCENT_SOFT, corner_radius=16, width=32, height=32)
        past.pack_propagate(False)
        past.pack(side="left")
        ctk.CTkLabel(past, text=str(num), font=(POLICE, 15, "bold"),
                     text_color=ACCENT_HOVER).pack(expand=True)
        bloc = ctk.CTkFrame(barre, fg_color="transparent")
        bloc.pack(side="left", padx=(12, 0), fill="x", expand=True)
        ctk.CTkLabel(bloc, text=titre, font=(POLICE, 16, "bold"),
                     text_color=TEXT).pack(anchor="w")
        if sous:
            ctk.CTkLabel(bloc, text=sous, font=(POLICE, 12),
                         text_color=MUTED).pack(anchor="w")

    def _zone_journal(self):
        """Journal de l'action en cours (rien n'est conservé entre les pages)."""
        c = ctk.CTkFrame(self.contenu, fg_color=CARD, corner_radius=16,
                         border_width=1, border_color=BORDER)
        c.pack(fill="both", expand=True, padx=36, pady=(8, 22))
        haut = ctk.CTkFrame(c, fg_color="transparent")
        haut.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(haut, text="Journal", font=(POLICE, 12, "bold"),
                     text_color=MUTED).pack(side="left")
        ctk.CTkButton(haut, text="Effacer", width=70, height=28, command=self._effacer_journal,
                      fg_color=ACCENT_SOFT, text_color=ACCENT_HOVER, hover_color="#E1DDFA",
                      corner_radius=8, font=(POLICE, 12)).pack(side="right")
        self.log = ctk.CTkTextbox(c, height=170, font=("Consolas", 12.5),
                                  fg_color=("#FBFBFE", "#0F1019"), text_color=TEXT,
                                  corner_radius=10)
        self.log.pack(fill="both", expand=True, padx=14, pady=(6, 14))
        self.log.configure(state="disabled")

    def _effacer_journal(self):
        if self.log is not None:
            try:
                self.log.configure(state="normal")
                self.log.delete("1.0", "end")
                self.log.configure(state="disabled")
            except Exception:
                pass

    def _btn(self, parent, texte, cmd, primaire=False):
        if primaire:
            return ctk.CTkButton(parent, text=texte, command=cmd, height=42, corner_radius=12,
                                 fg_color=ACCENT_HOVER, hover_color="#4A3FCC",
                                 font=(POLICE, 14, "bold"))
        return ctk.CTkButton(parent, text=texte, command=cmd, height=42, corner_radius=12,
                             fg_color=ACCENT_SOFT, text_color=ACCENT_HOVER,
                             hover_color="#E1DDFA", font=(POLICE, 14))

    # ==================================================================
    #  Page : Ranger les médias (3 étapes : calendrier → dossiers → rangement)
    # ==================================================================
    def _types_ranger_coches(self):
        """Types de posts que l'utilisateur veut ranger (réglage mémorisé)."""
        choix = self.params.get("ranger_types")
        if not isinstance(choix, dict):
            choix = {}
        return {t: bool(choix.get(t, True)) for t in rangement.TYPES}

    def _types_ranger_actifs(self):
        """Types cochés ET présents dans le calendrier."""
        n = rangement.compter()
        coches = self._types_ranger_coches()
        return [t for t in rangement.TYPES if coches[t] and n[t] > 0]

    def _maj_besoins_ranger(self):
        """Après modification du calendrier : reconstruit la page Ranger si elle
        est affichée (types disponibles + besoins à jour)."""
        z = getattr(self, "_ranger_etape2", None)
        try:
            if z is not None and z.winfo_exists():
                self._ouvrir_fonction("ranger")
        except Exception:
            pass

    @staticmethod
    def _nom_type(t):
        """« réels », « stories », « stories CTA », « carrousels »."""
        lib = rangement.LIBELLES[t]
        return lib[0].lower() + lib[1:]

    def _page_ranger(self):
        self._entete_page("Ranger les médias",
                          "Classe vos photos et vidéos selon votre calendrier de posts.")
        n = rangement.compter()
        nb_semaines = len(calendrier.charger_calendrier())

        # ---------- Encart info : à quoi sert le module ----------
        info = self._carte(pad=18)
        info_row = ctk.CTkFrame(info, fg_color="transparent")
        info_row.pack(fill="x")
        self._badge(info_row, "folder", taille=46).pack(side="left", padx=(0, 14))
        info_txt = ctk.CTkFrame(info_row, fg_color="transparent")
        info_txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info_txt, text="Ce que fait ce module", font=(POLICE, 14, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            info_txt, justify="left", font=(POLICE, 13), text_color=MUTED,
            text="HelpVA crée un dossier par semaine / jour / créneau et y copie vos médias.\n"
                 "Chaque type de post a son propre dossier source.\n"
                 "Vos originaux ne sont pas touchés.").pack(anchor="w", pady=(2, 0))

        # ---------- Étape 1 : calendrier + types de posts ----------
        c1 = self._carte()
        self._entete_etape(c1, 1, "Régler le calendrier",
                           "Choisissez les types de posts à ranger.")
        ligne = ctk.CTkFrame(c1, fg_color="transparent")
        ligne.pack(fill="x", pady=(16, 0))
        ctk.CTkLabel(ligne, font=(POLICE, 14, "bold"), text_color=TEXT,
                     text=f"Calendrier : {nb_semaines} semaine(s) · "
                          f"{sum(n.values())} créneau(x)").pack(side="left")
        self._btn(ligne, "Modifier le calendrier",
                  self.ouvrir_editeur_calendrier).pack(side="right")

        types_row = ctk.CTkFrame(c1, fg_color="transparent")
        types_row.pack(fill="x", pady=(14, 0))
        coches = self._types_ranger_coches()
        absents = []
        for t in rangement.TYPES:
            cb = ctk.CTkCheckBox(types_row, text=f"{rangement.LIBELLES[t]} ({n[t]})",
                                 font=(POLICE, 14), fg_color=ACCENT_HOVER,
                                 hover_color="#4A3FCC")
            cb.configure(command=lambda t=t, c=cb: self._basculer_type_ranger(t, c.get()))
            if n[t] == 0:
                cb.configure(state="disabled")
                absents.append(f"« {rangement.LIBELLES[t]} »")
            elif coches[t]:
                cb.select()
            cb.pack(side="left", padx=(0, 22))
        if absents:
            ctk.CTkLabel(c1, justify="left", font=(POLICE, 12), text_color=MUTED,
                         text=f"Aucun créneau {', '.join(absents)} dans le calendrier : "
                              "ajoutez-en via « Modifier le calendrier » pour l'activer."
                         ).pack(anchor="w", pady=(10, 0))

        # ---------- Étape 2 : un dossier par type (onglets) ----------
        c2 = self._carte()
        self._entete_etape(c2, 2, "Choisir les dossiers", "Un dossier par type de post.")
        self._ranger_etape2 = ctk.CTkFrame(c2, fg_color="transparent")
        self._ranger_etape2.pack(fill="x")
        self._construire_etape2_ranger()

        # ---------- Étape 3 : lancer ----------
        c3 = self._carte()
        self._entete_etape(c3, 3, "Lancer le rangement",
                           "Les médias sont copiés dans votre dossier de sortie.")
        self.chk_aleatoire_ranger = ctk.CTkCheckBox(
            c3, text="Répartir au hasard (les carrousels gardent toujours l'ordre 1, 2, 3…)",
            font=(POLICE, 14), fg_color=ACCENT_HOVER, hover_color="#4A3FCC",
            command=lambda: setattr(self, "ranger_aleatoire",
                                    bool(self.chk_aleatoire_ranger.get())))
        if self.ranger_aleatoire:
            self.chk_aleatoire_ranger.select()
        self.chk_aleatoire_ranger.pack(anchor="w", pady=(16, 0))

        action = ctk.CTkFrame(self.contenu, fg_color="transparent")
        action.pack(fill="x", padx=36, pady=(14, 2))
        self._btn(action, "Ranger les médias  →", self._lancer_ranger,
                  primaire=True).pack(fill="x")

        self._zone_journal()

    def _basculer_type_ranger(self, t, coche):
        coches = self._types_ranger_coches()
        coches[t] = bool(coche)
        self.params["ranger_types"] = coches
        parametres.sauver(self.params)
        self._construire_etape2_ranger()

    def _construire_etape2_ranger(self):
        z = self._ranger_etape2
        for w in z.winfo_children():
            w.destroy()
        actifs = self._types_ranger_actifs()
        if not actifs:
            ctk.CTkLabel(z, text="Cochez au moins un type de post à l'étape 1.",
                         font=(POLICE, 13), text_color=MUTED).pack(anchor="w", pady=(16, 0))
            return
        if self._onglet_ranger not in actifs:
            self._onglet_ranger = actifs[0]
        # Onglets aux couleurs de l'app ; ✓ quand le dossier du type est choisi.
        barre = ctk.CTkFrame(z, fg_color="transparent")
        barre.pack(anchor="w", pady=(16, 16))
        for t in actifs:
            actif = t == self._onglet_ranger
            ctk.CTkButton(
                barre, text=rangement.LIBELLES[t] + ("  ✓" if self.sources_ranger.get(t) else ""),
                height=38, corner_radius=10, font=(POLICE, 14, "bold"),
                fg_color=ACCENT_HOVER if actif else ACCENT_SOFT,
                hover_color="#4A3FCC" if actif else "#E1DDFA",
                text_color="#FFFFFF" if actif else ACCENT_HOVER,
                command=lambda t=t: self._choisir_onglet_ranger(t)).pack(side="left", padx=(0, 8))
        self._ranger_onglet = ctk.CTkFrame(z, fg_color="transparent")
        self._ranger_onglet.pack(fill="x")
        self._contenu_onglet_ranger(self._onglet_ranger)

    def _choisir_onglet_ranger(self, t):
        self._onglet_ranger = t
        self._construire_etape2_ranger()

    def _contenu_onglet_ranger(self, t):
        z = self._ranger_onglet
        video = rangement.est_video(t)
        unite = "vidéo(s)" if video else "image(s)"
        nb = rangement.compter()[t]
        requis = nb * rangement.medias_par_creneau(t)
        if t == "carousel":
            regle = ("Photos nommées 1, 2, 3… — rangées dans l'ordre par groupes de "
                     f"{rangement.IMAGES_PAR_CAROUSEL} (1-2-3 → 1er carrousel, etc.).")
        elif video:
            regle = "Uniquement des vidéos (.mp4, .mov…) — les images sont ignorées."
        else:
            regle = "Uniquement des images (.jpg, .png…) — les vidéos sont ignorées."
        ctk.CTkLabel(z, text=regle, font=(POLICE, 13), text_color=MUTED,
                     justify="left").pack(anchor="w")
        besoin = f"Besoin : {requis} {unite}"
        if t == "carousel":
            besoin += f" ({nb} carrousel(s))"
        ctk.CTkLabel(z, text=besoin, font=(POLICE, 14, "bold"),
                     text_color=ACCENT_HOVER).pack(anchor="w", pady=(8, 12))
        self._btn(z, f"Importer le dossier des {self._nom_type(t)}…",
                  lambda: self._choisir_dossier_type_ranger(t)).pack(anchor="w", pady=(0, 14))

        zone = ctk.CTkFrame(z, fg_color=ACCENT_SOFTER, corner_radius=12,
                            border_width=1, border_color=BORDER)
        zone.pack(fill="x")
        zrow = ctk.CTkFrame(zone, fg_color="transparent")
        zrow.pack(fill="x", padx=16, pady=14)
        self._badge(zrow, "folder", taille=40).pack(side="left", padx=(0, 12))
        src = ctk.CTkFrame(zrow, fg_color="transparent")
        src.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(src, text=f"DOSSIER DES {rangement.LIBELLES[t].upper()}",
                     font=(POLICE, 11, "bold"), text_color=MUTED).pack(anchor="w")
        d = self.sources_ranger.get(t)
        ctk.CTkLabel(src, text=d or "Aucun dossier sélectionné", justify="left",
                     font=(POLICE, 14), text_color=TEXT).pack(anchor="w", pady=(2, 0))
        if d:
            a = rangement.analyser_dossier(d, t)
            k = len(a["fichiers"])
            if k >= requis:
                etat, coul = f"✅ {k} {unite} trouvée(s)", GREEN
            else:
                etat, coul = f"⚠️ {k} {unite} trouvée(s) — il en manque {requis - k}", ORANGE
            if a["ignores"]:
                etat += f" · {a['ignores']} fichier(s) ignoré(s)"
            ctk.CTkLabel(src, text=etat, font=(POLICE, 13, "bold"),
                         text_color=coul).pack(anchor="w", pady=(4, 0))

    def _choisir_dossier_type_ranger(self, t):
        d = filedialog.askdirectory(title=f"Choisir le dossier des {self._nom_type(t)}")
        if not d:
            return
        self.sources_ranger[t] = d
        self._onglet_ranger = t
        self._construire_etape2_ranger()

    def _lancer_ranger(self):
        actifs = self._types_ranger_actifs()
        if not actifs:
            messagebox.showwarning("Ranger", "Cochez au moins un type de post (étape 1).")
            return
        manquants = [t for t in actifs
                     if not (self.sources_ranger.get(t) and os.path.isdir(self.sources_ranger[t]))]
        if manquants:
            self._onglet_ranger = manquants[0]
            self._construire_etape2_ranger()
            messagebox.showwarning("Ranger", "Choisissez un dossier pour :\n\n" + "\n".join(
                f"• {rangement.LIBELLES[t]}" for t in manquants))
            return

        sortie = os.path.join(self.dossier_sortie(), "ranger")
        a_out = os.path.normcase(os.path.abspath(sortie))
        vus = {}
        doublons = []
        for t in actifs:
            a_src = os.path.normcase(os.path.abspath(self.sources_ranger[t]))
            if a_src == a_out or a_src.startswith(a_out + os.sep):
                messagebox.showerror("Dossier invalide",
                                     f"Le dossier des {self._nom_type(t)} est dans le dossier de "
                                     "sortie, qui va être remplacé. Choisissez un autre dossier.")
                return
            # Même dossier pour deux types d'IMAGES -> mêmes images rangées 2 fois.
            if not rangement.est_video(t):
                if a_src in vus:
                    doublons.append(f"{rangement.LIBELLES[vus[a_src]]} et {rangement.LIBELLES[t]}")
                else:
                    vus[a_src] = t
        if doublons and not messagebox.askyesno(
                "Même dossier",
                "Le même dossier est utilisé pour : " + ", ".join(doublons) + ".\n"
                "Les mêmes images seront rangées deux fois.\n\nContinuer ?"):
            return

        n = rangement.compter()
        lignes, incomplet = [], False
        for t in actifs:
            k = len(rangement.analyser_dossier(self.sources_ranger[t], t)["fichiers"])
            requis = n[t] * rangement.medias_par_creneau(t)
            unite = "vidéo(s)" if rangement.est_video(t) else "image(s)"
            txt = f"• {rangement.LIBELLES[t]} : {k} {unite} pour {requis} requise(s)"
            if k < requis:
                txt += f"  ⚠️ il en manque {requis - k}"
                incomplet = True
            lignes.append(txt)
        existe = os.path.exists(sortie)
        msg = "À ranger :\n" + "\n".join(lignes) + f"\n\nDestination :\n{sortie}\n"
        if incomplet:
            msg += "\n⚠️ Certains créneaux resteront incomplets.\n"
        if existe:
            msg += "\n⚠️ Ce dossier existe déjà et sera REMPLACÉ.\n"
        if not messagebox.askyesno("Confirmer le rangement", msg + "\nContinuer ?"):
            return

        sources = dict(self.sources_ranger)
        aleatoire = bool(self.chk_aleatoire_ranger.get())

        def job():
            if existe:
                shutil.rmtree(sortie, ignore_errors=True)
            try:
                res = rangement.ranger(
                    sources, sortie, actifs, aleatoire=aleatoire,
                    progress=lambda txt: self.file_log.put(("uniq_progres", txt)),
                    doit_arreter=lambda: self._annule_tache)
            except Exception as e:
                print(f"\n[ERREUR] {e}")
                self._notifier("Ranger", str(e), erreur=True)
                return
            self.file_log.put(("fini_ranger", sortie, res))
        self._tache(job, "Rangement en cours…", annulable=True)

    # ==================================================================
    #  Page : Changer les métadonnées
    # ==================================================================
    def _page_metadonnees(self):
        self._entete_page("Changer les métadonnées",
                          "Rendez chaque photo et vidéo unique — en 2 étapes simples.")

        # ---------- Encart info : anti-doublon + conversion HEIC iPhone ----------
        info = self._carte(pad=18)
        info_row = ctk.CTkFrame(info, fg_color="transparent")
        info_row.pack(fill="x")
        self._badge(info_row, "bulb", taille=46).pack(side="left", padx=(0, 14))
        info_txt = ctk.CTkFrame(info_row, fg_color="transparent")
        info_txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info_txt, text="Ce que fait ce module", font=(POLICE, 14, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            info_txt, justify="left", font=(POLICE, 13), text_color=MUTED,
            text="Chaque média devient unique (métadonnées + pixels invisibles) pour éviter la\n"
                 "détection de doublon entre comptes. Les photos iPhone HEIC / HEIF — qui ne\n"
                 "s'affichent pas sur Instagram — sont aussi converties en .jpg automatiquement.\n"
                 "Importez un dossier même avec des sous-dossiers : la structure est conservée.\n"
                 "Vos fichiers originaux ne sont jamais modifiés.").pack(anchor="w", pady=(2, 0))

        # ---------- Étape 1 : choisir la source ----------
        c1 = self._carte()
        self._entete_etape(c1, 1, "Choisir la source",
                           "Un dossier entier, ou des images / vidéos précises.")
        boutons = ctk.CTkFrame(c1, fg_color="transparent")
        boutons.pack(fill="x", pady=(16, 14))
        self._btn(boutons, "Importer un dossier…",
                  self._choisir_dossier_uniq).pack(side="left", padx=(0, 10))
        self._btn(boutons, "Importer des images / vidéos…",
                  self._choisir_images_uniq).pack(side="left")
        zone = ctk.CTkFrame(c1, fg_color=ACCENT_SOFTER, corner_radius=12,
                            border_width=1, border_color=BORDER)
        zone.pack(fill="x")
        zone_row = ctk.CTkFrame(zone, fg_color="transparent")
        zone_row.pack(fill="x", padx=16, pady=14)
        self._badge(zone_row, "folder", taille=40).pack(side="left", padx=(0, 12))
        src = ctk.CTkFrame(zone_row, fg_color="transparent")
        src.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(src, text="SOURCE SÉLECTIONNÉE", font=(POLICE, 11, "bold"),
                     text_color=MUTED).pack(anchor="w")
        self.lbl_uniq = ctk.CTkLabel(src, text=self._txt_source_uniq(), justify="left",
                                     font=(POLICE, 14), text_color=TEXT)
        self.lbl_uniq.pack(anchor="w", pady=(2, 0))

        # ---------- Étape 2 : options ----------
        c2 = self._carte()
        self._entete_etape(c2, 2, "Options", "Un réglage, c'est tout.")
        self.chk_renommer = ctk.CTkCheckBox(c2, text="Renommer les médias (1, 2, 3…)",
                                            font=(POLICE, 14), fg_color=ACCENT_HOVER)
        self.chk_renommer.select()
        self.chk_renommer.pack(anchor="w", pady=(16, 2))
        ctk.CTkLabel(c2, text="Renumérote proprement les fichiers de sortie (recommandé).",
                     font=(POLICE, 12), text_color=MUTED).pack(anchor="w", padx=(30, 0))

        # ---------- Action : bouton « Lancer » pleine largeur ----------
        action = ctk.CTkFrame(self.contenu, fg_color="transparent")
        action.pack(fill="x", padx=36, pady=(14, 2))
        self._btn(action, "Lancer  →", self._lancer_uniquiser,
                  primaire=True).pack(fill="x")
        ctk.CTkLabel(
            action, justify="left", font=(POLICE, 11, "bold"), text_color=MUTED,
            text="Résultat : un dossier « <votre dossier> (métadonnées changées) » — même arborescence."
        ).pack(anchor="w", pady=(8, 0))

        self._zone_journal()

    def _txt_source_uniq(self):
        if self.fichiers_uniq_src:
            return f"{len(self.fichiers_uniq_src)} image(s)/vidéo(s) sélectionnée(s)"
        if self.dossier_uniq_src:
            return f"Dossier : {self.dossier_uniq_src}"
        return "Aucune source sélectionnée"

    def _choisir_dossier_uniq(self):
        dossier = filedialog.askdirectory(title="Choisir le dossier (images ou vidéos)")
        if not dossier:
            return
        self.dossier_uniq_src = dossier
        self.fichiers_uniq_src = None          # le dossier remplace la sélection de fichiers
        self.lbl_uniq.configure(text=self._txt_source_uniq())

    def _choisir_images_uniq(self):
        fichiers = filedialog.askopenfilenames(
            title="Choisir des images / vidéos",
            filetypes=[("Médias", "*.jpg *.jpeg *.png *.webp *.mp4 *.mov *.m4v *.avi *.mkv"),
                       ("Tous", "*.*")])
        if not fichiers:
            return
        self.fichiers_uniq_src = list(fichiers)
        self.dossier_uniq_src = None           # la sélection de fichiers remplace le dossier
        self.lbl_uniq.configure(text=self._txt_source_uniq())

    def _lancer_uniquiser(self):
        if not self.fichiers_uniq_src and not self.dossier_uniq_src:
            messagebox.showwarning("Métadonnées", "Importe d'abord un dossier ou des images.")
            return
        renommer = bool(self.chk_renommer.get())
        filtre = False   # option de filtre retirée : uniquisation invisible uniquement
        fichiers = list(self.fichiers_uniq_src) if self.fichiers_uniq_src else None
        dossier = self.dossier_uniq_src
        # Sortie nommée d'après le dossier importé : « OK » -> « OK (métadonnées changées) ».
        if dossier:
            nom_src = os.path.basename(os.path.normpath(dossier)) or "media"
            sortie = os.path.join(self.dossier_sortie(), f"{nom_src} (métadonnées changées)")
        else:
            sortie = os.path.join(self.dossier_sortie(), "media (métadonnées changées)")
        # Sécurité : la source ne doit pas être le dossier de sortie (ni dedans),
        # sinon on supprimerait la source (rmtree) avant de la traiter.
        if dossier:
            a_src, a_out = os.path.abspath(dossier), os.path.abspath(sortie)
            if a_src == a_out or a_src.startswith(a_out + os.sep):
                messagebox.showerror(
                    "Dossier invalide",
                    "Choisissez un autre dossier : la source ne peut pas être le dossier de "
                    "sortie « media (métadonnées changées) » (ni un sous-dossier de celui-ci).")
                return
        if os.path.exists(sortie):
            if not messagebox.askyesno("Remplacer ?",
                                       f"Le dossier existe déjà et sera REMPLACÉ :\n{sortie}\n\nContinuer ?"):
                return

        def job():
            if os.path.exists(sortie):
                shutil.rmtree(sortie, ignore_errors=True)

            def progres(txt):
                self.file_log.put(("uniq_progres", txt))
            try:
                if fichiers:
                    res = unicite.uniquiser_fichiers(
                        fichiers, sortie, renommer=renommer, filtre=filtre,
                        progress=progres, doit_arreter=lambda: self._annule_tache)
                    res["arrete"] = bool(self._annule_tache)
                    res.setdefault("dossiers", 0)
                else:
                    # Dossier : arborescence conservée + progression fichier par fichier.
                    res = unicite.uniquiser_arbre(
                        dossier, sortie, renommer=renommer, filtre=filtre,
                        progress=progres, doit_arreter=lambda: self._annule_tache)
            except Exception as e:
                print(f"\n[ERREUR] {e}")
                self._notifier("Métadonnées", str(e), erreur=True)
                return
            self._fin_traitement("Métadonnées changées", res, sortie,
                                 "média(s)", res.get("dossiers"))
        self._tache(job, "Changement des métadonnées…", annulable=True)

    def _fin_traitement(self, titre, res, sortie, mot="fichier(s)", nb_dossiers=None):
        """Message de fin commun : annulation, échecs éventuels, résultat."""
        n = res.get("medias", res.get("images", 0))
        echecs = res.get("echecs") or []
        if res.get("arrete"):
            print(f"\n⛔ Arrêté. {n} {mot} déjà traité(s) → {sortie}")
            self._notifier("Interrompu", f"Opération arrêtée.\n{n} {mot} déjà traité(s).")
            return
        detail = f"\n\nRésultat :\n{sortie}"
        if nb_dossiers:
            detail = (f" dans {nb_dossiers} dossier(s) !\n\nMême arborescence que "
                      f"votre dossier, dans :\n{sortie}")
            msg = f"✅ {n} {mot} traité(s)" + detail
        else:
            msg = f"✅ {n} {mot} traité(s) !" + detail
        print(f"\n✅ {n} {mot} → {sortie}")
        if echecs:
            apercu = ", ".join(echecs[:5]) + ("…" if len(echecs) > 5 else "")
            print(f"⚠️ {len(echecs)} fichier(s) illisibles : {apercu}")
            msg += (f"\n\n⚠️ {len(echecs)} fichier(s) n'ont PAS pu être traités "
                    f"(illisibles/corrompus) :\n{apercu}\n\nVoir le journal pour le détail.")
        self._notifier(titre, msg, erreur=bool(echecs))

    # ==================================================================
    #  Page : Convertir en MP4
    # ==================================================================
    def _page_convertir(self):
        self._entete_page("Convertir en MP4",
                          "Transforme vos vidéos (.mov, .avi, .mkv…) en .mp4.")

        # ---------- Encart info : ce que fait le module ----------
        info = self._carte(pad=18)
        info_row = ctk.CTkFrame(info, fg_color="transparent")
        info_row.pack(fill="x")
        self._badge(info_row, "convertir", taille=46).pack(side="left", padx=(0, 14))
        info_txt = ctk.CTkFrame(info_row, fg_color="transparent")
        info_txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info_txt, text="Ce que fait ce module", font=(POLICE, 14, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            info_txt, justify="left", font=(POLICE, 13), text_color=MUTED,
            text="Choisissez des vidéos ou un dossier. HelpVA crée une version .mp4 dans\n"
                 "« media (mp4) ». Rapide quand c'est possible (change juste le conteneur),\n"
                 "sinon ré-encodage automatique (H.264/AAC) pour que ça marche à coup sûr.\n"
                 "Vos originaux ne sont pas touchés.").pack(anchor="w", pady=(2, 0))

        # ---------- Étape 1 : choisir les vidéos ----------
        c1 = self._carte()
        self._entete_etape(c1, 1, "Choisir les vidéos",
                           "Un dossier entier, ou des vidéos précises.")
        boutons = ctk.CTkFrame(c1, fg_color="transparent")
        boutons.pack(fill="x", pady=(16, 14))
        self._btn(boutons, "Importer un dossier…",
                  self._choisir_dossier_convert).pack(side="left", padx=(0, 10))
        self._btn(boutons, "Importer des vidéos…",
                  self._choisir_videos_convert).pack(side="left")
        zone = ctk.CTkFrame(c1, fg_color=ACCENT_SOFTER, corner_radius=12,
                            border_width=1, border_color=BORDER)
        zone.pack(fill="x")
        zone_row = ctk.CTkFrame(zone, fg_color="transparent")
        zone_row.pack(fill="x", padx=16, pady=14)
        self._badge(zone_row, "folder", taille=40).pack(side="left", padx=(0, 12))
        src = ctk.CTkFrame(zone_row, fg_color="transparent")
        src.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(src, text="SOURCE SÉLECTIONNÉE", font=(POLICE, 11, "bold"),
                     text_color=MUTED).pack(anchor="w")
        self.lbl_convert = ctk.CTkLabel(src, text=self._txt_source_convert(), justify="left",
                                        font=(POLICE, 14), text_color=TEXT)
        self.lbl_convert.pack(anchor="w", pady=(2, 0))

        # ---------- Action : bouton « Convertir » pleine largeur ----------
        action = ctk.CTkFrame(self.contenu, fg_color="transparent")
        action.pack(fill="x", padx=36, pady=(14, 2))
        self._btn(action, "Convertir  →", self._lancer_convert,
                  primaire=True).pack(fill="x")
        ctk.CTkLabel(
            action, justify="left", font=(POLICE, 11, "bold"), text_color=MUTED,
            text="Résultat dans « media (mp4) ». La conversion peut être longue selon les vidéos."
        ).pack(anchor="w", pady=(8, 0))

        self._zone_journal()

    def _txt_source_convert(self):
        if self.fichiers_convert_src:
            return f"{len(self.fichiers_convert_src)} vidéo(s) sélectionnée(s)"
        if self.dossier_convert_src:
            return f"Dossier : {self.dossier_convert_src}"
        return "Aucune source sélectionnée"

    def _choisir_dossier_convert(self):
        dossier = filedialog.askdirectory(title="Choisir le dossier de vidéos")
        if not dossier:
            return
        self.dossier_convert_src = dossier
        self.fichiers_convert_src = None
        self.lbl_convert.configure(text=self._txt_source_convert())

    def _choisir_videos_convert(self):
        fichiers = filedialog.askopenfilenames(
            title="Choisir des vidéos",
            filetypes=[("Vidéos", "*.mov *.mp4 *.m4v *.avi *.mkv *.webm *.mpg *.mpeg *.wmv *.flv"),
                       ("Tous", "*.*")])
        if not fichiers:
            return
        self.fichiers_convert_src = list(fichiers)
        self.dossier_convert_src = None
        self.lbl_convert.configure(text=self._txt_source_convert())

    def _lancer_convert(self):
        if not self.fichiers_convert_src and not self.dossier_convert_src:
            messagebox.showwarning("Convertir", "Importe d'abord un dossier ou des vidéos.")
            return
        sortie = os.path.join(self.dossier_sortie(), "media (mp4)")
        fichiers = list(self.fichiers_convert_src) if self.fichiers_convert_src else None
        dossier = self.dossier_convert_src

        def job():
            os.makedirs(sortie, exist_ok=True)
            if fichiers:
                n, echecs = conversion.convertir_fichiers(fichiers, sortie)
            else:
                n, echecs = conversion.convertir_dossier(dossier, sortie)
            print(f"\n✅ {n} vidéo(s) converties en .mp4 → {sortie}")
            msg = f"✅ {n} vidéo(s) en .mp4 !\n\nRésultat :\n{sortie}"
            if echecs:
                msg += (f"\n\n⚠️ {len(echecs)} fichier(s) ignorés (vides/corrompus, "
                        "à re-télécharger).")
            self._notifier("Conversion terminée", msg)
        self._tache(job, "Conversion en MP4… (peut être long)", annulable=True)

    # ==================================================================
    #  Page : Convertir les images (JPG / PNG)
    # ==================================================================
    def _page_convertir_images(self):
        self._entete_page("Convertir les images",
                          "Convertit vos images en .jpg ou .png (HEIC iPhone inclus).")

        # ---------- Encart info ----------
        info = self._carte(pad=18)
        info_row = ctk.CTkFrame(info, fg_color="transparent")
        info_row.pack(fill="x")
        self._badge(info_row, "convertir", taille=46).pack(side="left", padx=(0, 14))
        info_txt = ctk.CTkFrame(info_row, fg_color="transparent")
        info_txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info_txt, text="Ce que fait ce module", font=(POLICE, 14, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            info_txt, justify="left", font=(POLICE, 13), text_color=MUTED,
            text="Convertit chaque image au format choisi (.jpg ou .png). Les photos iPhone\n"
                 "HEIC / HEIF — qui ne s'affichent pas sur Instagram — deviennent lisibles.\n"
                 "Vos fichiers originaux ne sont jamais modifiés.").pack(anchor="w", pady=(2, 0))

        # ---------- Étape 1 : choisir les images ----------
        c1 = self._carte()
        self._entete_etape(c1, 1, "Choisir les images",
                           "Un dossier entier, ou des images précises.")
        boutons = ctk.CTkFrame(c1, fg_color="transparent")
        boutons.pack(fill="x", pady=(16, 14))
        self._btn(boutons, "Importer un dossier…",
                  self._choisir_dossier_imgconv).pack(side="left", padx=(0, 10))
        self._btn(boutons, "Importer des images…",
                  self._choisir_images_imgconv).pack(side="left")
        zone = ctk.CTkFrame(c1, fg_color=ACCENT_SOFTER, corner_radius=12,
                            border_width=1, border_color=BORDER)
        zone.pack(fill="x")
        zone_row = ctk.CTkFrame(zone, fg_color="transparent")
        zone_row.pack(fill="x", padx=16, pady=14)
        self._badge(zone_row, "folder", taille=40).pack(side="left", padx=(0, 12))
        src = ctk.CTkFrame(zone_row, fg_color="transparent")
        src.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(src, text="SOURCE SÉLECTIONNÉE", font=(POLICE, 11, "bold"),
                     text_color=MUTED).pack(anchor="w")
        self.lbl_imgconv = ctk.CTkLabel(src, text=self._txt_source_imgconv(), justify="left",
                                        font=(POLICE, 14), text_color=TEXT)
        self.lbl_imgconv.pack(anchor="w", pady=(2, 0))

        # ---------- Étape 2 : format de sortie ----------
        c2 = self._carte()
        self._entete_etape(c2, 2, "Format de sortie", "Choisissez le format des images.")
        self.seg_format_imgconv = ctk.CTkSegmentedButton(
            c2, values=["JPG", "PNG"], selected_color=ACCENT_HOVER,
            selected_hover_color="#4A3FCC", font=(POLICE, 14))
        self.seg_format_imgconv.set("JPG")
        self.seg_format_imgconv.pack(anchor="w", pady=(16, 2))
        ctk.CTkLabel(c2, text="JPG = plus léger (recommandé pour Instagram) · "
                              "PNG = sans perte, garde la transparence.",
                     font=(POLICE, 12), text_color=MUTED).pack(anchor="w", pady=(4, 0))

        # ---------- Action ----------
        action = ctk.CTkFrame(self.contenu, fg_color="transparent")
        action.pack(fill="x", padx=36, pady=(14, 2))
        self._btn(action, "Convertir  →", self._lancer_imgconv, primaire=True).pack(fill="x")
        self._zone_journal()

    def _txt_source_imgconv(self):
        if self.fichiers_imgconv_src:
            return f"{len(self.fichiers_imgconv_src)} image(s) sélectionnée(s)"
        if self.dossier_imgconv_src:
            return f"Dossier : {self.dossier_imgconv_src}"
        return "Aucune source sélectionnée"

    def _choisir_dossier_imgconv(self):
        dossier = filedialog.askdirectory(title="Choisir le dossier d'images")
        if not dossier:
            return
        self.dossier_imgconv_src = dossier
        self.fichiers_imgconv_src = None
        self.lbl_imgconv.configure(text=self._txt_source_imgconv())

    def _choisir_images_imgconv(self):
        fichiers = filedialog.askopenfilenames(
            title="Choisir des images",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.heic *.heif *.bmp *.tif *.tiff"),
                       ("Tous", "*.*")])
        if not fichiers:
            return
        self.fichiers_imgconv_src = list(fichiers)
        self.dossier_imgconv_src = None
        self.lbl_imgconv.configure(text=self._txt_source_imgconv())

    def _lancer_imgconv(self):
        if not self.fichiers_imgconv_src and not self.dossier_imgconv_src:
            messagebox.showwarning("Convertir les images", "Importe d'abord un dossier ou des images.")
            return
        fmt = "png" if self.seg_format_imgconv.get() == "PNG" else "jpg"
        fichiers = list(self.fichiers_imgconv_src) if self.fichiers_imgconv_src else None
        dossier = self.dossier_imgconv_src
        sortie = os.path.join(self.dossier_sortie(), f"images ({fmt})")
        if dossier:
            a_src, a_out = os.path.abspath(dossier), os.path.abspath(sortie)
            if a_src == a_out or a_src.startswith(a_out + os.sep):
                messagebox.showerror("Dossier invalide",
                                     "Choisissez un autre dossier : la source ne peut pas être le "
                                     "dossier de sortie.")
                return
        if os.path.exists(sortie):
            if not messagebox.askyesno("Remplacer ?",
                                       f"Le dossier existe déjà et sera REMPLACÉ :\n{sortie}\n\nContinuer ?"):
                return

        def job():
            if os.path.exists(sortie):
                shutil.rmtree(sortie, ignore_errors=True)

            def progres(txt):
                self.file_log.put(("uniq_progres", txt))
            try:
                if fichiers:
                    res = unicite.convertir_images_fichiers(
                        fichiers, sortie, fmt, progress=progres,
                        doit_arreter=lambda: self._annule_tache)
                else:
                    res = unicite.convertir_images_dossier(
                        dossier, sortie, fmt, progress=progres,
                        doit_arreter=lambda: self._annule_tache)
            except Exception as e:
                print(f"\n[ERREUR] {e}")
                self._notifier("Convertir les images", str(e), erreur=True)
                return
            res["arrete"] = bool(self._annule_tache)
            self._fin_traitement("Images converties", res, sortie, f"image(s) en .{fmt}")
        self._tache(job, f"Conversion des images en .{fmt}…", annulable=True)

    # ==================================================================
    #  Page : Télécharger depuis Google Drive
    # ==================================================================
    def _page_drive(self):
        self._entete_page("Télécharger depuis Google Drive",
                          "Récupère les médias d'un dossier Drive partagé, classés par type.")

        # ---------- Encart info : partage requis + rangement ----------
        info = self._carte(pad=18)
        info_row = ctk.CTkFrame(info, fg_color="transparent")
        info_row.pack(fill="x")
        self._badge(info_row, "drive", taille=46).pack(side="left", padx=(0, 14))
        info_txt = ctk.CTkFrame(info_row, fg_color="transparent")
        info_txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info_txt, text="Avant de commencer", font=(POLICE, 14, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            info_txt, justify="left", font=(POLICE, 13), text_color=MUTED,
            text="Le dossier Google Drive doit être partagé « Tous les utilisateurs disposant\n"
                 "du lien ». Les médias seront rangés dans les sous-dossiers images et videos\n"
                 "— prêts pour Ranger ou Changer les métadonnées.").pack(anchor="w", pady=(2, 0))
        ctk.CTkButton(info_txt, text="Comment rendre un dossier Drive public ?  →",
                      command=self._popup_tuto_drive, height=28, anchor="w",
                      fg_color="transparent", text_color=ACCENT_HOVER,
                      hover_color=ACCENT_SOFTER, corner_radius=8,
                      font=(POLICE, 13, "bold")).pack(anchor="w", pady=(6, 0))

        # ---------- Étape 1 : coller le(s) lien(s) ----------
        c1 = self._carte()
        self._entete_etape(c1, 1, "Coller le(s) lien(s)",
                           "Le lien de partage du dossier Google Drive.")
        self.champ_drive = ctk.CTkTextbox(c1, height=90, font=(POLICE, 13), corner_radius=10)
        self.champ_drive.pack(fill="x", pady=(16, 0))
        ctk.CTkLabel(c1, text="Un lien par ligne : ils sont téléchargés l'un après l'autre, "
                              "dans le même dossier de sortie.",
                     font=(POLICE, 11), text_color=MUTED).pack(anchor="w", pady=(3, 0))

        # ---------- Étape 2 : options de téléchargement ----------
        c2 = self._carte()
        self._entete_etape(c2, 2, "Options de téléchargement",
                           "Ce que vous prenez, dans quel ordre, et combien.")

        ctk.CTkLabel(c2, text="Que télécharger ?", font=(POLICE, 13, "bold"),
                     text_color=ACCENT_HOVER).pack(anchor="w", pady=(16, 4))
        self.seg_drive = ctk.CTkSegmentedButton(c2, values=["Images", "Vidéos", "Les deux"],
                                                selected_color=ACCENT_HOVER,
                                                selected_hover_color="#4A3FCC", font=(POLICE, 14))
        self.seg_drive.set("Les deux")
        self.seg_drive.pack(anchor="w")

        ctk.CTkLabel(c2, text="Ordre", font=(POLICE, 13, "bold"),
                     text_color=ACCENT_HOVER).pack(anchor="w", pady=(14, 4))
        self.seg_tri_drive = ctk.CTkSegmentedButton(c2, values=["Plus récents", "Par nom"],
                                                    selected_color=ACCENT_HOVER,
                                                    selected_hover_color="#4A3FCC", font=(POLICE, 14))
        self.seg_tri_drive.set("Plus récents")
        self.seg_tri_drive.pack(anchor="w")
        ctk.CTkLabel(c2, text="« Plus récents » : prend d'abord les médias les plus "
                              "récemment ajoutés.",
                     font=(POLICE, 11), text_color=MUTED).pack(anchor="w", pady=(3, 0))

        ctk.CTkLabel(c2, text="Combien de médias prendre ? (vide = tout)",
                     font=(POLICE, 13, "bold"), text_color=ACCENT_HOVER).pack(anchor="w", pady=(14, 4))
        self.champ_nb_drive = ctk.CTkEntry(c2, width=160, height=42, font=(POLICE, 14),
                                           placeholder_text="Ex : 35  (ou vide)")
        self.champ_nb_drive.pack(anchor="w")

        # ---------- Actions : aperçu (secondaire) + télécharger (primaire pleine largeur) ----------
        action = ctk.CTkFrame(self.contenu, fg_color="transparent")
        action.pack(fill="x", padx=36, pady=(14, 2))
        row = ctk.CTkFrame(action, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        self._btn(row, "Voir le contenu", self._apercu_drive).pack(side="left")
        self._btn(action, "Télécharger  →", self._importer_drive, primaire=True).pack(fill="x")
        ctk.CTkLabel(
            action, justify="left", font=(POLICE, 11, "bold"), text_color=MUTED,
            text="Résultat dans « telechargement drive » (sous-dossiers images\\ et videos\\)."
        ).pack(anchor="w", pady=(8, 0))

        self._zone_journal()

    def _popup_tuto_drive(self):
        """Mini-tuto en images : rendre un dossier Google Drive public."""
        top = ctk.CTkToplevel(self)
        top.title("Rendre un dossier Drive public")
        top.geometry("700x660")
        top.configure(fg_color=BG)
        top.transient(self)
        self._modale_devant(top)
        top.after(200, lambda: top.winfo_exists() and top.grab_set())

        cont = ctk.CTkScrollableFrame(top, fg_color=BG)
        cont.pack(fill="both", expand=True, padx=18, pady=16)
        ctk.CTkLabel(cont, text="Rendre un dossier Google Drive public",
                     font=(POLICE, 20, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(cont, text="Deux étapes, directement dans Google Drive :",
                     font=(POLICE, 13), text_color=MUTED).pack(anchor="w", pady=(2, 14))

        self._tuto_imgs = []
        etapes = [
            (1, "Clic droit sur le dossier → Partager → Partager", "drive_etape1.png"),
            (2, "Accès général → « Tous les utilisateurs disposant du lien »", "drive_etape2.png"),
            (3, "Ouvrez le dossier, puis copiez le lien dans la barre d'adresse (encadré en rouge)", "drive_etape3.png"),
        ]
        for num, titre, fichier in etapes:
            self._entete_etape(cont, num, titre)
            try:
                from PIL import Image
                im = Image.open(chemin_ressource(os.path.join("assets", "tuto", fichier)))
                w, h = im.size
                lw = min(620, w)
                img = ctk.CTkImage(im, size=(lw, int(h * lw / w)))
                self._tuto_imgs.append(img)
                ctk.CTkLabel(cont, image=img, text="").pack(anchor="w", pady=(10, 20))
            except Exception:
                ctk.CTkLabel(cont, text="(image indisponible)", font=(POLICE, 12),
                             text_color=MUTED).pack(anchor="w", pady=(6, 16))

        ctk.CTkButton(cont, text="J'ai compris", command=top.destroy, height=44,
                      corner_radius=12, fg_color=ACCENT_HOVER, hover_color="#4A3FCC",
                      font=(POLICE, 15, "bold")).pack(fill="x", pady=(4, 6))

    def _liens_drive(self):
        """Liste des liens Drive saisis (un par ligne, vides ignorés)."""
        txt = self.champ_drive.get("1.0", "end")
        return [l.strip() for l in txt.splitlines() if l.strip()]

    def _apercu_drive(self):
        liens = self._liens_drive()
        if not liens:
            messagebox.showwarning("Google Drive", "Collez d'abord au moins un lien de dossier partagé.")
            return
        lien = liens[0]   # l'aperçu se base sur le PREMIER lien
        choix = self.seg_drive.get()
        prendre = {"Images": {"images"}, "Vidéos": {"videos"},
                   "Les deux": {"images", "videos"}}.get(choix, {"images", "videos"})
        txt_nb = self.champ_nb_drive.get().strip()
        limite = int(txt_nb) if (txt_nb.isdigit() and int(txt_nb) > 0) else None
        tri = "recent" if self.seg_tri_drive.get() == "Plus récents" else "nom"

        def job():
            import tempfile
            items = drive.lister_apercu(lien, prendre, limite, tri=tri)
            cap = items[:40]
            print(f"Chargement de l'aperçu ({len(cap)} vignette(s))…")
            vignettes = []
            for i, it in enumerate(cap, 1):
                tmp = os.path.join(tempfile.gettempdir(), f"helpva_thumb_{i}.jpg")
                ok = drive.telecharger_vignette(it["id"], tmp)
                vignettes.append((i, it["est_video"], tmp if ok else None))
            self.file_log.put(("drive_apercu", vignettes, len(items)))
        self._tache(job, "Chargement de l'aperçu…")

    def _popup_apercu_drive(self, vignettes, total):
        top = ctk.CTkToplevel(self)
        top.title("Aperçu Google Drive")
        top.geometry("790x650")
        top.configure(fg_color=BG)
        top.transient(self)
        self._modale_devant(top)
        top.after(200, lambda: top.winfo_exists() and top.grab_set())
        ctk.CTkLabel(top, text=f"Aperçu — {total} média(s) dans le dossier",
                     font=(POLICE, 19, "bold"), text_color=TEXT).pack(pady=(16, 2))
        if total > 40:
            ctk.CTkLabel(top, text="(aperçu des 40 premiers)", font=(POLICE, 12),
                         text_color=MUTED).pack()
        sc = ctk.CTkScrollableFrame(top, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=16, pady=12)
        self._thumb_refs = []
        from PIL import Image
        col = 5
        for idx, (num, est_video, path) in enumerate(vignettes):
            cell = ctk.CTkFrame(sc, fg_color=CARD, corner_radius=10,
                                border_width=1, border_color=BORDER)
            cell.grid(row=idx // col, column=idx % col, padx=6, pady=6)
            try:
                if path and os.path.isfile(path):
                    img = Image.open(path)
                    img.thumbnail((120, 120))
                    cimg = ctk.CTkImage(img, size=img.size)
                    self._thumb_refs.append(cimg)
                    ctk.CTkLabel(cell, image=cimg, text="").pack(padx=8, pady=(8, 2))
                else:
                    ctk.CTkLabel(cell, text=("vidéo" if est_video else "image"),
                                 font=(POLICE, 13), text_color=MUTED).pack(padx=28, pady=(26, 2))
            except Exception:
                ctk.CTkLabel(cell, text="?", font=(POLICE, 20)).pack(padx=28, pady=26)
            ctk.CTkLabel(cell, text=f"{'vidéo' if est_video else 'image'} {num}",
                         font=(POLICE, 11), text_color=MUTED).pack(pady=(0, 8))

    def _importer_drive(self):
        liens = self._liens_drive()
        if not liens:
            messagebox.showwarning("Google Drive", "Collez d'abord au moins un lien de dossier partagé.")
            return
        choix = self.seg_drive.get()
        prendre = {"Images": {"images"}, "Vidéos": {"videos"},
                   "Les deux": {"images", "videos"}}.get(choix, {"images", "videos"})
        txt_nb = self.champ_nb_drive.get().strip()
        limite = None
        if txt_nb:
            if not txt_nb.isdigit() or int(txt_nb) <= 0:
                messagebox.showwarning("Nombre", "Entre un nombre valide (ex : 35), ou laisse vide pour tout.")
                return
            limite = int(txt_nb)
        sortie = os.path.join(self.dossier_sortie(), "telechargement drive")
        tri = "recent" if self.seg_tri_drive.get() == "Plus récents" else "nom"

        def job():
            n = len(liens)
            print(f"Téléchargement de {n} dossier(s) Drive…")
            total_i = total_v = total_err = 0
            bloque = False
            for idx, lien in enumerate(liens, 1):
                if self._annule_tache:
                    print("⛔ Annulé — dossiers suivants ignorés.")
                    break
                print(f"\n=== Dossier {idx}/{n} ===")

                def prog(i, total, nom):
                    print(f"  [{i}/{total}] {nom}")
                try:
                    ni, nv, err = drive.telecharger_dossier(
                        lien, sortie, prendre=prendre, limite=limite, progress=prog,
                        tri=tri, doit_arreter=lambda: self._annule_tache)
                    total_i += ni; total_v += nv; total_err += err
                    print(f"  → Dossier {idx} : {ni} image(s), {nv} vidéo(s), {err} erreur(s)")
                except drive.BlocageGoogleError:
                    bloque = True
                    print("  ⛔ Google a bloqué les téléchargements depuis votre réseau.")
                    break   # inutile de continuer, tout échouera
                except Exception as e:
                    print(f"  ❌ Dossier {idx} échoué : {e}")
                    total_err += 1
            self.file_log.put(("drive_fini", sortie, total_i, total_v, total_err, bloque))
        self._tache(job, "Téléchargement Google Drive…", annulable=True)

    # ==================================================================
    #  Page : Paramètres
    # ==================================================================
    def _page_parametres(self):
        self._entete_page("Paramètres", "Dossier de sortie, raccourci et licence.")

        # --- Dossier de sortie ---
        ds = self._carte()
        ctk.CTkLabel(ds, text="Dossier de sortie", font=(POLICE, 14, "bold"),
                     text_color=ACCENT_HOVER).pack(anchor="w")
        perso = bool(self.params.get("dossier_sortie", "").strip())
        ctk.CTkLabel(ds, text="Emplacement où vos fichiers préparés sont enregistrés"
                     + ("" if perso else "  (par défaut : Bureau)"),
                     font=(POLICE, 13), text_color=MUTED).pack(anchor="w", pady=(6, 6))
        ctk.CTkLabel(ds, text=self.dossier_sortie(), font=("Consolas", 12),
                     text_color=TEXT, wraplength=560, justify="left").pack(anchor="w", pady=(0, 10))
        ligne_ds = ctk.CTkFrame(ds, fg_color="transparent")
        ligne_ds.pack(anchor="w")
        self._btn(ligne_ds, "Changer…", self._changer_dossier_sortie, primaire=True).pack(side="left")
        self._btn(ligne_ds, "Ouvrir", self._ouvrir_dossier_sortie).pack(side="left", padx=(8, 0))
        if perso:
            self._btn(ligne_ds, "Réinitialiser (Bureau)", self._reinit_dossier_sortie).pack(side="left", padx=(8, 0))

        # --- Raccourci sur le Bureau ---
        rc = self._carte()
        ctk.CTkLabel(rc, text="Raccourci sur le Bureau", font=(POLICE, 14, "bold"),
                     text_color=ACCENT_HOVER).pack(anchor="w")
        ctk.CTkLabel(rc, text="Ouvrez HelpVA en un double-clic depuis votre Bureau.",
                     font=(POLICE, 13), text_color=MUTED).pack(anchor="w", pady=(6, 10))
        self._btn(rc, "Créer le raccourci", self._creer_raccourci_manuel).pack(anchor="w")

        # --- Licence & abonnement ---
        lic = self._carte()
        ctk.CTkLabel(lic, text="Licence & abonnement", font=(POLICE, 14, "bold"),
                     text_color=ACCENT_HOVER).pack(anchor="w")
        nom_det = (self.statut or {}).get("nom")
        if nom_det:
            ctk.CTkLabel(lic, text=f"Détenteur : {nom_det}", font=(POLICE, 15, "bold"),
                         text_color=TEXT).pack(anchor="w", pady=(8, 0))
        typ = (self.statut or {}).get("type")
        fin = (self.statut or {}).get("expire_le")
        if typ == "vie" or not fin:
            ctk.CTkLabel(lic, text="Abonnement à vie — sans expiration",
                         font=(POLICE, 15), text_color=TEXT).pack(anchor="w", pady=(8, 12))
        else:
            debut = None
            if typ == "an":
                debut = licence._ajouter_mois(fin, -12)
            elif typ == "mois":
                debut = licence._ajouter_mois(fin, -1)
            if debut:
                ctk.CTkLabel(lic, text=f"Début de l'abonnement : {_date_fr(debut)}",
                             font=(POLICE, 15), text_color=TEXT).pack(anchor="w", pady=(8, 0))
            ctk.CTkLabel(lic, text=f"Fin de l'abonnement : {_date_fr(fin)}",
                         font=(POLICE, 15), text_color=TEXT).pack(anchor="w", pady=(2, 12))

        # Résilier / changer de licence
        ctk.CTkButton(lic, text="Résilier / changer de licence", command=self._resilier_licence,
                      fg_color=("#FDECEA", "#3A1E1E"), text_color="#E5484D", hover_color="#F8D7D5",
                      height=40, corner_radius=10, font=(POLICE, 13)).pack(anchor="w", pady=(14, 0))

    def _resilier_licence(self):
        if not messagebox.askyesno(
                "Résilier la licence",
                "Cela SUPPRIME la licence de ce PC et revient à l'écran d'activation.\n\n"
                "⚠️ Cette licence sera définitivement bloquée : il faudra un "
                "NOUVEAU code pour réactiver.\n\nContinuer ?"):
            return
        licence.supprimer_licence()
        self.statut = {"ok": False, "raison": "pas_active"}
        self._router_licence()   # -> écran d'activation

    # ---- re-contrôle périodique de l'abonnement ----
    def _planifier_verif_periodique(self):
        if self._timer_verif:
            try:
                self.after_cancel(self._timer_verif)
            except Exception:
                pass
            self._timer_verif = None
        self._echecs_verif = 0
        if self.statut.get("type") in ("mois", "an", "essai"):
            self._timer_verif = self.after(INTERVALLE_VERIF_MS, self._verif_periodique)

    def _verif_periodique(self):
        def job():
            self.file_log.put(("verif_licence", licence.verifier()))
        threading.Thread(target=job, daemon=True).start()

    def _traiter_verif(self, st):
        if st["ok"]:
            self.statut = st
            self._echecs_verif = 0
            if st.get("hors_ligne"):
                # Toléré (hors-ligne) : on NE bloque PAS. Bandeau discret +
                # re-contrôle rapproché pour effacer le bandeau au retour du réseau.
                self._montrer_bandeau_horsligne(True)
                self._timer_verif = self.after(RETRY_VERIF_MS, self._verif_periodique)
            else:
                self._montrer_bandeau_horsligne(False)
                self._planifier_verif_periodique()
            return
        # Non OK : résiliée / suspendue / expirée / hors-ligne au-delà de la tolérance.
        self.statut = st
        self._montrer_bandeau_horsligne(False)
        self._vider()
        if st["raison"] == "pas_internet":
            self._ecran_internet()
        else:
            self._ecran_activation()

    # ==================================================================
    #  Éditeur de calendrier (semaines, max 4)
    # ==================================================================
    def ouvrir_editeur_calendrier(self):
        """Éditeur de calendrier — UI en tkinter/ttk CLASSIQUE (widgets légers)
        pour un rendu instantané (ajout/suppression/duplication de semaines)."""
        import copy
        _dark = ctk.get_appearance_mode() == "Dark"
        def _col(t):
            return (t[1] if _dark else t[0]) if isinstance(t, (tuple, list)) else t
        cBG, cCARD, cTEXT, cMUTED = _col(BG), _col(CARD), _col(TEXT), _col(MUTED)
        cACCENT, cHOVER = _col(ACCENT), _col(ACCENT_HOVER)
        cSOFT, cSOFTER = _col(ACCENT_SOFT), _col(ACCENT_SOFTER)
        cBORDER, cGREEN = _col(BORDER), _col(GREEN)
        cal = calendrier.charger_calendrier()
        courant = {"nom": next(iter(cal), None)}

        top = tk.Toplevel(self)
        top.title("Calendrier")
        top.geometry("760x780")
        top.configure(bg=cBG)
        top.transient(self)
        self._modale_devant(top)
        top.after(200, lambda: top.winfo_exists() and top.grab_set())

        def bouton(parent, texte, cmd, genre="doux", **kw):
            couleurs = {"doux": (cSOFT, cHOVER),
                        "primaire": (cACCENT, "#FFFFFF"),
                        "danger": ("#FDECEA", "#E5484D")}
            bg, fg = couleurs.get(genre, couleurs["doux"])
            kw.setdefault("font", (POLICE, 10))
            return tk.Button(parent, text=texte, command=cmd, bg=bg, fg=fg,
                             activebackground=bg, activeforeground=fg, relief="flat",
                             bd=0, cursor="hand2", padx=9, pady=3, **kw)

        # --- en-tête ---
        tk.Label(top, text="Ajuster le calendrier", bg=cBG, fg=cTEXT,
                 font=(POLICE, 20, "bold")).pack(anchor="w", padx=22, pady=(16, 0))
        tk.Label(top, text="Autant de semaines que vous voulez : dupliquez ou supprimez-les.",
                 bg=cBG, fg=cMUTED, font=(POLICE, 12)).pack(anchor="w", padx=22, pady=(2, 8))
        besoins_lbl = tk.Label(top, text="", bg=cBG, fg=cHOVER, font=(POLICE, 13, "bold"))
        besoins_lbl.pack(anchor="w", padx=22, pady=(0, 8))

        # --- Contenu : « Vidéos uniquement » (tout reels) ou « Images + Vidéos » ---
        def _mode_actuel():
            for jours in cal.values():
                for creneaux in jours.values():
                    for cr in creneaux:
                        if cr.get("type") != "reel":
                            return "mixte"
            return "reels"

        mode = {"val": _mode_actuel()}
        mode_frame = tk.Frame(top, bg=cBG)
        mode_frame.pack(anchor="w", padx=22, pady=(0, 10))
        tk.Label(mode_frame, text="Contenu :", bg=cBG, fg=cTEXT,
                 font=(POLICE, 11, "bold")).pack(side="left", padx=(0, 8))

        def construire_mode():
            for w in mode_frame.winfo_children()[1:]:   # garde le label "Contenu :"
                w.destroy()
            for cle, libelle in (("mixte", "Images + Vidéos"), ("reels", "Vidéos uniquement")):
                actif = mode["val"] == cle
                tk.Button(mode_frame, text=libelle,
                          command=lambda c=cle: appliquer_mode(c),
                          bg=(cACCENT if actif else cSOFT),
                          fg=("#FFFFFF" if actif else cHOVER),
                          activebackground=(cACCENT if actif else cSOFT),
                          activeforeground=("#FFFFFF" if actif else cHOVER),
                          relief="flat", bd=0, cursor="hand2",
                          font=(POLICE, 10, "bold"), padx=9, pady=3).pack(side="left", padx=(0, 6))

        def appliquer_mode(nouveau):
            if nouveau == mode["val"]:
                return
            if nouveau == "reels":
                if not messagebox.askyesno(
                        "Vidéos uniquement",
                        "Mettre TOUT le calendrier en reels (vidéos) ?\n"
                        "Les stories, stories CTA et carrousels deviendront des reels."):
                    return
                for jours in cal.values():
                    for creneaux in jours.values():
                        for cr in creneaux:
                            cr["type"] = "reel"
            else:
                if not messagebox.askyesno(
                        "Images + Vidéos",
                        "Revenir au calendrier mixte par défaut (images + vidéos) ?\n"
                        "Cela REMPLACE le calendrier actuel."):
                    return
                cal.clear()
                cal.update(copy.deepcopy(calendrier.CALENDRIER))
                courant["nom"] = next(iter(cal), None)
            mode["val"] = nouveau
            construire_mode()
            construire_barre()
            afficher_semaine(courant["nom"])

        # --- bas : Réinitialiser / Enregistrer (réservé en premier -> toujours visible) ---
        bas = tk.Frame(top, bg=cBG)
        bas.pack(side="bottom", fill="x", padx=22, pady=12)

        # --- barre des semaines ---
        barre = tk.Frame(top, bg=cBG)
        barre.pack(fill="x", padx=18, pady=(0, 6))

        # --- zone défilable (contenu de la semaine active) ---
        zone = tk.Frame(top, bg=cCARD)
        zone.pack(fill="both", expand=True, padx=18, pady=4)
        canvas = tk.Canvas(zone, bg=cCARD, highlightthickness=0)
        vsb = tk.Scrollbar(zone, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=cCARD)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        top.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        def maj_besoins():
            n = rangement.compter(cal)
            img = sum(n[t] * rangement.medias_par_creneau(t) for t in n if t != "reel")
            besoins_lbl.configure(text=f"Besoins : {n['reel']} vidéo(s)   ·   {img} image(s)   "
                                       f"({n['story']} stories + {n['story_cta']} CTA + "
                                       f"{n['carousel']} carrousels)")

        def libelle_semaine(nom):
            num = nom.replace("semaine-", "")
            return f"Semaine {int(num) if num.isdigit() else num}"

        def renumeroter():
            vals = list(cal.values())
            cal.clear()
            for i, j in enumerate(vals, 1):
                cal[f"semaine-{i:02d}"] = j

        def selectionner(nom):
            courant["nom"] = nom
            construire_barre()
            afficher_semaine(nom)

        def dupliquer(nom):
            vals = list(cal.values())
            idx = list(cal.keys()).index(nom)
            vals.insert(idx + 1, copy.deepcopy(cal[nom]))
            cal.clear()
            for i, j in enumerate(vals, 1):
                cal[f"semaine-{i:02d}"] = j
            selectionner(list(cal.keys())[idx + 1])

        def supprimer_sem(nom):
            if len(cal) <= 1:
                messagebox.showwarning("Semaines", "Il faut au moins 1 semaine.")
                return
            if not messagebox.askyesno("Supprimer",
                                       f"Supprimer la {libelle_semaine(nom).lower()} ?"):
                return
            idx = list(cal.keys()).index(nom)
            del cal[nom]
            renumeroter()
            noms = list(cal.keys())
            selectionner(noms[min(idx, len(noms) - 1)])

        police_onglet = tkfont.Font(family=POLICE, size=10, weight="bold")
        largeur_barre = {"val": 0}

        def construire_barre():
            for w in barre.winfo_children():
                w.destroy()
            dispo = barre.winfo_width()
            if dispo <= 1:                       # fenêtre pas encore affichée
                dispo = top.winfo_width() - 36 if top.winfo_width() > 1 else 720
            largeur_barre["val"] = dispo

            # Nombre de lignes d'onglets nécessaires à cette largeur.
            lignes_req, occ = 1, 0
            for nom in cal:
                l_btn = police_onglet.measure(libelle_semaine(nom)) + 2 * 9 + 12
                if occ and occ + l_btn > dispo:
                    lignes_req, occ = lignes_req + 1, 0
                occ += l_btn
            if lignes_req > 2:
                construire_selecteur()
                return

            ligne, occupe = None, dispo + 1
            for nom in cal:
                actif = nom == courant["nom"]
                texte = libelle_semaine(nom)
                l_btn = police_onglet.measure(texte) + 2 * 9 + 12   # + marges
                if ligne is None or occupe + l_btn > dispo:
                    ligne = tk.Frame(barre, bg=cBG)
                    ligne.pack(anchor="w", pady=(0, 5))
                    occupe = 0
                tk.Button(ligne, text=texte,
                          command=lambda n=nom: selectionner(n),
                          bg=(cACCENT if actif else cSOFT),
                          fg=("#FFFFFF" if actif else cHOVER),
                          activebackground=(cACCENT if actif else cSOFT),
                          activeforeground=("#FFFFFF" if actif else cHOVER),
                          relief="flat", bd=0, cursor="hand2",
                          font=police_onglet, padx=9, pady=3).pack(side="left", padx=(0, 6))
                occupe += l_btn

        def construire_selecteur():
            """Beaucoup de semaines : ◀ [Semaine N ▾] ▶ sur une seule ligne."""
            noms = list(cal)
            idx = noms.index(courant["nom"]) if courant["nom"] in noms else 0
            libs = [libelle_semaine(n) for n in noms]
            ligne = tk.Frame(barre, bg=cBG)
            ligne.pack(anchor="w", pady=(0, 5))
            prec = bouton(ligne, "◀", lambda: selectionner(noms[idx - 1]),
                          font=(POLICE, 10, "bold"))
            prec.pack(side="left")
            var = tk.StringVar(value=libs[idx])
            cb = ttk.Combobox(ligne, values=libs, textvariable=var, state="readonly",
                              width=14, height=15, font=(POLICE, 10))
            cb.pack(side="left", padx=6)
            cb.bind("<<ComboboxSelected>>", lambda ev: selectionner(noms[libs.index(var.get())]))
            suiv = bouton(ligne, "▶", lambda: selectionner(noms[idx + 1]),
                          font=(POLICE, 10, "bold"))
            suiv.pack(side="left")
            if idx == 0:
                prec.configure(state="disabled")
            if idx == len(noms) - 1:
                suiv.configure(state="disabled")
            tk.Label(ligne, text=f"{len(noms)} semaines", bg=cBG, fg=cMUTED,
                     font=(POLICE, 10)).pack(side="left", padx=(10, 0))

        def _barre_redimensionnee(ev):
            if abs(ev.width - largeur_barre["val"]) > 4:
                construire_barre()
        barre.bind("<Configure>", _barre_redimensionnee)

        def _set_type(cr, val):
            cr["type"] = val
            maj_besoins()

        def _rendre_ligne(cont, cr):
            """Une ligne créneau : heure + type + supprimer. Widgets tk = rapide."""
            row = tk.Frame(cont, bg=cCARD)
            row.pack(fill="x", pady=3, padx=(20, 8))
            e = tk.Entry(row, width=7, font=(POLICE, 11), relief="solid", bd=1)
            e.insert(0, cr["heure"])
            e.pack(side="left")
            e.bind("<KeyRelease>", lambda ev, c=cr, en=e: c.__setitem__("heure", en.get()))
            libs = rangement.LIBELLE_CRENEAU
            var = tk.StringVar(value=libs.get(cr["type"], cr["type"]))
            cb = ttk.Combobox(row, values=list(libs.values()), textvariable=var,
                              state="readonly", width=11, font=(POLICE, 10))
            cb.pack(side="left", padx=10)
            vers_type = {v: k for k, v in libs.items()}
            cb.bind("<<ComboboxSelected>>",
                    lambda ev, c=cr, v=var: _set_type(c, vers_type.get(v.get(), v.get())))
            tk.Button(row, text="×", command=lambda c=cr, r=row: supprimer_creneau(c, r),
                      bg="#FDECEA", fg="#E5484D", activebackground="#F8D7D5",
                      activeforeground="#E5484D", relief="flat", bd=0, cursor="hand2",
                      font=(POLICE, 10, "bold"), width=2, pady=0).pack(side="left")

        def ajouter_creneau(j, cont):
            cr = {"heure": "12h00", "type": "reel"}
            cal[courant["nom"]][j].append(cr)
            _rendre_ligne(cont, cr)          # AJOUTE une seule ligne -> instantané
            maj_besoins()

        def supprimer_creneau(cr, row):
            for jours in cal.get(courant["nom"], {}).values():
                for k, c in enumerate(jours):
                    if c is cr:
                        del jours[k]
                        break
            row.destroy()                    # RETIRE une seule ligne -> instantané
            maj_besoins()

        def afficher_semaine(nom):
            for w in inner.winfo_children():
                w.destroy()
            if nom is None or nom not in cal:
                return
            act = tk.Frame(inner, bg=cCARD)
            act.pack(fill="x", pady=(10, 6), padx=16)
            bouton(act, "Dupliquer cette semaine", lambda: dupliquer(nom)).pack(side="left", padx=(0, 8))
            bouton(act, "Supprimer cette semaine", lambda: supprimer_sem(nom),
                   genre="danger").pack(side="left")
            for nom_jour, creneaux in cal[nom].items():
                hj = tk.Frame(inner, bg=cCARD)
                hj.pack(fill="x", pady=(12, 2), padx=16)
                tk.Label(hj, text=nom_jour.capitalize(), bg=cCARD, fg=cTEXT,
                         font=(POLICE, 13, "bold")).pack(side="left")
                cont = tk.Frame(inner, bg=cCARD)
                bouton(hj, "+ Ajouter un créneau",
                       lambda j=nom_jour, ct=cont: ajouter_creneau(j, ct)).pack(side="left", padx=12)
                cont.pack(fill="x")
                for cr in creneaux:
                    _rendre_ligne(cont, cr)
            canvas.yview_moveto(0)
            maj_besoins()

        def reinit():
            from agent.calendrier import CALENDRIER
            cal.clear()
            cal.update(copy.deepcopy(CALENDRIER))
            courant["nom"] = next(iter(cal), None)
            mode["val"] = "mixte"
            construire_mode()
            construire_barre()
            afficher_semaine(courant["nom"])

        import json as _json
        instantane = {"val": _json.dumps(cal, sort_keys=True)}

        def fermer():
            if _json.dumps(cal, sort_keys=True) != instantane["val"]:
                rep_ = messagebox.askyesnocancel(
                    "Calendrier", "Enregistrer les modifications du calendrier ?", parent=top)
                if rep_ is None:
                    return
                if rep_:
                    enreg()
                    return
            top.destroy()
        top.protocol("WM_DELETE_WINDOW", fermer)

        def enreg():
            calendrier.sauver_calendrier(cal)
            messagebox.showinfo("Calendrier", f"Enregistré ({len(cal)} semaine(s)).\n"
                                "Appliqué au prochain rangement.")
            top.destroy()
            self._maj_besoins_ranger()   # la page Ranger reste à jour

        bouton(bas, "Réinitialiser", reinit).pack(side="left")
        bouton(bas, "Enregistrer", enreg, genre="primaire",
               font=(POLICE, 11, "bold")).pack(side="right")

        construire_mode()
        construire_barre()
        afficher_semaine(courant["nom"])


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
