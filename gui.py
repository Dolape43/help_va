"""
HelpVA — interface graphique, pas à pas.

Parcours :
  1) Écran de bienvenue -> bouton "Commencer"
  2) "Que veux-tu faire ?" :
        - Ranger les médias
        - Uniquiser les images (modifier les métadonnées)
        - Publier le contenu   (seule action qui demande la clé API)
Les résultats sont écrits dans un dossier "HelpVA" sur le Bureau.

Lancement : python gui.py   (ou double-clic sur l'exe une fois empaqueté)
"""

import os
import sys
import queue
import shutil
import tempfile
import threading
import time
from datetime import datetime, date
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from agent import parametres, adspower, instagram, calendrier, legendes, montage
from agent import ranger as rangement
from agent import unicite
from agent import planificateur
from agent import licence
from agent import version
from agent import demarrage
from agent.main import navigateur_du_profil

IMAGES_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEOS_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

# Re-contrôle de l'abonnement quand l'app reste ouverte longtemps.
# Fréquence réglable pour les tests (variable d'env) ; défaut produit = 5 h.
try:
    INTERVALLE_VERIF_MS = int(os.environ.get("HELPVA_VERIF_MS", str(5 * 60 * 60 * 1000)))
except ValueError:
    INTERVALLE_VERIF_MS = 5 * 60 * 60 * 1000
RETRY_VERIF_MS = 5 * 60 * 1000             # +5 min si internet coupé (tolérance)
MAX_ECHECS_VERIF = 3                       # après ~15 min sans internet -> on bloque

POLICE = "Segoe UI"

# Palette (reprend les couleurs du logo : violet -> bleu)
ACCENT = "#5B4FE3"        # violet-indigo
ACCENT_FONCE = "#4A3FCC"
BLEU = "#3B82F6"
BLEU_FONCE = "#2E6BD6"
BG = "#F4F5FB"            # fond très clair lavande
TEXTE = "#22243A"
GRIS = "#6B7280"


def chemin_ressource(rel: str) -> str:
    """Chemin d'une ressource, compatible PyInstaller (--add-data)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def dossier_sortie() -> str:
    """Dossier de travail sur le Bureau (créé au besoin)."""
    bureau = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(bureau):
        bureau = os.path.expanduser("~")
    d = os.path.join(bureau, "HelpVA")
    os.makedirs(d, exist_ok=True)
    return d


class FluxVersLog:
    """Redirige les print() vers la zone de log (via une file d'attente)."""
    def __init__(self, file):
        self.file = file

    def write(self, texte):
        if texte:
            self.file.put(texte)

    def flush(self):
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"HelpVA v{version.VERSION}")
        self.root.geometry("760x760")
        self.file_log = queue.Queue()
        self.profils = {}
        self.params = parametres.charger()
        self.modele = self.params.get("modele", "")
        self.genre = self.params.get("genre", "feminin")
        self.dossier_ranger_src = None   # dossier importé pour "Ranger"
        self.dossier_uniq_src = None     # dossier importé pour "Uniquiser"
        self.occupe = False
        self.log = None
        self.planif_actif = False        # automatisation horaire en cours ?
        self.planif_thread = None
        self._timer_verif = None         # timer de re-contrôle abonnement
        self._echecs_verif = 0
        self.dossier_planif_src = None   # dossier "ranger" importé pour l'auto
        self._auto_resume_fait = False   # reprise auto tentée une seule fois

        self.root.configure(bg=BG)
        self._styles()
        try:
            self.root.iconbitmap(chemin_ressource("assets/logo.ico"))
        except Exception:
            pass

        self._entete()

        # Zone de contenu SCROLLABLE (canvas + scrollbar + frame interne).
        wrap = ttk.Frame(self.root)
        wrap.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.conteneur = ttk.Frame(self._canvas, padding=20)
        self._fenetre_id = self._canvas.create_window((0, 0), window=self.conteneur, anchor="nw")
        self.conteneur.bind(
            "<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>", lambda e: self._canvas.itemconfig(self._fenetre_id, width=e.width))
        # Molette de la souris pour défiler.
        self._canvas.bind_all(
            "<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-e.delta / 120), "units"))

        sys.stdout = FluxVersLog(self.file_log)
        sys.stderr = FluxVersLog(self.file_log)
        self.root.after(100, self._vider_file_log)

        # Verrou de licence : on vérifie au démarrage (et il faut internet
        # pour les abonnements mois/an).
        self.statut_licence = {"ok": False, "raison": "pas_active"}
        self._router_licence()

    # --------------------------------------------------------------- styles

    def _styles(self):
        self.root.option_add("*Font", (POLICE, 11))
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        # Fonds
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=TEXTE)
        s.configure("TLabelframe", background=BG)
        s.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=(POLICE, 11, "bold"))
        s.configure("TRadiobutton", background=BG)
        s.configure("TCheckbutton", background=BG)

        # Boutons — taille uniforme, pas trop gros
        s.configure("TButton", font=(POLICE, 11), padding=(10, 6))
        # Bouton principal d'une action (bleu)
        s.configure("Primaire.TButton", font=(POLICE, 11, "bold"),
                    padding=(14, 8), background=BLEU, foreground="white", borderwidth=0)
        s.map("Primaire.TButton", background=[("active", BLEU_FONCE)])
        # Boutons du menu "Que veux-tu faire ?" (violet, uniformes)
        s.configure("Menu.TButton", font=(POLICE, 12, "bold"),
                    padding=(14, 14), background=ACCENT, foreground="white", borderwidth=0)
        s.map("Menu.TButton", background=[("active", ACCENT_FONCE)])

        # Bouton "Retour" / "Paramètres" : discret, cohérent partout
        s.configure("Retour.TButton", font=(POLICE, 10), padding=(8, 4),
                    background=BG, foreground=ACCENT, borderwidth=0)
        s.map("Retour.TButton", background=[("active", "#E7E8F6")])

        # Types de post : plus grands
        s.configure("Type.TRadiobutton", background=BG, font=(POLICE, 12), padding=(2, 4))

        # Barre de progression (couleur accent)
        s.configure("TProgressbar", background=ACCENT, troughcolor="#E7E8F6")

        # Titres colorés
        s.configure("Titre.TLabel", font=(POLICE, 22, "bold"), foreground=ACCENT)
        s.configure("Sous.TLabel", font=(POLICE, 11), foreground=GRIS)
        s.configure("H2.TLabel", font=(POLICE, 15, "bold"), foreground=ACCENT)
        # Grand titre du menu (foncé, à gauche)
        s.configure("Grand.TLabel", font=(POLICE, 26, "bold"), foreground=TEXTE)
        # Petit intitulé de groupe (au-dessus d'une rangée de boutons)
        s.configure("Groupe.TLabel", font=(POLICE, 12, "bold"), foreground=GRIS)

    def _entete(self):
        """Barre d'en-tête colorée avec le logo + le nom."""
        barre = tk.Frame(self.root, bg=ACCENT, height=56)
        barre.pack(fill="x")
        barre.pack_propagate(False)
        try:
            from PIL import Image, ImageTk
            img = Image.open(chemin_ressource("assets/logo.png")).convert("RGBA")
            img.thumbnail((38, 38))
            self._logo_entete = ImageTk.PhotoImage(img)
            tk.Label(barre, image=self._logo_entete, bg=ACCENT).pack(side="left", padx=(14, 8))
        except Exception:
            pass
        tk.Label(barre, text="HelpVA", bg=ACCENT, fg="white",
                 font=(POLICE, 16, "bold")).pack(side="left")
        tk.Label(barre, text=f"v{version.VERSION}", bg=ACCENT, fg="#E6E0FF",
                 font=(POLICE, 9)).pack(side="right", padx=14)

    # ------------------------------------------------------------ navigation

    def montrer(self, builder):
        for w in self.conteneur.winfo_children():
            w.destroy()
        self.log = None
        builder()
        # Revenir en haut et recalculer la zone défilable.
        self.conteneur.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._canvas.yview_moveto(0)

    def dossier_modele(self) -> str:
        """Dossier de travail du modèle en cours (sur le Bureau)."""
        d = os.path.join(dossier_sortie(), self.modele or "SansNom")
        os.makedirs(d, exist_ok=True)
        return d

    def _barre_retour(self):
        ttk.Button(self.conteneur, text="← Retour", style="Retour.TButton",
                   command=lambda: self.montrer(self.ecran_menu)).pack(anchor="w")

    def _zone_log(self):
        cadre = ttk.LabelFrame(self.conteneur, text="Journal", padding=6)
        cadre.pack(fill="both", expand=True, pady=(12, 0))
        self.log = tk.Text(cadre, height=10, wrap="word", state="disabled",
                           font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(cadre, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log["yscrollcommand"] = sb.set

    # ---------------------------------------------------------------- écrans

    def _router_licence(self):
        """Vérifie la licence et affiche l'écran adapté."""
        self.statut_licence = licence.verifier()
        raison = self.statut_licence["raison"]
        if self.statut_licence["ok"]:
            self.montrer(self.ecran_bienvenue)
            self._planifier_verif_periodique()
            # Reprise automatique de l'automatisation (une seule fois).
            if not self._auto_resume_fait:
                self._auto_resume_fait = True
                self.root.after(3000, self._reprendre_auto)
        elif raison == "pas_internet":
            self.montrer(self.ecran_internet)
        else:  # pas_active / invalide / mauvais_pc / expire
            self.montrer(self.ecran_activation)

    # --- Re-contrôle périodique de l'abonnement (app laissée ouverte) ---

    def _planifier_verif_periodique(self):
        """Programme un contrôle en ligne dans 5 h (seulement pour mois/an)."""
        if getattr(self, "_timer_verif", None):
            try:
                self.root.after_cancel(self._timer_verif)
            except Exception:
                pass
            self._timer_verif = None
        self._echecs_verif = 0
        # "à vie" n'a rien à re-vérifier -> pas de timer.
        if self.statut_licence.get("type") in ("mois", "an"):
            self._timer_verif = self.root.after(INTERVALLE_VERIF_MS, self._verif_periodique)

    def _verif_periodique(self):
        """Lance la vérif en ligne dans un thread (ne fige pas l'interface)."""
        def job():
            st = licence.verifier()
            self.file_log.put(("verif_licence", st))
        threading.Thread(target=job, daemon=True).start()

    def _traiter_verif(self, st):
        """Réagit au résultat du contrôle périodique."""
        if st["ok"]:
            self.statut_licence = st
            self._planifier_verif_periodique()   # prochain dans 5 h
            return
        if st["raison"] == "pas_internet":
            # Micro-coupure ? On retente quelques fois avant de bloquer.
            self._echecs_verif = getattr(self, "_echecs_verif", 0) + 1
            if self._echecs_verif <= MAX_ECHECS_VERIF:
                self._timer_verif = self.root.after(RETRY_VERIF_MS, self._verif_periodique)
                return
        # Expiré, ou internet toujours absent après plusieurs essais -> on bloque.
        self.planif_actif = False        # coupe une éventuelle automatisation
        self.statut_licence = st
        if st["raison"] == "pas_internet":
            self.montrer(self.ecran_internet)
        else:
            self.montrer(self.ecran_activation)

    def ecran_internet(self):
        cadre = ttk.Frame(self.conteneur)
        cadre.pack(expand=True)
        try:
            from PIL import Image, ImageTk
            img = Image.open(chemin_ressource("assets/logo.png")).convert("RGBA")
            img.thumbnail((110, 110))
            self._logo = ImageTk.PhotoImage(img)
            ttk.Label(cadre, image=self._logo).pack(pady=(10, 6))
        except Exception:
            pass
        ttk.Label(cadre, text="Connexion internet requise", style="Titre.TLabel").pack(pady=(6, 6))
        ttk.Label(cadre, style="Sous.TLabel", justify="center",
                  text="HelpVA doit vérifier ton abonnement en ligne.\n"
                       "Connecte-toi à internet, puis clique « Réessayer ».").pack(pady=(0, 16))
        ttk.Button(cadre, text="Réessayer", style="Primaire.TButton", width=18,
                   command=self._router_licence).pack()

    def ecran_activation(self):
        cadre = ttk.Frame(self.conteneur)
        cadre.pack(expand=True, fill="x")

        # Logo (si présent)
        try:
            from PIL import Image, ImageTk
            img = Image.open(chemin_ressource("assets/logo.png")).convert("RGBA")
            img.thumbnail((110, 110))
            self._logo = ImageTk.PhotoImage(img)
            ttk.Label(cadre, image=self._logo).pack(pady=(6, 4))
        except Exception:
            pass

        raison = self.statut_licence.get("raison", "pas_active")
        if raison == "expire":
            exp = self.statut_licence.get("expire_le")
            titre = "Abonnement expiré"
            sous = (f"Ton abonnement a expiré le {exp.strftime('%d/%m/%Y') if exp else ''}.\n"
                    "Renvoie ton empreinte au vendeur pour le renouveler.")
        elif raison == "mauvais_pc":
            titre = "Licence non valable pour ce PC"
            sous = ("Cette licence a été faite pour un autre PC.\n"
                    "Envoie l'empreinte ci-dessous au vendeur.")
        else:
            titre = "Activation de HelpVA"
            sous = ("Ce logiciel est lié à CE PC.\n"
                    "Envoie l'empreinte ci-dessous au vendeur pour recevoir ta licence.")
        ttk.Label(cadre, text=titre, style="Titre.TLabel").pack(pady=(4, 4))
        ttk.Label(cadre, style="Sous.TLabel", justify="center", text=sous).pack(pady=(0, 14))

        emp = licence.empreinte_machine()

        # Empreinte machine (lecture seule) + bouton Copier.
        bloc = ttk.LabelFrame(cadre, text="1) Empreinte de ce PC (à envoyer)", padding=10)
        bloc.pack(fill="x", padx=10)
        champ_emp = ttk.Entry(bloc, width=30, font=("Consolas", 13), justify="center")
        champ_emp.insert(0, emp)
        champ_emp.configure(state="readonly")
        champ_emp.pack(side="left", padx=(0, 8), pady=2)

        def copier():
            self.root.clipboard_clear()
            self.root.clipboard_append(emp)
            messagebox.showinfo("Copié", "Empreinte copiée.\nEnvoie-la au vendeur.")
        ttk.Button(bloc, text="Copier", command=copier).pack(side="left")

        # Saisie de la licence + activation.
        bloc2 = ttk.LabelFrame(cadre, text="2) Colle ta licence reçue, puis Active", padding=10)
        bloc2.pack(fill="x", padx=10, pady=(12, 0))
        self.champ_licence = tk.Text(bloc2, height=3, width=52, font=("Consolas", 10), wrap="char")
        self.champ_licence.pack(fill="x", pady=(0, 8))
        ttk.Button(bloc2, text="Activer HelpVA", style="Primaire.TButton",
                   command=self._activer).pack()

        ttk.Label(cadre, style="Sous.TLabel", justify="center",
                  text="Une licence ne fonctionne que sur le PC dont elle vient l'empreinte.").pack(pady=(14, 4))

    def _activer(self):
        cle = self.champ_licence.get("1.0", "end").strip()
        if not cle:
            messagebox.showwarning("Activation", "Colle d'abord ta licence.")
            return
        st = licence.enregistrer_licence(cle)
        self.statut_licence = st
        if st["ok"]:
            exp = st.get("expire_le")
            if exp:
                msg = f"✅ HelpVA activé sur ce PC.\nAbonnement valable jusqu'au {exp.strftime('%d/%m/%Y')}."
            else:
                msg = "✅ HelpVA activé sur ce PC (licence à vie). Merci !"
            messagebox.showinfo("Activation", msg)
            self.montrer(self.ecran_bienvenue)
            self._planifier_verif_periodique()
        elif st["raison"] == "expire":
            messagebox.showwarning("Activation",
                                   "❌ Cette licence est déjà expirée.\n"
                                   "Demande une licence à jour au vendeur.")
        elif st["raison"] == "pas_internet":
            messagebox.showwarning("Activation",
                                   "❌ Pas d'internet pour vérifier l'abonnement.\n"
                                   "Connecte-toi puis réessaie.")
        else:
            messagebox.showwarning(
                "Activation",
                "❌ Licence invalide pour ce PC.\n\n"
                "Vérifie que :\n"
                "• tu as bien copié TOUTE la licence (sans espace en trop),\n"
                "• la licence a été générée avec l'empreinte de CE PC.")

    def ecran_bienvenue(self):
        cadre = ttk.Frame(self.conteneur)
        cadre.pack(expand=True)

        # Logo (si présent)
        try:
            from PIL import Image, ImageTk
            img = Image.open(chemin_ressource("assets/logo.png")).convert("RGBA")
            img.thumbnail((140, 140))
            self._logo = ImageTk.PhotoImage(img)
            ttk.Label(cadre, image=self._logo).pack(pady=(10, 6))
        except Exception:
            pass

        ttk.Label(cadre, text="Bienvenue sur HelpVA", style="Titre.TLabel").pack(pady=(6, 4))
        ttk.Label(cadre, style="Sous.TLabel", justify="center",
                  text="Ton assistant pour organiser tes contenus\n"
                       "et publier sur Instagram, simplement.").pack(pady=(0, 20))
        ttk.Button(cadre, text="Commencer", style="Primaire.TButton", width=18,
                   command=lambda: self.montrer(self.ecran_menu)).pack()

    def ecran_modele(self):
        ttk.Button(self.conteneur, text="← Retour", style="Retour.TButton",
                   command=lambda: self.montrer(self.ecran_menu)).pack(anchor="w")
        cadre = ttk.Frame(self.conteneur)
        cadre.pack(expand=True)
        ttk.Label(cadre, text="Nom du modèle", style="Titre.TLabel").pack(pady=(10, 4))
        ttk.Label(cadre, style="Sous.TLabel", justify="center",
                  text="Pour quel modèle (compte) travailles-tu ?\n"
                       "Les médias seront rangés dans SON dossier sur le Bureau.").pack(pady=(0, 16))
        self.champ_modele = ttk.Entry(cadre, width=28, font=(POLICE, 13), justify="center")
        self.champ_modele.pack(pady=6)
        self.champ_modele.insert(0, self.modele or "")
        self.champ_modele.focus()
        self.champ_modele.bind("<Return>", lambda e: self._valider_modele())

        cadre_g = ttk.Frame(cadre)
        cadre_g.pack(pady=(12, 4))
        ttk.Label(cadre_g, text="Genre :").pack(side="left", padx=(0, 8))
        self.genre_var = tk.StringVar(value=self.genre)
        ttk.Radiobutton(cadre_g, text="Féminin", value="feminin", variable=self.genre_var,
                        style="Type.TRadiobutton").pack(side="left", padx=6)
        ttk.Radiobutton(cadre_g, text="Masculin", value="masculin", variable=self.genre_var,
                        style="Type.TRadiobutton").pack(side="left", padx=6)

        ttk.Button(cadre, text="Continuer", style="Primaire.TButton", width=18,
                   command=self._valider_modele).pack(pady=14)

    def _valider_modele(self):
        nom = self.champ_modele.get().strip()
        if not nom:
            messagebox.showwarning("Modèle", "Entre un nom de modèle.")
            return
        # Nettoie les caractères interdits dans un nom de dossier.
        for c in '<>:"/\\|?*':
            nom = nom.replace(c, "")
        self.modele = nom.strip()
        self.genre = self.genre_var.get()
        self.params["modele"] = self.modele
        self.params["genre"] = self.genre
        parametres.sauver(self.params)
        self.montrer(self.ecran_menu)

    def ecran_menu(self):
        # --- barre du haut : modèle (si défini) + abonnement ---
        haut = ttk.Frame(self.conteneur)
        haut.pack(fill="x")
        if self.modele:
            genre_txt = "Féminin" if self.genre == "feminin" else "Masculin"
            ttk.Label(haut, text=f"Modèle : {self.modele}  ({genre_txt})",
                      style="Sous.TLabel").pack(side="left")
            ttk.Button(haut, text="changer", style="Retour.TButton",
                       command=lambda: self.montrer(self.ecran_modele)).pack(side="left", padx=6)

        st = getattr(self, "statut_licence", {}) or {}
        type_l = st.get("type")
        if type_l == "vie":
            txt_ab = "Abonnement : à vie"
        elif st.get("expire_le"):
            jr = st.get("jours_restants")
            txt_ab = f"Abonnement {type_l or ''} · jusqu'au {st['expire_le'].strftime('%d/%m/%Y')}"
            if isinstance(jr, int) and jr <= 7:
                txt_ab += f" ({jr} j restants)"
        else:
            txt_ab = ""
        if txt_ab:
            ttk.Label(haut, text=txt_ab, style="Sous.TLabel").pack(side="right")

        # --- grand titre, à gauche, avec une bonne marge ---
        ttk.Label(self.conteneur, text="Ton espace de travail",
                  style="Grand.TLabel").pack(anchor="w", padx=16, pady=(22, 4))
        ttk.Label(self.conteneur,
                  text="Prépare le contenu d'un modèle, puis publie — à la main ou en automatique.",
                  style="Sous.TLabel").pack(anchor="w", padx=16, pady=(0, 22))

        def rangee(titre, boutons):
            ttk.Label(self.conteneur, text=titre, style="Groupe.TLabel").pack(
                anchor="w", padx=16, pady=(6, 8))
            r = ttk.Frame(self.conteneur)
            r.pack(pady=(0, 14))   # centré horizontalement
            for lib, cmd in boutons:
                ttk.Button(r, text=lib, style="Menu.TButton", width=22,
                           command=cmd).pack(side="left", padx=8)

        # Groupe 1 : fonctions qui ont besoin d'un modèle (demande nom+sexe au clic).
        rangee("Contenu du modèle", [
            ("Ranger les médias", lambda: self._lancer_fonction_modele(self.ecran_ranger)),
            ("Changer les métadonnées", lambda: self._lancer_fonction_modele(self.ecran_uniquiser)),
            ("Générer les légendes", lambda: self._lancer_fonction_modele(self.ecran_legendes)),
        ])
        # Groupe 2 : publication (pas besoin du nom de modèle).
        rangee("Publication", [
            ("Publier le contenu", lambda: self.montrer(self.ecran_publier)),
            ("Automatiser les publications", lambda: self.montrer(self.ecran_planifier)),
        ])

    def _lancer_fonction_modele(self, ecran):
        """Fonctions liées à un modèle : si aucun modèle défini, on demande
        d'abord le nom + le sexe (puis retour au menu), sinon on ouvre l'écran."""
        if not self.modele:
            self.montrer(self.ecran_modele)
        else:
            self.montrer(ecran)

    def ecran_ranger(self):
        haut = ttk.Frame(self.conteneur)
        haut.pack(fill="x")
        ttk.Button(haut, text="← Retour", style="Retour.TButton",
                   command=lambda: self.montrer(self.ecran_menu)).pack(side="left")
        ttk.Button(haut, text="⚙ Paramètres", style="Retour.TButton",
                   command=self.ouvrir_editeur_calendrier).pack(side="right")
        ttk.Label(self.conteneur, text="Ranger les médias", style="H2.TLabel").pack(anchor="w", pady=(8, 6))
        ttk.Label(self.conteneur, style="Sous.TLabel", justify="left",
                  text="Prépare un dossier contenant EXACTEMENT ces 2 sous-dossiers :\n\n"
                       "   TonDossier\\\n"
                       "        videos\\   → tes vidéos (pour les Reels)\n"
                       "        images\\   → tes images (pour Carrousels + Stories)\n\n"
                       "1) Importe le dossier   2) Clique « Lancer le rangement ».").pack(anchor="w")
        # Minimum de médias à préparer selon le calendrier actuel.
        ttk.Label(self.conteneur, text=self._besoins_texte(calendrier.charger_calendrier()),
                  style="Sous.TLabel", foreground=ACCENT_FONCE).pack(anchor="w", pady=(6, 0))
        ligne = ttk.Frame(self.conteneur)
        ligne.pack(pady=12)
        ttk.Button(ligne, text="Importer un dossier…",
                   command=self.choisir_dossier_ranger).pack(side="left", padx=4)
        ttk.Button(ligne, text="Lancer le rangement", style="Primaire.TButton",
                   command=self.lancer_ranger).pack(side="left", padx=4)
        txt = f"Dossier : {self.dossier_ranger_src}" if self.dossier_ranger_src else "Aucun dossier sélectionné"
        self.lbl_ranger = ttk.Label(self.conteneur, text=txt, style="Sous.TLabel")
        self.lbl_ranger.pack(anchor="w")
        self._zone_log()

    def ecran_uniquiser(self):
        self._barre_retour()
        ttk.Label(self.conteneur, text="Changer les métadonnées", style="H2.TLabel").pack(anchor="w", pady=(8, 6))
        ttk.Label(self.conteneur, style="Sous.TLabel", justify="left",
                  text="Choisis un dossier d'IMAGES et/ou de VIDÉOS. HelpVA crée une version\n"
                       "unique de chaque média (métadonnées changées + micro-modifications\n"
                       "invisibles) pour éviter la détection de doublon entre comptes.\n\n"
                       "Résultat dans le dossier « media (métadonnées changées) » du modèle :\n"
                       "     images\\   (images traitées)\n"
                       "     videos\\   (vidéos traitées)\n"
                       "Tes originaux ne sont pas touchés. Les vidéos sont ré-encodées\n"
                       "(ça peut prendre un peu de temps).\n\n"
                       "1) Importe le dossier   2) Clique « Lancer ».").pack(anchor="w")
        self.renommer_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.conteneur, text="Renommer les médias (1, 2, 3…)",
                        variable=self.renommer_var, style="TCheckbutton").pack(anchor="w", pady=(8, 0))
        ligne = ttk.Frame(self.conteneur)
        ligne.pack(pady=12)
        ttk.Button(ligne, text="Importer un dossier…",
                   command=self.choisir_dossier_uniq).pack(side="left", padx=4)
        ttk.Button(ligne, text="Lancer", style="Primaire.TButton",
                   command=self.lancer_uniquiser).pack(side="left", padx=4)
        txt = f"Dossier : {self.dossier_uniq_src}" if self.dossier_uniq_src else "Aucun dossier sélectionné"
        self.lbl_uniq = ttk.Label(self.conteneur, text=txt, style="Sous.TLabel")
        self.lbl_uniq.pack(anchor="w")
        self._zone_log()

    def ecran_legendes(self):
        self._barre_retour()
        ttk.Label(self.conteneur, text="Générer les légendes", style="H2.TLabel").pack(anchor="w", pady=(8, 6))
        genre_txt = "Féminin" if self.genre == "feminin" else "Masculin"
        ttk.Label(self.conteneur, style="Sous.TLabel", justify="left",
                  text="Remplit automatiquement la LÉGENDE (legende.txt) de chaque\n"
                       "REEL et CARROUSEL du modèle. Les stories ne sont pas concernées.\n"
                       "(Les captions ne sont plus générées : elles sont déjà sur les vidéos.)\n\n"
                       f"Genre utilisé : {genre_txt}   ·   Modèle : {self.modele}\n"
                       "⚠️ Range d'abord tes médias (le dossier « ranger » doit exister).").pack(anchor="w")
        self.hashtags_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.conteneur, text="Ajouter des hashtags à la fin",
                        variable=self.hashtags_var, style="TCheckbutton").pack(anchor="w", pady=(8, 0))
        ttk.Button(self.conteneur, text="Générer les légendes", style="Primaire.TButton",
                   width=26, command=self.generer_legendes).pack(pady=14)
        self._zone_log()

    def ecran_publier(self):
        self._barre_retour()
        ttk.Label(self.conteneur, text="Publier le contenu", style="H2.TLabel").pack(anchor="w", pady=(8, 6))

        # Connexion (clé API + profil)
        co = ttk.LabelFrame(self.conteneur, text="Connexion AdsPower", padding=8)
        co.pack(fill="x")
        ttk.Label(co, text="Clé API :").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.champ_cle = ttk.Entry(co, width=46)
        self.champ_cle.grid(row=0, column=1, padx=4, pady=4)
        self.champ_cle.insert(0, self.params.get("api_key", ""))
        ttk.Button(co, text="Enregistrer + charger profils",
                   command=self.enregistrer_et_charger).grid(row=0, column=2, padx=4)
        ttk.Label(co, text="Profil :").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.combo_profil = ttk.Combobox(co, width=44, state="readonly")
        self.combo_profil.grid(row=1, column=1, padx=4, pady=4)

        # Formulaire
        form = ttk.LabelFrame(self.conteneur, text="Publication", padding=8)
        form.pack(fill="x", pady=(10, 0))

        ttk.Button(form, text="Ouvrir un dossier (créneau ranger)…",
                   command=self.ouvrir_creneau).pack(anchor="w", pady=(0, 8))

        corps = ttk.Frame(form)
        corps.pack(fill="x")
        gauche = ttk.Frame(corps)
        gauche.pack(side="left", anchor="n")
        droite = ttk.Frame(corps)
        droite.pack(side="left", anchor="n", padx=(18, 0))

        # --- colonne gauche : champs ---
        lg = ttk.Frame(gauche)
        lg.pack(anchor="w", pady=2)
        ttk.Label(lg, text="Type :").pack(side="left")
        self.type_var = tk.StringVar(value="publication")
        for t in ["publication", "carrousel", "reel"]:
            ttk.Radiobutton(lg, text=t, value=t, variable=self.type_var,
                            style="Type.TRadiobutton").pack(side="left", padx=4)

        self.fichiers = []
        self.lf = ttk.Frame(gauche)
        self.lf.pack(anchor="w", pady=2)
        ttk.Button(self.lf, text="Choisir…", command=self._choisir_fichiers).pack(side="left")
        self.lbl_fichiers = ttk.Label(self.lf, text="Aucun fichier", style="Sous.TLabel")
        self.lbl_fichiers.pack(side="left", padx=6)

        # Bloc LÉGENDE.
        self.cadre_legende = ttk.Frame(gauche)
        ttk.Label(self.cadre_legende, text="Légende :").pack(anchor="w", pady=(6, 0))
        self.champ_leg = tk.Text(self.cadre_legende, height=4, width=42, font=(POLICE, 10))
        self.champ_leg.pack(anchor="w")
        self.cadre_legende.pack(anchor="w")

        self.essai_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(gauche, text="Essai (ne publie pas vraiment)",
                        variable=self.essai_var, style="TCheckbutton").pack(anchor="w", pady=(4, 0))
        ligne_btn = ttk.Frame(gauche)
        ligne_btn.pack(anchor="w", pady=8)
        ttk.Button(ligne_btn, text="Publier", style="Primaire.TButton", width=16,
                   command=self.publier).pack(side="left")
        ttk.Button(ligne_btn, text="Effacer / vider",
                   command=self.effacer_publier).pack(side="left", padx=8)

        # --- colonne droite : aperçu(s) ---
        ttk.Label(droite, text="Aperçu :", style="Sous.TLabel").pack(anchor="w")
        self.cadre_apercu = ttk.Frame(droite)
        self.cadre_apercu.pack(anchor="n", pady=4)
        ttk.Label(self.cadre_apercu, text="(aucun média)", style="Sous.TLabel").pack()

        self._zone_log()

        # Pré-remplit les profils si une clé est déjà là.
        if self.params.get("api_key"):
            self.enregistrer_et_charger()

    # ---------------------------------------------------------------- utils

    def _vider_file_log(self):
        try:
            while True:
                item = self.file_log.get_nowait()
                if isinstance(item, tuple):
                    self._controle(item)
                elif self.log is not None:
                    self.log.configure(state="normal")
                    self.log.insert("end", item)
                    self.log.see("end")
                    self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._vider_file_log)

    def _controle(self, item):
        if item[0] == "profils":
            self.profils = item[1]
            noms = list(self.profils.keys())
            if hasattr(self, "combo_profil") and self.combo_profil.winfo_exists():
                self.combo_profil["values"] = noms
                cible = self.params.get("profil", "")
                choisi = next((n for n, u in self.profils.items() if u == cible), None)
                self.combo_profil.set(choisi or (noms[0] if noms else ""))
        elif item[0] == "loading_fini":
            self._cacher_loading()
        elif item[0] == "planif_arret":
            self._maj_boutons_planif(False)
        elif item[0] == "verif_licence":
            self._traiter_verif(item[1])
        elif item[0] == "popup":
            self._cacher_loading()   # ferme le loading avant le message
            titre, message, erreur = item[1], item[2], item[3]
            if erreur:
                messagebox.showwarning(titre, message)
            else:
                messagebox.showinfo(titre, message)
        elif item[0] == "fini_ranger":
            self._cacher_loading()   # ferme le loading avant le message
            sortie, res = item[1], item[2]
            txt = f"Rangement terminé !\n\nDossier créé sur le Bureau :\n{sortie}"
            mv, mi = res.get("manque_videos", 0), res.get("manque_images", 0)
            if mv or mi:
                txt += "\n\n⚠️ Médias insuffisants :"
                if mv:
                    txt += f"\n• Il manque {mv} vidéo(s) pour les reels"
                if mi:
                    txt += f"\n• Il manque {mi} image(s) pour carrousels/stories"
                txt += "\n(les créneaux concernés sont vides — voir le journal)"
            if res.get("surplus"):
                txt += f"\n\n📦 {res['surplus']} média(s) en surplus rangé(s) dans le dossier « surplus »."
            if mv or mi:
                messagebox.showwarning("Ranger", txt)
            else:
                messagebox.showinfo("Ranger", txt)

    def _afficher_loading(self, message):
        """Affiche un popup modal de chargement avec barre animée."""
        self._popup = tk.Toplevel(self.root)
        self._popup.title("Veuillez patienter")
        self._popup.configure(bg=BG)
        self._popup.resizable(False, False)
        self._popup.transient(self.root)
        self._popup.protocol("WM_DELETE_WINDOW", lambda: None)  # non fermable
        ttk.Label(self._popup, text=message, style="Sous.TLabel").pack(padx=30, pady=(20, 10))
        pb = ttk.Progressbar(self._popup, mode="indeterminate", length=260)
        pb.pack(padx=30, pady=(0, 20))
        pb.start(12)
        self._pb = pb
        self._popup.update_idletasks()
        x = self.root.winfo_rootx() + self.root.winfo_width() // 2 - self._popup.winfo_width() // 2
        y = self.root.winfo_rooty() + self.root.winfo_height() // 2 - 60
        self._popup.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self._popup.grab_set()

    def _cacher_loading(self):
        try:
            if getattr(self, "_pb", None):
                self._pb.stop()
            if getattr(self, "_popup", None):
                self._popup.grab_release()
                self._popup.destroy()
        except Exception:
            pass
        self._popup = None

    def _tache(self, fn, message="Traitement en cours…"):
        if self.occupe:
            print("[!] Une action est déjà en cours, patiente…")
            return

        self._afficher_loading(message)

        def envelopper():
            self.occupe = True
            try:
                fn()
            except Exception as e:
                print(f"\n[ERREUR] {e}")
            finally:
                self.occupe = False
                self.file_log.put(("loading_fini",))

        threading.Thread(target=envelopper, daemon=True).start()

    def _notifier(self, titre, message, erreur=False):
        """Enqueue un popup de confirmation (appelable depuis un thread)."""
        self.file_log.put(("popup", titre, message, erreur))

    def _profil(self):
        uid = self.profils.get(self.combo_profil.get())
        if not uid:
            print("[!] Choisis d'abord un profil (Enregistrer + charger profils).")
        else:
            self.params["profil"] = uid
            parametres.sauver(self.params)
        return uid

    # -------------------------------------------------------------- actions

    def enregistrer_et_charger(self):
        self.params["api_key"] = self.champ_cle.get().strip()
        parametres.sauver(self.params)

        def job():
            print("Chargement des profils AdsPower…")
            liste = adspower.lister_profils()
            profils = {f"{p['name']} ({p['user_id']})": p["user_id"] for p in liste}
            self.file_log.put(("profils", profils))
            print(f"{len(profils)} profil(s) trouvé(s).")
        self._tache(job, "Chargement des profils…")

    def _besoins_du_cal(self, cal):
        """Compte les médias nécessaires pour remplir un calendrier sans manque.
        Retourne (reels, carrousels, stories, images_totales)."""
        reels = carrousels = stories = 0
        for jours in cal.values():
            for creneaux in jours.values():
                for c in creneaux:
                    t = c.get("type")
                    if t == "reel":
                        reels += 1
                    elif t == "carousel":
                        carrousels += 1
                    elif t == "story":
                        stories += 1
        images = carrousels * rangement.IMAGES_PAR_CAROUSEL + stories
        return reels, carrousels, stories, images

    def _besoins_texte(self, cal):
        reels, carrousels, stories, images = self._besoins_du_cal(cal)
        par = rangement.IMAGES_PAR_CAROUSEL
        return (f"📊 Pour {len(cal)} semaine(s) sans manque : "
                f"{reels} vidéo(s)  ·  {images} image(s) "
                f"({carrousels} carrousel(s)×{par} + {stories} story(s))")

    MAX_SEMAINES = 4   # 1 mois = 4 semaines

    def ouvrir_editeur_calendrier(self):
        """Éditeur du calendrier : créneaux + gestion des semaines (max 4).

        On peut dupliquer une semaine (ex: répéter la croisière) ou en
        supprimer une (ex: enlever le démarrage pour un VA déjà lancé).
        """
        import copy
        cal = calendrier.charger_calendrier()
        fen = tk.Toplevel(self.root)
        fen.title("Paramètres — Ajuster le calendrier")
        fen.geometry("620x640")
        fen.configure(bg=BG)

        haut = ttk.Frame(fen)
        haut.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Button(haut, text="← Retour", style="Retour.TButton",
                   command=fen.destroy).pack(side="left")
        ttk.Label(fen, text="Ajuster le calendrier", style="H2.TLabel").pack(pady=(2, 2))
        ttk.Label(fen, style="Sous.TLabel", justify="center",
                  text="Max 4 semaines (= 1 mois). Duplique une semaine pour la répéter,\n"
                       "supprime-en une pour l'enlever. Le rangement se fait 1×/mois.").pack(pady=(0, 6))

        nb = ttk.Notebook(fen)
        nb.pack(fill="both", expand=True, padx=10)
        internes = {}
        lbl_besoins = None   # créé plus bas ; mis à jour à chaque changement

        def maj_besoins():
            if lbl_besoins is not None:
                lbl_besoins.configure(text=self._besoins_texte(cal))

        # ---- opérations sur les CRÉNEAUX ----
        def maj_heure(s, j, i, v):
            try:
                cal[s][j][i]["heure"] = v.get()
            except Exception:
                pass

        def maj_type(s, j, i, v):
            try:
                cal[s][j][i]["type"] = v.get()
                maj_besoins()
            except Exception:
                pass

        def ajouter(s, j):
            cal[s][j].append({"heure": "12h00", "type": "reel"})
            rendre(s)

        def supprimer(s, j, i):
            del cal[s][j][i]
            rendre(s)

        # ---- opérations sur les SEMAINES ----
        def renumeroter():
            vals = list(cal.values())
            cal.clear()
            for i, jours in enumerate(vals, start=1):
                cal[f"semaine-{i:02d}"] = jours

        def dupliquer_semaine(nom_sem):
            if len(cal) >= self.MAX_SEMAINES:
                messagebox.showwarning(
                    "Semaines", f"Maximum {self.MAX_SEMAINES} semaines (= 1 mois).")
                return
            vals = list(cal.values())
            idx = list(cal.keys()).index(nom_sem)
            vals.insert(idx + 1, copy.deepcopy(cal[nom_sem]))
            cal.clear()
            for i, jours in enumerate(vals, start=1):
                cal[f"semaine-{i:02d}"] = jours
            rebuild(select=idx + 1)

        def supprimer_semaine(nom_sem):
            if len(cal) <= 1:
                messagebox.showwarning("Semaines", "Il faut au moins 1 semaine.")
                return
            if not messagebox.askyesno(
                    "Supprimer la semaine",
                    f"Supprimer {nom_sem.replace('semaine-', 'la semaine ')} ?\n"
                    "Les autres semaines seront renumérotées."):
                return
            del cal[nom_sem]
            renumeroter()
            rebuild()

        # ---- rendu des jours d'une semaine ----
        def rendre(nom_sem):
            interne = internes[nom_sem]
            for w in interne.winfo_children():
                w.destroy()
            r = 0
            for nom_jour, creneaux in cal[nom_sem].items():
                entete = ttk.Frame(interne)
                entete.grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 1))
                ttk.Label(entete, text=nom_jour, style="Sous.TLabel").pack(side="left", padx=(4, 8))
                ttk.Button(entete, text="+ Ajouter un créneau", style="Retour.TButton",
                           command=lambda s=nom_sem, j=nom_jour: ajouter(s, j)).pack(side="left")
                r += 1
                for idx, cr in enumerate(creneaux):
                    hv = tk.StringVar(value=cr["heure"])
                    tv = tk.StringVar(value=cr["type"])
                    hv.trace_add("write", lambda *a, s=nom_sem, j=nom_jour, i=idx, v=hv: maj_heure(s, j, i, v))
                    tv.trace_add("write", lambda *a, s=nom_sem, j=nom_jour, i=idx, v=tv: maj_type(s, j, i, v))
                    ttk.Entry(interne, textvariable=hv, width=8).grid(row=r, column=0, padx=(24, 6), sticky="w", pady=1)
                    ttk.Combobox(interne, values=["reel", "carousel", "story"], textvariable=tv,
                                 state="readonly", width=12).grid(row=r, column=1, sticky="w")
                    ttk.Button(interne, text="✕", style="Retour.TButton", width=3,
                               command=lambda s=nom_sem, j=nom_jour, i=idx: supprimer(s, j, i)).grid(
                        row=r, column=2, padx=6)
                    r += 1
            interne.update_idletasks()
            maj_besoins()

        # ---- (re)construction des onglets (semaines) ----
        def rebuild(select=0):
            for w in nb.winfo_children():
                w.destroy()
            internes.clear()
            for nom_sem in cal:
                onglet = ttk.Frame(nb)
                nb.add(onglet, text=nom_sem.replace("semaine-", "Sem. "))
                # Barre d'actions de la semaine.
                actions = ttk.Frame(onglet)
                actions.pack(fill="x", padx=6, pady=(6, 2))
                ttk.Button(actions, text="⧉ Dupliquer cette semaine", style="Retour.TButton",
                           command=lambda s=nom_sem: dupliquer_semaine(s)).pack(side="left")
                ttk.Button(actions, text="🗑 Supprimer cette semaine", style="Retour.TButton",
                           command=lambda s=nom_sem: supprimer_semaine(s)).pack(side="left", padx=6)
                # Zone défilable des jours.
                canvas = tk.Canvas(onglet, bg=BG, highlightthickness=0)
                sb = ttk.Scrollbar(onglet, orient="vertical", command=canvas.yview)
                interne = ttk.Frame(canvas)
                interne.bind("<Configure>", lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
                canvas.create_window((0, 0), window=interne, anchor="nw")
                canvas.configure(yscrollcommand=sb.set)
                canvas.pack(side="left", fill="both", expand=True)
                sb.pack(side="right", fill="y")
                internes[nom_sem] = interne
                rendre(nom_sem)
            tabs = nb.tabs()
            if tabs:
                nb.select(tabs[min(select, len(tabs) - 1)])

        rebuild()

        def reinitialiser():
            from agent.calendrier import CALENDRIER
            neuf = copy.deepcopy(CALENDRIER)
            cal.clear()
            cal.update(neuf)
            rebuild()

        def enregistrer():
            calendrier.sauver_calendrier(cal)
            messagebox.showinfo("Calendrier",
                                f"Ajustements enregistrés ({len(cal)} semaine(s)).\n"
                                "Appliqués au prochain rangement.")
            fen.destroy()

        # Calcul en direct du minimum de médias à préparer.
        lbl_besoins = ttk.Label(fen, style="Sous.TLabel", foreground=ACCENT_FONCE)
        lbl_besoins.pack(pady=(4, 0))
        maj_besoins()

        barre = ttk.Frame(fen)
        barre.pack(fill="x", pady=8, padx=10)
        ttk.Button(barre, text="Enregistrer", style="Primaire.TButton",
                   command=enregistrer).pack(side="right")
        ttk.Button(barre, text="Réinitialiser", style="Retour.TButton",
                   command=reinitialiser).pack(side="left")

    def choisir_dossier_ranger(self):
        """Sélectionne (sans lancer) le dossier à ranger ; vérifie le format."""
        dossier = filedialog.askdirectory(title="Choisir le dossier à ranger")
        if not dossier:
            return
        dv = os.path.join(dossier, "videos")
        di = os.path.join(dossier, "images")
        if not (os.path.isdir(dv) and os.path.isdir(di)):
            messagebox.showerror(
                "Format du dossier",
                "Le dossier doit contenir 2 sous-dossiers nommés :\n\n"
                "   videos   (tes vidéos)\n"
                "   images   (tes images)")
            return
        self.dossier_ranger_src = dossier
        self.lbl_ranger.configure(text=f"Dossier : {dossier}")

    def lancer_ranger(self):
        dossier = self.dossier_ranger_src
        if not dossier:
            messagebox.showwarning("Ranger", "Importe d'abord un dossier.")
            return
        dv = os.path.join(dossier, "videos")
        di = os.path.join(dossier, "images")

        # Vérifie que rien n'est mal placé (images dans videos/, etc.).
        infos = rangement.verifier_dossiers(dv, di)
        if infos["img_dans_videos"] or infos["vid_dans_images"]:
            msg = "Des fichiers semblent mal placés :\n"
            if infos["img_dans_videos"]:
                ex = ", ".join(infos["img_dans_videos"][:5])
                msg += f"\n• {len(infos['img_dans_videos'])} image(s) dans « videos » : {ex}"
            if infos["vid_dans_images"]:
                ex = ", ".join(infos["vid_dans_images"][:5])
                msg += f"\n• {len(infos['vid_dans_images'])} vidéo(s) dans « images » : {ex}"
            msg += "\n\nCes fichiers seront IGNORÉS. Continuer quand même ?"
            if not messagebox.askyesno("Fichiers mal placés", msg):
                return

        # Confirmation avant d'écrire sur le Bureau (dossier du modèle).
        sortie = os.path.join(self.dossier_modele(), "ranger")
        existe = os.path.exists(sortie)
        msg = (f"{infos['nb_videos']} vidéo(s) et {infos['nb_images']} image(s) vont être "
               f"rangées selon le calendrier.\n\nDestination :\n{sortie}\n")
        if existe:
            msg += "\n⚠️ Ce dossier existe déjà et sera REMPLACÉ (ancien contenu supprimé).\n"
        if not messagebox.askyesno("Confirmer le rangement", msg + "\nContinuer ?"):
            return

        def job():
            if existe:
                shutil.rmtree(sortie, ignore_errors=True)   # régénération propre
            res = rangement.ranger(dv, di, sortie, simuler=False)
            self.file_log.put(("fini_ranger", sortie, res))
        self._tache(job, "Rangement en cours…")

    def choisir_dossier_uniq(self):
        """Sélectionne (sans lancer) le dossier images/vidéos à traiter."""
        dossier = filedialog.askdirectory(title="Choisir le dossier (images ou vidéos)")
        if not dossier:
            return
        self.dossier_uniq_src = dossier
        self.lbl_uniq.configure(text=f"Dossier : {dossier}")

    def lancer_uniquiser(self):
        dossier = self.dossier_uniq_src
        if not dossier:
            messagebox.showwarning("Changer les métadonnées", "Importe d'abord un dossier.")
            return
        sortie = os.path.join(self.dossier_modele(), "media (métadonnées changées)")
        renommer = self.renommer_var.get()
        if os.path.exists(sortie):
            if not messagebox.askyesno(
                    "Remplacer ?",
                    f"Le dossier existe déjà et sera REMPLACÉ :\n{sortie}\n\nContinuer ?"):
                return

        def job():
            if os.path.exists(sortie):
                shutil.rmtree(sortie, ignore_errors=True)   # régénération propre
            n = unicite.uniquiser_dossier(dossier, sortie, renommer=renommer)
            print(f"\n✅ {n} média(s) traité(s) → {sortie}")
            print("   (sous-dossiers : images\\  et  videos\\)")
            self._notifier("Métadonnées changées",
                           f"✅ {n} média(s) traité(s) !\n\n"
                           f"Résultat sur le Bureau :\n{sortie}\n"
                           f"(sous-dossiers images\\ et videos\\)")
        self._tache(job, "Changement des métadonnées…")

    def generer_legendes(self):
        dossier = os.path.join(self.dossier_modele(), "ranger")
        if not os.path.isdir(dossier):
            messagebox.showwarning(
                "Légendes",
                "Le dossier « ranger » du modèle est introuvable.\n"
                "Range d'abord tes médias (Ranger les médias).")
            return
        genre = self.genre
        avec = self.hashtags_var.get()

        def job():
            n = legendes.generer_pour_dossier(dossier, genre, avec_hashtags=avec)
            print(f"\n✅ {n} créneau(x) reel/carrousel : légende remplie.")
            self._notifier("Légendes générées",
                           f"✅ {n} créneau(x) reel/carrousel :\nlégende remplie avec succès !")
        self._tache(job, "Génération des légendes…")

    def _choisir_fichiers(self):
        sel = filedialog.askopenfilenames(title="Choisir le(s) média(s)")
        if sel:
            self.fichiers = list(sel)
            self.lbl_fichiers.configure(text=f"{len(sel)} fichier(s) sélectionné(s)")
            self._afficher_apercu(self.fichiers)

    def _afficher_apercu(self, medias):
        """Affiche une vignette par média dans la colonne de droite."""
        for w in self.cadre_apercu.winfo_children():
            w.destroy()
        self._apercu_imgs = []   # garde les références (sinon effacées)
        try:
            from PIL import Image, ImageTk
            for i, media in enumerate(medias[:9]):   # 9 vignettes max
                if os.path.splitext(media)[1].lower() in VIDEOS_EXT:
                    tmp = os.path.join(tempfile.gettempdir(), "helpva_apercu.png")
                    montage.vignette(media, tmp)
                    img = Image.open(tmp)
                else:
                    img = Image.open(media)
                # une grande vignette si 1 seul média, sinon plus petites en grille
                taille = (280, 380) if len(medias) == 1 else (125, 170)
                img.thumbnail(taille)
                photo = ImageTk.PhotoImage(img)
                self._apercu_imgs.append(photo)
                col = 2 if len(medias) == 1 else 3
                ttk.Label(self.cadre_apercu, image=photo).grid(
                    row=i // col, column=i % col, padx=3, pady=3)
            if not medias:
                ttk.Label(self.cadre_apercu, text="(aucun média)", style="Sous.TLabel").pack()
        except Exception:
            for w in self.cadre_apercu.winfo_children():
                w.destroy()
            ttk.Label(self.cadre_apercu, text="(aperçu indisponible)", style="Sous.TLabel").pack()

    def ouvrir_creneau(self):
        dossier = filedialog.askdirectory(title="Ouvrir un créneau (dossier ranger)")
        if dossier:
            self._charger_creneau(dossier)

    def _charger_creneau(self, dossier):
        """Charge média(s) + type + légende depuis un dossier créneau."""
        fichiers = sorted(os.listdir(dossier))
        images = [os.path.join(dossier, f) for f in fichiers
                  if os.path.splitext(f)[1].lower() in IMAGES_EXT]
        videos = [os.path.join(dossier, f) for f in fichiers
                  if os.path.splitext(f)[1].lower() in VIDEOS_EXT]

        if videos:
            self.fichiers = [videos[0]]
            self.type_var.set("reel")
        elif len(images) >= 2:
            self.fichiers = images
            self.type_var.set("carrousel")
        elif len(images) == 1:
            self.fichiers = images
            self.type_var.set("publication")
        else:
            messagebox.showwarning("Créneau", "Aucun média (image/vidéo) dans ce dossier.")
            return

        self.lbl_fichiers.configure(text=f"{len(self.fichiers)} fichier(s) — {os.path.basename(dossier)}")
        self._afficher_apercu(self.fichiers)

        # Légende, si elle existe.
        leg = ""
        p = os.path.join(dossier, "legende.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                leg = f.read().strip()
        self.champ_leg.delete("1.0", "end")
        self.champ_leg.insert("1.0", leg)

        print(f"[créneau] {os.path.basename(dossier)} : {len(self.fichiers)} média(s), "
              f"légende {len(leg)} car.")
        if not leg:
            print("[info] Légende vide dans ce créneau — lance d'abord « Générer les légendes ».")

    def effacer_publier(self):
        """Vide tout le formulaire de publication (nouveau départ)."""
        self.fichiers = []
        self.lbl_fichiers.configure(text="Aucun fichier")
        self.champ_leg.delete("1.0", "end")
        self.type_var.set("publication")
        self.essai_var.set(False)
        self._afficher_apercu([])   # remet "(aucun média)"
        print("[publier] formulaire vidé.")

    def publier(self):
        uid = self._profil()
        if not uid:
            return
        if not self.fichiers:
            messagebox.showwarning("Publier", "Choisis au moins un fichier.")
            return
        legende = self.champ_leg.get("1.0", "end").strip()
        essai = self.essai_var.get()
        fichiers = list(self.fichiers)
        type_post = self.type_var.get()

        # Validation des fichiers selon le type choisi.
        IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
        VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
        ext = lambda f: os.path.splitext(f)[1].lower()
        if type_post == "reel":
            if len(fichiers) != 1 or ext(fichiers[0]) not in VIDEOS:
                messagebox.showwarning("Réel", "Un réel nécessite UNE seule vidéo.")
                return
        elif type_post == "publication":
            if len(fichiers) != 1 or ext(fichiers[0]) not in IMAGES:
                messagebox.showwarning("Publication", "Une publication nécessite UNE seule photo.")
                return
        elif type_post == "carrousel":
            if len(fichiers) < 2 or not all(ext(f) in IMAGES for f in fichiers):
                messagebox.showwarning("Carrousel", "Un carrousel nécessite AU MOINS 2 photos.")
                return

        def job():
            try:
                with navigateur_du_profil(uid) as driver:
                    if type_post == "publication":
                        instagram.poster_publication(driver, fichiers[0], legende, essai)
                    elif type_post == "carrousel":
                        instagram.poster_carrousel(driver, fichiers, legende, essai)
                    elif type_post == "reel":
                        instagram.poster_reel(driver, fichiers[0], legende, essai)
                print("✅ Terminé.")
                if essai:
                    self._notifier("Publication",
                                   "✅ ESSAI OK — tout est prêt (rien n'a été publié).")
                else:
                    self._notifier("Publication",
                                   f"✅ Contenu publié avec succès !\n({type_post})")
            except Exception as e:
                print(f"[ERREUR] {e}")
                self._notifier("Publication", f"❌ Échec de la publication :\n\n{e}", erreur=True)
        self._tache(job, "Publication en cours…")

    # ============================================================ PLANIFICATEUR

    def _dossier_planning(self) -> str:
        """Dossier « ranger » à utiliser : celui importé si présent, sinon
        celui du modèle par défaut (Bureau\\HelpVA\\<Modèle>\\ranger)."""
        if self.dossier_planif_src and os.path.isdir(self.dossier_planif_src):
            return self.dossier_planif_src
        return os.path.join(self.dossier_modele(), "ranger")

    def choisir_adspower(self):
        """Enregistre le chemin de l'exe AdsPower (si l'auto-détection échoue)."""
        chemin = filedialog.askopenfilename(
            title="Choisir AdsPower Global.exe",
            filetypes=[("AdsPower", "*.exe"), ("Tous", "*.*")])
        if not chemin:
            return
        self.params["adspower_exe"] = chemin
        parametres.sauver(self.params)
        if hasattr(self, "lbl_adspower") and self.lbl_adspower.winfo_exists():
            self.lbl_adspower.configure(
                text=f"AdsPower : {os.path.basename(chemin)} (ouverture auto)")

    def choisir_dossier_planif(self):
        """Laisse l'utilisateur importer le dossier « ranger » du modèle.

        Accepte soit le dossier « ranger » lui-même, soit un dossier qui
        contient un sous-dossier « ranger »."""
        dossier = filedialog.askdirectory(title="Choisir le dossier du modèle (ranger)")
        if not dossier:
            return
        # Si l'utilisateur a choisi le dossier du modèle, on descend dans "ranger".
        sous = os.path.join(dossier, "ranger")
        if os.path.isdir(sous):
            dossier = sous
        # Contrôle : y a-t-il bien des semaines dedans ?
        a_des_semaines = any(n.startswith("semaine-") and os.path.isdir(os.path.join(dossier, n))
                             for n in os.listdir(dossier)) if os.path.isdir(dossier) else False
        self.dossier_planif_src = dossier
        if hasattr(self, "lbl_dossier_planif") and self.lbl_dossier_planif.winfo_exists():
            self.lbl_dossier_planif.configure(text=f"Dossier : {dossier}")
        if not a_des_semaines:
            messagebox.showwarning(
                "Dossier",
                "Ce dossier ne contient pas de sous-dossiers « semaine-XX ».\n"
                "Choisis le dossier « ranger » créé par « Ranger les médias ».")

    def _lire_date_debut(self):
        """Lit la date de début (JJ/MM/AAAA). Retourne un date, ou None si invalide."""
        txt = self.champ_date.get().strip()
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(txt, fmt).date()
            except ValueError:
                continue
        messagebox.showwarning("Date de début",
                               "Date invalide. Utilise le format JJ/MM/AAAA (ex : 07/08/2026).")
        return None

    def _maj_demarrage_windows(self):
        """Active/désactive le lancement de HelpVA au démarrage de Windows."""
        if self.demarrage_win_var.get():
            ok = demarrage.activer()
            if ok:
                messagebox.showinfo("Démarrage Windows",
                                    "✅ HelpVA se lancera au démarrage de Windows.\n"
                                    "L'automatisation reprendra toute seule après un redémarrage.")
            else:
                self.demarrage_win_var.set(False)
                messagebox.showwarning("Démarrage Windows",
                                       "Impossible d'activer le démarrage automatique.")
        else:
            demarrage.desactiver()

    def ecran_planifier(self):
        self._barre_retour()
        ttk.Label(self.conteneur, text="Automatiser les publications",
                  style="H2.TLabel").pack(anchor="w", pady=(8, 6))
        ttk.Label(self.conteneur, style="Sous.TLabel", justify="left",
                  text="Tu cliques « Démarrer » UNE fois → HelpVA publie ensuite TOUT SEUL\n"
                       "les reels et carrousels aux heures du calendrier, jour après jour.\n\n"
                       "🔁 Si l'app se ferme ou le PC redémarre, elle REPREND toute seule et\n"
                       "    rattrape les publications manquées (coche « démarrage Windows »).\n"
                       "📌 Les stories ne sont pas automatisées (à poster à la main via Inssist).\n"
                       "📌 AdsPower doit être ouvert. Sans internet au moment prévu, le post\n"
                       "    part dès que la connexion revient.").pack(anchor="w")

        # Connexion (clé API + profil) — même mécanique que la page Publier.
        co = ttk.LabelFrame(self.conteneur, text="Connexion AdsPower", padding=8)
        co.pack(fill="x", pady=(10, 0))
        ttk.Label(co, text="Clé API :").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.champ_cle = ttk.Entry(co, width=46)
        self.champ_cle.grid(row=0, column=1, padx=4, pady=4)
        self.champ_cle.insert(0, self.params.get("api_key", ""))
        ttk.Button(co, text="Enregistrer + charger profils",
                   command=self.enregistrer_et_charger).grid(row=0, column=2, padx=4)
        ttk.Label(co, text="Profil :").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.combo_profil = ttk.Combobox(co, width=44, state="readonly")
        self.combo_profil.grid(row=1, column=1, padx=4, pady=4)
        # AdsPower : détection + ouverture auto (au reboot). Bouton si non trouvé.
        detect = adspower.chemin_adspower()
        txt_ap = (f"AdsPower : {os.path.basename(detect)} (ouverture auto)"
                  if detect else "AdsPower : non trouvé — clique pour l'indiquer")
        self.lbl_adspower = ttk.Label(co, text=txt_ap, style="Sous.TLabel")
        self.lbl_adspower.grid(row=2, column=1, sticky="w", padx=4, pady=(0, 2))
        ttk.Button(co, text="Choisir AdsPower.exe…",
                   command=self.choisir_adspower).grid(row=2, column=2, padx=4)

        # Dossier du modèle (arborescence "ranger" que l'agent va utiliser).
        dm = ttk.LabelFrame(self.conteneur, text="Dossier du modèle (rangé)", padding=8)
        dm.pack(fill="x", pady=(10, 0))
        ttk.Label(dm, style="Sous.TLabel", justify="left",
                  text="Choisis le dossier « ranger » du modèle (celui créé par « Ranger les\n"
                       "médias », avec les sous-dossiers semaine-XX / jour-Y / créneaux).").pack(anchor="w")
        ligne_dm = ttk.Frame(dm)
        ligne_dm.pack(anchor="w", pady=(6, 2))
        ttk.Button(ligne_dm, text="Importer le dossier…",
                   command=self.choisir_dossier_planif).pack(side="left")
        defaut = self._dossier_planning()
        txt_dm = defaut if os.path.isdir(defaut) else "Aucun dossier sélectionné"
        self.lbl_dossier_planif = ttk.Label(dm, text=f"Dossier : {txt_dm}", style="Sous.TLabel")
        self.lbl_dossier_planif.pack(anchor="w")

        # Réglages du planning.
        reg = ttk.LabelFrame(self.conteneur, text="Planning", padding=8)
        reg.pack(fill="x", pady=(10, 0))
        ttk.Label(reg, text="Date de début (jour-1 de la semaine-01) :").grid(
            row=0, column=0, sticky="w", padx=4, pady=4)
        self.champ_date = ttk.Entry(reg, width=16)
        self.champ_date.grid(row=0, column=1, sticky="w", padx=4, pady=4)
        self.champ_date.insert(0, date.today().strftime("%d/%m/%Y"))
        self.rattrapage_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(reg, text="Rattraper les créneaux déjà passés (au démarrage)",
                        variable=self.rattrapage_var, style="TCheckbutton").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 4))
        self.planif_essai_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(reg, text="Essai (déroule tout SANS publier — pour tester)",
                        variable=self.planif_essai_var, style="TCheckbutton").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        self.demarrage_win_var = tk.BooleanVar(value=demarrage.est_actif())
        ttk.Checkbutton(reg, text="Lancer HelpVA au démarrage de Windows (reprise auto)",
                        variable=self.demarrage_win_var, command=self._maj_demarrage_windows,
                        style="TCheckbutton").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        ttk.Button(reg, text="Vérifier le planning",
                   command=self.verifier_planning).grid(row=0, column=2, padx=8)

        # État + boutons marche/arrêt.
        self.lbl_planif = ttk.Label(self.conteneur, text="⏸ Automatisation arrêtée",
                                    style="Sous.TLabel")
        self.lbl_planif.pack(anchor="w", pady=(10, 4))
        ligne = ttk.Frame(self.conteneur)
        ligne.pack(anchor="w", pady=(0, 4))
        self.btn_demarrer = ttk.Button(ligne, text="▶ Démarrer l'automatisation",
                                       style="Primaire.TButton", command=self.demarrer_planif)
        self.btn_demarrer.pack(side="left", padx=4)
        self.btn_arreter = ttk.Button(ligne, text="■ Arrêter", style="Retour.TButton",
                                      command=self.arreter_planif, state="disabled")
        self.btn_arreter.pack(side="left", padx=4)

        self._zone_log()
        # Reflète l'état si l'automatisation tourne déjà (retour sur l'écran).
        if self.planif_actif:
            self._maj_boutons_planif(True)

    def _maj_boutons_planif(self, actif: bool):
        """Active/désactive les boutons selon l'état (thread-safe via after)."""
        try:
            if hasattr(self, "btn_demarrer") and self.btn_demarrer.winfo_exists():
                self.btn_demarrer.configure(state="disabled" if actif else "normal")
                self.btn_arreter.configure(state="normal" if actif else "disabled")
                self.lbl_planif.configure(
                    text="⏺ Automatisation ACTIVE — laisse l'app ouverte."
                    if actif else "⏸ Automatisation arrêtée")
        except Exception:
            pass

    def verifier_planning(self):
        """Affiche un bilan du planning (sans rien publier)."""
        dossier = self._dossier_planning()
        if not os.path.isdir(dossier):
            messagebox.showwarning("Planning",
                                   "Aucun dossier « ranger » trouvé pour ce modèle.\n"
                                   "Fais d'abord « Ranger les médias ».")
            return
        d = self._lire_date_debut()
        if not d:
            return
        creneaux = planificateur.lister_creneaux(dossier, d)
        etat = planificateur.charger_etat(dossier)
        r = planificateur.resume(creneaux, etat, datetime.now())
        prochain = r["prochain"]
        if prochain:
            ph = prochain["quand"].strftime("%d/%m/%Y à %Hh%M")
            ligne_prochain = f"\n➡️ Prochaine publication auto : {prochain['type']} le {ph}"
        else:
            ligne_prochain = "\n➡️ Aucune publication auto à venir."
        msg = (f"Publications automatiques (reels + carrousels) : {r['total_auto']}\n"
               f"• Déjà publiées : {r['publies']}\n"
               f"• À venir : {r['a_venir']}\n"
               f"• En retard (pas encore publiées) : {r['en_retard']}\n"
               f"Stories (manuelles, non automatisées) : {r['stories']}"
               f"{ligne_prochain}")
        print("\n=== Vérification du planning ===")
        print(msg)
        messagebox.showinfo("Planning", msg)

    def demarrer_planif(self):
        if self.planif_actif:
            return
        uid = self._profil()
        if not uid:
            messagebox.showwarning("Profil", "Choisis d'abord un profil "
                                   "(Enregistrer + charger profils).")
            return
        dossier = self._dossier_planning()
        if not os.path.isdir(dossier):
            messagebox.showwarning("Planning",
                                   "Aucun dossier « ranger » trouvé pour ce modèle.\n"
                                   "Fais d'abord « Ranger les médias ».")
            return
        d = self._lire_date_debut()
        if not d:
            return

        rattrapage = self.rattrapage_var.get()
        essai = self.planif_essai_var.get()
        # Mémorise la config pour reprendre automatiquement au prochain lancement.
        self.params.update({
            "auto_actif": True, "auto_profil": uid, "auto_dossier": dossier,
            "auto_date_debut": d.isoformat(), "auto_rattrapage": rattrapage,
            "auto_essai": essai,
        })
        parametres.sauver(self.params)
        self.planif_actif = True
        self._maj_boutons_planif(True)
        if essai:
            print("\n▶ Automatisation démarrée en MODE ESSAI (rien ne sera publié).")
        else:
            print("\n▶ Automatisation démarrée. HelpVA publiera aux heures prévues.")
        print("   (laisse l'app et AdsPower ouverts ; elle reprendra seule si l'app se relance)")
        self.planif_thread = threading.Thread(
            target=self._boucle_planif, args=(uid, dossier, d, rattrapage, essai), daemon=True)
        self.planif_thread.start()

    def arreter_planif(self):
        if not self.planif_actif:
            return
        self.planif_actif = False
        self.params["auto_actif"] = False   # ne plus reprendre au prochain lancement
        parametres.sauver(self.params)
        self._maj_boutons_planif(False)
        print("\n■ Automatisation arrêtée (elle s'arrêtera après le créneau en cours).")

    def _reprendre_auto(self):
        """Relance l'automatisation seule si elle était active (après une
        fermeture de l'app ou un redémarrage du PC). Rattrape les posts manqués."""
        if self.planif_actif or not self.params.get("auto_actif"):
            return
        uid = self.params.get("auto_profil")
        dossier = self.params.get("auto_dossier")
        ds = self.params.get("auto_date_debut")
        if not (uid and dossier and ds and os.path.isdir(dossier)):
            return
        try:
            d = date.fromisoformat(ds)
        except Exception:
            return
        essai = self.params.get("auto_essai", False)
        self.planif_actif = True
        self._maj_boutons_planif(True)
        print("\n▶ Automatisation REPRISE automatiquement (rattrapage des posts manqués)…")
        self._notifier("Automatisation",
                       "▶ Automatisation reprise automatiquement.\n"
                       "Les publications manquées vont être rattrapées.")
        # rattrapage forcé à True : on rattrape tout ce qui a été manqué hors-ligne.
        self.planif_thread = threading.Thread(
            target=self._boucle_planif, args=(uid, dossier, d, True, essai), daemon=True)
        self.planif_thread.start()

    def _publier_creneau(self, driver, creneau, essai=False):
        """Publie un créneau selon son type. Lève une exception si échec.
        essai=True : déroule tout SANS cliquer Partager (test)."""
        typ = creneau["type"]
        medias = creneau["medias"]
        legende = creneau["legende"]
        if typ == "reel":
            instagram.poster_reel(driver, medias[0], legende, essai=essai)
        elif typ == "carousel":
            if len(medias) >= 2:
                instagram.poster_carrousel(driver, medias, legende, essai=essai)
            else:
                instagram.poster_publication(driver, medias[0], legende, essai=essai)
        else:  # sécurité : tout autre type avec 1 média -> publication simple
            instagram.poster_publication(driver, medias[0], legende, essai=essai)

    def _boucle_planif(self, uid, dossier, date_debut, rattrapage, essai=False):
        """Thread résistant : surveille le calendrier et publie chaque créneau
        à son heure jusqu'à l'arrêt. essai=True : ne publie pas vraiment.

        Si le navigateur/AdsPower lâche, on réessaie (au lieu de s'arrêter)."""
        debut = datetime.now()
        essai_faits = set()   # en mode essai : ne pas reboucler sur un créneau
        # Boucle EXTÉRIEURE : ré-ouvre le navigateur si la session échoue.
        while self.planif_actif:
            try:
                # S'assurer qu'AdsPower est ouvert (le lance au besoin, ex: au reboot).
                if not adspower.api_joignable():
                    print("[auto] AdsPower non détecté — ouverture en cours…")
                    if adspower.assurer_adspower():
                        print("[auto] ✅ AdsPower prêt.")
                    else:
                        print("[auto] ❌ AdsPower introuvable/non démarré. Réessai dans 60 s.")
                        print("[auto] (indique le chemin d'AdsPower dans l'écran si besoin)")
                        self._dormir_planif(60)
                        continue
                with navigateur_du_profil(uid) as driver:
                    print("[auto] navigateur prêt. Surveillance du calendrier…")
                    while self.planif_actif:
                        creneaux = planificateur.lister_creneaux(dossier, date_debut)
                        etat = planificateur.charger_etat(dossier)
                        dus = planificateur.a_publier_maintenant(
                            creneaux, etat, datetime.now(), rattrapage, debut)
                        if essai:
                            dus = [c for c in dus if c["id"] not in essai_faits]

                        if dus:
                            c = dus[0]   # le plus ancien d'abord
                            heure = c["quand"].strftime("%d/%m %Hh%M")
                            mode = " (ESSAI)" if essai else ""
                            print(f"\n[auto]{mode} Créneau {c['id']} "
                                  f"(prévu {heure}, type {c['type']})…")
                            try:
                                self._publier_creneau(driver, c, essai)
                                if essai:
                                    essai_faits.add(c["id"])
                                    print(f"[auto] ✅ ESSAI OK ({c['type']}) — non publié.")
                                else:
                                    planificateur.marquer(dossier, etat, c["id"], "publie")
                                    print(f"[auto] ✅ {c['type']} publié.")
                            except Exception as e:
                                if essai:
                                    essai_faits.add(c["id"])
                                else:
                                    planificateur.marquer(dossier, etat, c["id"], "echec")
                                print(f"[auto] ❌ Échec sur {c['id']} : {e}")
                                print("[auto] (créneau ignoré, on continue les suivants)")
                            self._dormir_planif(20)   # rythme humain
                        else:
                            self._dormir_planif(30)   # rien à faire, on revérifie
            except Exception as e:
                if not self.planif_actif:
                    break
                print(f"[auto] ⚠️ Problème navigateur/AdsPower : {e}")
                print("[auto] Nouvelle tentative dans 60 s… (vérifie qu'AdsPower est ouvert)")
                self._dormir_planif(60)   # puis la boucle extérieure ré-ouvre
        # Fin propre.
        self.planif_actif = False
        self.file_log.put(("planif_arret",))
        print("[auto] Automatisation terminée.")

    def _dormir_planif(self, secondes):
        """Dort par petits pas pour réagir vite à un Arrêt."""
        fin = time.time() + secondes
        while time.time() < fin and self.planif_actif:
            time.sleep(1)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
