"""
HelpVA — Générateur de licences + tableau de bord (OUTIL PRIVÉ DU VENDEUR).

⚠️ NE JAMAIS distribuer cet outil ni la clé privée à un client.

2 onglets :
  - « Générer »     : fabriquer une licence (à vie / mois / an) pour un client.
  - « Mes licences »: tableau de bord de toutes les licences générées
                      (client, empreinte, type, expiration, statut) + renouveler.

Les données sont dans licences.json (à côté de l'outil). La clé privée
(cle_privee.pem) doit être dans le même dossier (ou chargée via le bouton).
"""

import os
import sys
import json
from datetime import datetime, date
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Permet d'importer le paquet `agent` (format de licence partagé avec l'app).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives import serialization
from agent import licence as L
from agent import version

BG = "#0A0A0A"
JAUNE = "#FFC400"
BLANC = "#F5F5F5"
GRIS = "#9AA0A6"
VERT = "#5AD16A"
ROUGE = "#FF6B6B"
POLICE = "Segoe UI"

NOM_CLE = "cle_privee.pem"
NOM_DB = "licences.json"


def _dossier_base() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Admin:
    def __init__(self, root):
        self.root = root
        self.root.title(f"HelpVA — Licences  v{version.VERSION}")
        self.root.geometry("720x580")
        self.root.configure(bg=BG)
        self.cle = None
        self.chemin_cle = os.path.join(_dossier_base(), NOM_CLE)

        self._styles()
        self._construire()
        self._charger_cle(self.chemin_cle, silencieux=True)
        self._rafraichir_tableau()

    # ------------------------------------------------------------ styles

    def _styles(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TFrame", background=BG)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background="#1A1A1A", foreground=BLANC,
                    padding=(16, 8), font=(POLICE, 10, "bold"))
        s.map("TNotebook.Tab", background=[("selected", JAUNE)],
              foreground=[("selected", "#0A0A0A")])
        s.configure("TLabel", background=BG, foreground=BLANC, font=(POLICE, 10))
        s.configure("Titre.TLabel", background=BG, foreground=JAUNE, font=(POLICE, 15, "bold"))
        s.configure("Sous.TLabel", background=BG, foreground=GRIS, font=(POLICE, 9))
        s.configure("Etat.TLabel", background=BG, foreground=GRIS, font=(POLICE, 9, "bold"))
        s.configure("TButton", font=(POLICE, 10), padding=6)
        s.configure("Primaire.TButton", font=(POLICE, 11, "bold"), padding=8)
        s.configure("TRadiobutton", background=BG, foreground=BLANC, font=(POLICE, 10))
        s.map("TRadiobutton", background=[("active", BG)])
        s.configure("TEntry", fieldbackground="#1A1A1A", foreground=BLANC)
        # Tableau
        s.configure("Treeview", background="#141414", foreground=BLANC,
                    fieldbackground="#141414", rowheight=28, font=(POLICE, 10))
        s.configure("Treeview.Heading", background="#242424", foreground=JAUNE,
                    font=(POLICE, 10, "bold"))
        s.map("Treeview", background=[("selected", "#333355")])

    def _construire(self):
        entete = ttk.Frame(self.root, padding=(16, 12, 16, 4))
        entete.pack(fill="x")
        ttk.Label(entete, text="HelpVA — Licences", style="Titre.TLabel").pack(side="left")
        ttk.Label(entete, text=f"v{version.VERSION}", style="Sous.TLabel").pack(side="left", padx=(8, 0))
        ttk.Button(entete, text="Clé…", command=self._choisir_cle).pack(side="right", padx=(8, 0))
        self.lbl_cle = ttk.Label(entete, text="", style="Etat.TLabel")
        self.lbl_cle.pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        onglet_gen = ttk.Frame(nb, padding=14)
        onglet_dash = ttk.Frame(nb, padding=14)
        nb.add(onglet_gen, text="  Générer  ")
        nb.add(onglet_dash, text="  Mes licences  ")
        self._construire_generer(onglet_gen)
        self._construire_dashboard(onglet_dash)

    # ------------------------------------------------------------ onglet Générer

    def _construire_generer(self, c):
        ttk.Label(c, text="Nom du détenteur (affiché dans son app) :").pack(anchor="w", pady=(2, 2))
        self.champ_nom = ttk.Entry(c, width=40, font=(POLICE, 11))
        self.champ_nom.pack(anchor="w")

        ttk.Label(c, text="Empreinte reçue du client :").pack(anchor="w", pady=(10, 2))
        self.champ_emp = ttk.Entry(c, width=40, font=("Consolas", 13))
        self.champ_emp.pack(anchor="w", ipady=3)
        self.champ_emp.bind("<Return>", lambda e: self.generer())

        ttk.Label(c, text="Type d'abonnement :").pack(anchor="w", pady=(10, 2))
        self.type_var = tk.StringVar(value="vie")
        ligne_type = ttk.Frame(c)
        ligne_type.pack(anchor="w")
        for val, txt in (("essai", "Essai 3 jours"), ("vie", "À vie"),
                         ("mois", "Par mois"), ("an", "Par an")):
            ttk.Radiobutton(ligne_type, text=txt, value=val, variable=self.type_var,
                            command=self._maj_apercu).pack(side="left", padx=(0, 14))
        self.lbl_apercu = ttk.Label(c, text="", style="Sous.TLabel")
        self.lbl_apercu.pack(anchor="w", pady=(2, 0))

        self.premium_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(c, text="Automatisation des publications (Premium)",
                        variable=self.premium_var).pack(anchor="w", pady=(8, 0))

        ttk.Button(c, text="Générer la licence", style="Primaire.TButton",
                   command=self.generer).pack(anchor="w", pady=12)

        ttk.Label(c, text="Licence à renvoyer au client :").pack(anchor="w", pady=(2, 2))
        self.sortie = tk.Text(c, height=4, width=70, font=("Consolas", 10), wrap="char",
                              bg="#1A1A1A", fg=BLANC, insertbackground=BLANC,
                              relief="flat", padx=8, pady=8)
        self.sortie.pack(fill="x")
        self.sortie.configure(state="disabled")
        ttk.Button(c, text="Copier la licence", command=self._copier_sortie).pack(anchor="w", pady=8)
        self._maj_apercu()

    def _maj_apercu(self):
        t = self.type_var.get()
        exp = L.construire_payload("X", t, date.today()).get("exp")
        self.lbl_apercu.configure(
            text=f"→ Expire le {exp} (à partir d'aujourd'hui)." if exp
            else "→ Pas d'expiration (licence permanente).")

    def generer(self):
        if not self.cle:
            messagebox.showwarning("Clé privée", "Charge d'abord ta clé privée (cle_privee.pem).")
            return
        emp = self.champ_emp.get().strip().upper()
        if not emp:
            messagebox.showwarning("Empreinte", "Colle d'abord l'empreinte du client.")
            return
        nom = self.champ_nom.get().strip()
        t = self.type_var.get()
        premium = self.premium_var.get()
        licence = self._fabriquer(emp, t, nom, premium)
        if not licence:
            return
        self.sortie.configure(state="normal")
        self.sortie.delete("1.0", "end")
        self.sortie.insert("1.0", licence)
        self.sortie.configure(state="disabled")
        self.root.clipboard_clear()
        self.root.clipboard_append(licence)
        self._rafraichir_tableau()
        messagebox.showinfo("Licence générée",
                            f"✅ Licence {t} générée et copiée.\nEnregistrée dans le tableau de bord.")

    def _fabriquer(self, emp, type_licence, nom, premium=False):
        """Signe une licence, met à jour la base. Retourne la licence (ou None)."""
        try:
            payload = L.construire_payload(emp, type_licence, date.today(),
                                           nom=nom, premium=premium)
            licence = L.encoder_licence(payload, self.cle.sign)
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec de la génération :\n{e}")
            return None
        record = {
            "nom": nom,
            "emp": emp,
            "type": type_licence,
            "premium": bool(premium),
            "genere_le": date.today().isoformat(),
            "expire_le": payload.get("exp"),
            "licence": licence,
        }
        self._upsert(record)
        return licence

    def _copier_sortie(self):
        licence = self.sortie.get("1.0", "end").strip()
        if not licence:
            messagebox.showwarning("Copier", "Aucune licence à copier.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(licence)
        messagebox.showinfo("Copié", "Licence copiée.")

    # ------------------------------------------------------------ base de données

    def _chemin_db(self):
        return os.path.join(_dossier_base(), NOM_DB)

    def _charger_db(self) -> list:
        chemin = self._chemin_db()
        if os.path.isfile(chemin):
            try:
                with open(chemin, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _sauver_db(self, data: list):
        try:
            with open(self._chemin_db(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showwarning("Sauvegarde", f"Impossible d'écrire licences.json :\n{e}")

    def _upsert(self, record: dict):
        """Ajoute ou met à jour l'entrée pour cette empreinte (1 par appareil)."""
        data = self._charger_db()
        for i, r in enumerate(data):
            if r.get("emp") == record["emp"]:
                # garde l'ancien nom si le nouveau est vide
                if not record.get("nom") and r.get("nom"):
                    record["nom"] = r["nom"]
                data[i] = record
                break
        else:
            data.append(record)
        self._sauver_db(data)

    # ------------------------------------------------------------ onglet Dashboard

    def _construire_dashboard(self, c):
        haut = ttk.Frame(c)
        haut.pack(fill="x", pady=(0, 8))
        ttk.Label(haut, text="Rechercher :").pack(side="left")
        self.champ_recherche = ttk.Entry(haut, width=24)
        self.champ_recherche.pack(side="left", padx=6)
        self.champ_recherche.bind("<KeyRelease>", lambda e: self._rafraichir_tableau())
        self.filtre_bientot = tk.BooleanVar(value=False)
        ttk.Checkbutton(haut, text="Expire bientôt seulement", variable=self.filtre_bientot,
                        command=self._rafraichir_tableau).pack(side="left", padx=10)
        ttk.Button(haut, text="Rafraîchir", command=self._rafraichir_tableau).pack(side="right")

        cols = ("nom", "emp", "type", "expire", "statut")
        self.tableau = ttk.Treeview(c, columns=cols, show="headings", height=11)
        for col, txt, w in (("nom", "Client", 130), ("emp", "Empreinte", 170),
                            ("type", "Type", 60), ("expire", "Expire le", 100),
                            ("statut", "Statut", 130)):
            self.tableau.heading(col, text=txt)
            self.tableau.column(col, width=w, anchor="w")
        self.tableau.tag_configure("actif", foreground=VERT)
        self.tableau.tag_configure("vie", foreground=VERT)
        self.tableau.tag_configure("bientot", foreground=JAUNE)
        self.tableau.tag_configure("expire", foreground=ROUGE)
        self.tableau.pack(fill="both", expand=True)
        self.tableau.bind("<Double-1>", lambda e: self._copier_selection())

        self.lbl_resume = ttk.Label(c, text="", style="Sous.TLabel")
        self.lbl_resume.pack(anchor="w", pady=(6, 4))

        actions = ttk.Frame(c)
        actions.pack(fill="x", pady=(2, 0))
        ttk.Button(actions, text="Copier la licence",
                   command=self._copier_selection).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Essai 3j",
                   command=lambda: self._renouveler("essai")).pack(side="left", padx=6)
        ttk.Button(actions, text="Renouveler 1 mois",
                   command=lambda: self._renouveler("mois")).pack(side="left", padx=6)
        ttk.Button(actions, text="Renouveler 1 an",
                   command=lambda: self._renouveler("an")).pack(side="left", padx=6)
        ttk.Button(actions, text="Supprimer", command=self._supprimer).pack(side="right")

    def _statut(self, record):
        """Retourne (texte, tag) selon l'expiration."""
        t = record.get("type")
        exp = record.get("expire_le")
        if t == "vie" or not exp:
            return ("🟢 À vie", "vie")
        try:
            d = date.fromisoformat(exp)
        except Exception:
            return ("?", "expire")
        reste = (d - date.today()).days
        if reste < 0:
            return (f"🔴 Expiré ({-reste}j)", "expire")
        if reste <= 7:
            return (f"🟠 Expire ({reste}j)", "bientot")
        return (f"🟢 Actif ({reste}j)", "actif")

    def _rafraichir_tableau(self):
        if not hasattr(self, "tableau"):
            return
        for ligne in self.tableau.get_children():
            self.tableau.delete(ligne)
        recherche = self.champ_recherche.get().strip().lower() if hasattr(self, "champ_recherche") else ""
        bientot_seul = self.filtre_bientot.get() if hasattr(self, "filtre_bientot") else False
        data = self._charger_db()
        nb_actif = nb_bientot = nb_expire = 0
        for r in sorted(data, key=lambda x: (x.get("expire_le") or "9999")):
            texte, tag = self._statut(r)
            if tag == "actif" or tag == "vie":
                nb_actif += 1
            elif tag == "bientot":
                nb_bientot += 1
            elif tag == "expire":
                nb_expire += 1
            if bientot_seul and tag != "bientot":
                continue
            blob = f"{r.get('nom','')} {r.get('emp','')}".lower()
            if recherche and recherche not in blob:
                continue
            exp = r.get("expire_le") or "—"
            self.tableau.insert("", "end", values=(
                r.get("nom", ""), r.get("emp", ""), r.get("type", ""),
                exp, texte), tags=(tag,))
        self.lbl_resume.configure(
            text=f"Total : {len(data)}   ·   🟢 {nb_actif} actifs   "
                 f"·   🟠 {nb_bientot} expirent bientôt   ·   🔴 {nb_expire} expirés")

    def _record_selectionne(self):
        sel = self.tableau.selection()
        if not sel:
            messagebox.showinfo("Sélection", "Choisis d'abord une ligne dans le tableau.")
            return None
        emp = self.tableau.item(sel[0], "values")[1]
        for r in self._charger_db():
            if r.get("emp") == emp:
                return r
        return None

    def _copier_selection(self):
        r = self._record_selectionne()
        if not r:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(r.get("licence", ""))
        messagebox.showinfo("Copié", f"Licence de {r.get('nom') or r.get('emp')} copiée.")

    def _renouveler(self, type_licence):
        if not self.cle:
            messagebox.showwarning("Clé privée", "Charge d'abord ta clé privée.")
            return
        r = self._record_selectionne()
        if not r:
            return
        licence = self._fabriquer(r["emp"], type_licence, r.get("nom", ""),
                                  r.get("premium", False))
        if not licence:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(licence)
        self._rafraichir_tableau()
        exp = L.construire_payload("X", type_licence, date.today()).get("exp")
        messagebox.showinfo("Renouvelé",
                            f"✅ {r.get('nom') or r['emp']} renouvelé ({type_licence}).\n"
                            f"Nouvelle expiration : {exp}\nLicence copiée — renvoie-la au client.")

    def _supprimer(self):
        r = self._record_selectionne()
        if not r:
            return
        if not messagebox.askyesno("Supprimer",
                                   f"Retirer {r.get('nom') or r['emp']} du tableau ?\n"
                                   "(ça ne désactive pas sa licence, ça l'enlève juste de la liste)"):
            return
        data = [x for x in self._charger_db() if x.get("emp") != r["emp"]]
        self._sauver_db(data)
        self._rafraichir_tableau()

    # ------------------------------------------------------------ clé privée

    def _charger_cle(self, chemin, silencieux=False):
        try:
            with open(chemin, "rb") as f:
                self.cle = serialization.load_pem_private_key(f.read(), password=None)
            self.chemin_cle = chemin
            self.lbl_cle.configure(text=f"🔑 Clé privée chargée", foreground=VERT)
            return True
        except Exception as e:
            self.cle = None
            self.lbl_cle.configure(text="⚠️ Clé privée introuvable", foreground=ROUGE)
            if not silencieux:
                messagebox.showwarning("Clé privée", f"Impossible de charger la clé :\n{e}")
            return False

    def _choisir_cle(self):
        chemin = filedialog.askopenfilename(
            title="Choisir cle_privee.pem",
            filetypes=[("Clé privée PEM", "*.pem"), ("Tous", "*.*")])
        if chemin:
            self._charger_cle(chemin)


def main():
    root = tk.Tk()
    app = Admin(root)
    # Bouton discret pour recharger la clé si besoin (menu clic droit sur l'état).
    root.mainloop()


if __name__ == "__main__":
    main()
