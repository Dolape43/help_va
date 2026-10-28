"""
Tests du moteur HelpVA (protocole JSON-lines) — bibliothèque standard uniquement.

Lancement :
    cd engine
    python -m unittest -v

Chaque test lance le VRAI moteur (helpva_engine.py) comme sous-processus, comme
le fera Tauri, et lui parle par ses tubes. Sécurité : APPDATA, USERPROFILE et
HOME pointent vers un dossier TEMPORAIRE -> on ne touche jamais aux vraies
données (%APPDATA%\\HelpVA) ni au vrai Bureau.

Les vidéos de test sont fabriquées à la volée avec le ffmpeg d'imageio-ffmpeg.
Les dossiers ont volontairement des espaces et des accents / caractères Unicode.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER_ENGINE = os.path.dirname(ICI)
MOTEUR = os.path.join(DOSSIER_ENGINE, "helpva_engine.py")
PONT = os.path.join(DOSSIER_ENGINE, "dev_bridge.py")
FINAUX = ("result", "error")


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg(*args) -> None:
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args],
                   check=True, stdin=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def codec_video(chemin: str) -> str:
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", chemin],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    err = r.stderr.decode("utf-8", "ignore")
    return "h264" if "Video: h264" in err else err[-300:]


def processus_vivant(pid: int) -> bool:
    """Sans os.kill (qui, sous Windows, TUERAIT le processus)."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
        return code.value == 259                    # STILL_ACTIVE
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


# ═══════════════════════════════════════════════════════════════════════════
#  Un petit client du protocole (ce que fera l'interface, en TypeScript)
# ═══════════════════════════════════════════════════════════════════════════
class ClientMoteur:
    def __init__(self, env: dict, cwd: str):
        self.proc = subprocess.Popen([sys.executable, MOTEUR], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=env, cwd=cwd)
        self.evenements = []
        self.lignes_invalides = []
        self.stderr = []
        self._cond = threading.Condition()
        self._n = 0
        threading.Thread(target=self._lire, daemon=True).start()
        threading.Thread(target=self._lire_stderr, daemon=True).start()
        self.pret = self.attendre(lambda e: e.get("type") == "pret", 20)

    def _lire(self):
        for brut in self.proc.stdout:
            try:
                brut.decode("ascii")                 # le protocole est 100 % ASCII
                ev = json.loads(brut)
                if not isinstance(ev, dict) or "type" not in ev or "id" not in ev:
                    raise ValueError("pas un événement")
            except (UnicodeDecodeError, ValueError):
                with self._cond:
                    self.lignes_invalides.append(brut)
                continue
            with self._cond:
                self.evenements.append(ev)
                self._cond.notify_all()
        with self._cond:
            self._cond.notify_all()

    def _lire_stderr(self):
        for brut in self.proc.stderr:
            self.stderr.append(brut)

    def envoyer(self, cmd: str, args=None, rid: str = None) -> str:
        if rid is None:
            self._n += 1
            rid = f"t-{self._n}"
        req = {"id": rid, "cmd": cmd}
        if args is not None:
            req["args"] = args
        self.envoyer_brut(json.dumps(req, ensure_ascii=False).encode("utf-8") + b"\n")
        return rid

    def envoyer_brut(self, donnees: bytes):
        self.proc.stdin.write(donnees)
        self.proc.stdin.flush()

    def attendre(self, predicat, delai: float = 30.0):
        fin = time.monotonic() + delai
        with self._cond:
            while True:
                for ev in self.evenements:
                    if predicat(ev):
                        return ev
                reste = fin - time.monotonic()
                if reste <= 0:
                    raise AssertionError(
                        f"Délai dépassé. Derniers événements : {self.evenements[-5:]}\n"
                        f"stderr : {b''.join(self.stderr)[-2000:]!r}")
                self._cond.wait(min(reste, 0.5))

    def fin(self, rid: str, delai: float = 60.0) -> dict:
        return self.attendre(lambda e: e.get("id") == rid and e.get("type") in FINAUX, delai)

    def appeler(self, cmd: str, args=None, delai: float = 60.0) -> dict:
        return self.fin(self.envoyer(cmd, args), delai)

    def de(self, rid: str, typ: str = None) -> list:
        with self._cond:
            return [e for e in self.evenements
                    if e.get("id") == rid and (typ is None or e.get("type") == typ)]

    def fermer(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()            # EOF -> le moteur s'arrête seul
                self.proc.wait(timeout=8)
            except Exception:
                pass
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
        for tube in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                tube.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
#  Les tests
# ═══════════════════════════════════════════════════════════════════════════
class TestProtocole(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Espaces + accents + Unicode dans TOUS les chemins.
        cls.tmp = tempfile.mkdtemp(prefix="HelpVA tést ")
        cls.appdata = os.path.join(cls.tmp, "Données appli")
        cls.home = os.path.join(cls.tmp, "Profil utilisateur")
        os.makedirs(cls.appdata)
        os.makedirs(os.path.join(cls.home, "Desktop"))

        # Vidéos : un dossier avec un sous-dossier (2 « groupes »).
        cls.videos = os.path.join(cls.tmp, "Vidéos du shooting")
        os.makedirs(os.path.join(cls.videos, "Modèle A"))
        cls.video_avi = os.path.join(cls.videos, "clip é 01.avi")      # mpeg4 -> ré-encodage
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
               "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
               "-c:v", "mpeg4", "-q:v", "5", "-c:a", "pcm_s16le", "-shortest", cls.video_avi)
        cls.video_mkv = os.path.join(cls.videos, "Modèle A", "clip 02 ☀.mkv")  # h264 -> remux
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
               "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", cls.video_mkv)
        with open(os.path.join(cls.videos, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("pas une vidéo")

        # Une vidéo LONGUE pour l'annulation (60 s en 720p : plusieurs secondes de travail).
        cls.longues = os.path.join(cls.tmp, "Longues vidéos")
        os.makedirs(cls.longues)
        cls.video_longue = os.path.join(cls.longues, "longue vidéo.avi")
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=60",
               "-c:v", "mpeg4", "-q:v", "12", cls.video_longue)

        # Images (PNG) pour la conversion d'images, les métadonnées et le rangement.
        cls.images = os.path.join(cls.tmp, "Images été")
        os.makedirs(cls.images)
        for i in (1, 2, 3):
            # Tailles différentes : 3 images DIFFÉRENTES (le compteur d'activité ignore les doublons).
            ffmpeg("-f", "lavfi", "-i", f"testsrc=size=96x{62 + i * 2}:rate=1:duration=1",
                   "-frames:v", "1", os.path.join(cls.images, f"{i} photo ☀.png"))
        cls.vide = os.path.join(cls.tmp, "Dossier vide")
        os.makedirs(cls.vide)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ----------------------------------------------------------------- outils
    def env(self, sans_licence: bool = True, appdata: str = None, home: str = None) -> dict:
        appdata, home = appdata or self.appdata, home or self.home
        env = dict(os.environ)
        env.update({"APPDATA": appdata, "USERPROFILE": home, "HOME": home,
                    "XDG_DATA_HOME": appdata, "HELPVA_MOTEUR_TESTS": "1"})
        env.pop("HELPVA_MOTEUR_SANS_LICENCE", None)
        if sans_licence:
            env["HELPVA_MOTEUR_SANS_LICENCE"] = "1"
        return env

    def moteur(self, sans_licence: bool = True, appdata: str = None,
               home: str = None) -> ClientMoteur:
        c = ClientMoteur(self.env(sans_licence, appdata, home), cwd=self.tmp)
        self.addCleanup(self._verifier_et_fermer, c)
        return c

    def profil_isole(self, nom: str):
        """APPDATA et profil NEUFS (toujours dans le dossier temporaire) : les comptes du
        Ranger d'un test ne dépendent ni de l'ordre des tests ni des autres tests."""
        appdata = os.path.join(self.tmp, nom, "Données appli")
        home = os.path.join(self.tmp, nom, "Profil")
        os.makedirs(appdata)
        os.makedirs(os.path.join(home, "Desktop"))
        return appdata, home

    def _verifier_et_fermer(self, c: ClientMoteur):
        c.fermer()
        # Quoi qu'il arrive dans le test : AUCUNE ligne non-JSON sur stdout.
        self.assertEqual(c.lignes_invalides, [], "stdout corrompu par des lignes non-JSON")

    def nouvelle_sortie(self, c: ClientMoteur, nom: str) -> str:
        sortie = os.path.join(self.tmp, nom)
        r = c.appeler("parametres_ecrire", {"valeurs": {"dossier_sortie": sortie}})
        self.assertEqual(r["type"], "result", r)
        return sortie

    def assertResultat(self, ev: dict) -> dict:
        self.assertEqual(ev["type"], "result", ev)
        return ev["data"]

    def assertErreur(self, ev: dict, code: str) -> dict:
        self.assertEqual(ev["type"], "error", ev)
        self.assertEqual(ev["code"], code, ev)
        self.assertIsInstance(ev["message"], str)
        return ev

    # ----------------------------------------------------------------- démarrage
    def test_poignee_de_main(self):
        c = self.moteur()
        self.assertEqual(c.pret["id"], None)
        self.assertEqual(c.pret["nom"], "HelpVA")
        self.assertEqual(c.pret["protocole"], 1)
        self.assertIsInstance(c.pret["pid"], int)
        self.assertFalse(c.pret["frozen"])
        self.assertEqual(self.assertResultat(c.appeler("ping")), {"pong": True})

    def test_info(self):
        c = self.moteur()
        d = self.assertResultat(c.appeler("info"))
        self.assertEqual(d["protocole"], 1)
        self.assertIn(".mov", d["extensions"]["videos_mp4"])
        self.assertIn(".heic", d["extensions"]["images_conversion"])
        self.assertEqual([t["type"] for t in d["types_ranger"]],
                         ["reel", "story", "story_cta", "carousel"])
        # Les données vont dans le APPDATA TEMPORAIRE, jamais dans le vrai.
        self.assertTrue(os.path.normcase(d["dossier_donnees"]).startswith(
            os.path.normcase(self.appdata)), d["dossier_donnees"])
        self.assertTrue(os.path.normcase(d["dossier_sortie_defaut"]).startswith(
            os.path.normcase(self.home)))
        self.assertIn("conversion_mp4", d["commandes"])

    # ----------------------------------------------------------------- paramètres
    def test_parametres_aller_retour(self):
        c = self.moteur()
        sortie = os.path.join(self.tmp, "Sortie été ☀")
        valeurs = {"theme": "dark", "dossier_sortie": sortie,
                   "ranger_types": {"reel": True, "story": False}}
        ecrit = self.assertResultat(c.appeler("parametres_ecrire", {"valeurs": valeurs}))
        self.assertTrue(ecrit["personnalise"])
        lu = self.assertResultat(c.appeler("parametres_lire"))
        self.assertEqual(lu["parametres"]["theme"], "dark")
        self.assertEqual(lu["parametres"]["dossier_sortie"], sortie)
        self.assertEqual(lu["parametres"]["ranger_types"], {"reel": True, "story": False})
        self.assertEqual(lu["dossier_sortie"], sortie)
        self.assertTrue(os.path.isdir(sortie))
        # Le fichier est bien dans le APPDATA temporaire.
        with open(os.path.join(self.appdata, "HelpVA", "parametres.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["dossier_sortie"], sortie)
        # dossier_sortie (effectif)
        ds = self.assertResultat(c.appeler("dossier_sortie"))
        self.assertEqual(ds["chemin"], sortie)
        # Clé inconnue / mauvaise valeur -> refus clair.
        self.assertErreur(c.appeler("parametres_ecrire", {"valeurs": {"pirate": 1}}),
                          "ARGUMENTS_INVALIDES")
        e = self.assertErreur(c.appeler("parametres_ecrire", {"valeurs": {"theme": "rose"}}),
                              "ARGUMENTS_INVALIDES")
        self.assertEqual(e["details"]["champ"], "valeurs.theme")
        # Retour au défaut (Bureau du profil temporaire).
        lu = self.assertResultat(c.appeler("parametres_ecrire", {"valeurs": {"dossier_sortie": ""}}))
        self.assertFalse(lu["personnalise"])
        self.assertEqual(lu["dossier_sortie"], os.path.join(self.home, "Desktop", "HelpVA"))

    def test_parametres_choix_par_defaut_et_fin(self):
        appdata, home = self.profil_isole("Paramètres choix")
        c = self.moteur(appdata=appdata, home=home)
        p = self.assertResultat(c.appeler("parametres_lire"))["parametres"]
        # Défauts : jpg, false, false, true, true, false, true.
        self.assertEqual({k: p[k] for k in ("format_images", "renommer_images", "renommer_mp4",
                                            "renommer_metadonnees", "ranger_aleatoire",
                                            "fin_ouvrir_dossier", "fin_notification")},
                         {"format_images": "jpg", "renommer_images": False, "renommer_mp4": False,
                          "renommer_metadonnees": True, "ranger_aleatoire": True,
                          "fin_ouvrir_dossier": False, "fin_notification": True})
        valeurs = {"format_images": "png", "renommer_images": True, "renommer_mp4": True,
                   "renommer_metadonnees": False, "ranger_aleatoire": False,
                   "fin_ouvrir_dossier": True, "fin_notification": False}
        self.assertResultat(c.appeler("parametres_ecrire", {"valeurs": valeurs}))
        p = self.assertResultat(c.appeler("parametres_lire"))["parametres"]
        self.assertEqual({k: p[k] for k in valeurs}, valeurs)
        # Mauvais types -> refus clair, qui nomme le champ.
        for cle, val in (("format_images", "gif"), ("format_images", True),
                         ("renommer_mp4", "oui"), ("fin_notification", 1)):
            e = self.assertErreur(c.appeler("parametres_ecrire", {"valeurs": {cle: val}}),
                                  "ARGUMENTS_INVALIDES")
            self.assertEqual(e["details"]["champ"], f"valeurs.{cle}")

    # ----------------------------------------------------------------- licence
    def test_licence_requise_sans_contournement(self):
        c = self.moteur(sans_licence=False)
        st = self.assertResultat(c.appeler("licence_statut"))
        self.assertFalse(st["ok"])
        # Pas de licence -> offre gratuite, qui demande le serveur (coupé pendant les tests).
        self.assertEqual(st["raison"], "pas_internet")
        self.assertEqual(st["type"], "gratuit")
        self.assertIsNone(st["essai"])
        self.assertRegex(st["empreinte"], r"^[A-Z2-7]{4}(-[A-Z2-7]{4}){3}$")
        self.assertErreur(c.appeler("conversion_mp4", {"source": {"type": "dossier",
                                                                  "chemin": self.videos}}),
                          "LICENCE_REQUISE")
        info = self.assertResultat(c.appeler("info"))
        self.assertFalse(info["licence_contournee_dev"])

    # ----------------------------------------------------------------- conversion MP4
    def test_conversion_mp4_dossier_reelle(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie conversion é")
        rid = c.envoyer("conversion_mp4", {"source": {"type": "dossier", "chemin": self.videos}})
        d = self.assertResultat(c.fin(rid, 120))
        sortie = os.path.join(base, "media (mp4)")
        self.assertEqual(d["sortie"], sortie)
        self.assertEqual(d["traites"], 2)
        self.assertEqual(d["echecs"], [])
        self.assertFalse(d["arrete"])
        self.assertEqual(d["dossiers"], 2)
        # Mêmes noms et même arborescence que la source.
        mp4_1 = os.path.join(sortie, "clip é 01.mp4")
        mp4_2 = os.path.join(sortie, "Modèle A", "clip 02 ☀.mp4")
        self.assertTrue(os.path.isfile(mp4_1))
        self.assertTrue(os.path.isfile(mp4_2))
        self.assertEqual(codec_video(mp4_1), "h264")
        self.assertEqual(codec_video(mp4_2), "h264")
        # Progression : texte + fraction, et détails structurés (noms COMPLETS).
        prog = c.de(rid, "progress")
        self.assertGreater(len(prog), 2)
        for p in prog:
            self.assertIsInstance(p["texte"], str)
            self.assertTrue(p["texte"])
            self.assertGreaterEqual(p["fraction"], 0.0)
            self.assertLessEqual(p["fraction"], 1.0)
        textes = [p["texte"] for p in prog]
        self.assertTrue(any(t.startswith("Dossier 1/2") for t in textes), textes)
        self.assertTrue(any("Dossier 2/2 — Modèle A" in t for t in textes), textes)
        self.assertTrue(any(p["details"] and p["details"]["element"]["nom"] == "clip 02 ☀.mkv"
                            for p in prog))
        self.assertTrue(any(p["details"]["groupe"] and p["details"]["groupe"]["nom"] == "Modèle A"
                            for p in prog))
        # Journal : les print() d'agent/ arrivent en événements « log ».
        logs = [l["texte"] for l in c.de(rid, "log")]
        self.assertIn("[convert] (1/1) clip é 01.avi…", logs)
        self.assertTrue(any(l.startswith("✅ 2 vidéo(s) en .mp4") for l in logs), logs)
        # Message de fin identique à l'ancienne app.
        self.assertEqual(d["bilan"]["titre"], "Conversion terminée")
        self.assertTrue(d["bilan"]["message"].startswith(
            "✅ 2 vidéo(s) en .mp4 traité(s) dans 2 dossier(s) !"), d["bilan"])
        self.assertFalse(d["bilan"]["erreur"])

    def test_conversion_mp4_fichiers(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie fichiers ☀")
        d = self.assertResultat(c.appeler(
            "conversion_mp4", {"source": {"type": "fichiers", "chemins": [self.video_mkv]}}, 120))
        self.assertEqual(d["traites"], 1)
        self.assertTrue(os.path.isfile(os.path.join(base, "media (mp4)", "clip 02 ☀.mp4")))
        self.assertTrue(d["bilan"]["message"].startswith("✅ 1 vidéo(s) en .mp4 traité(s) !"))
        # preparer signale le .mp4 qui sera écrasé si on relance.
        p = self.assertResultat(c.appeler("preparer", {"commande": "conversion_mp4", "args": {
            "source": {"type": "fichiers", "chemins": [self.video_mkv, self.video_avi]}}}))
        self.assertEqual(p["deja_presents"], 1)
        self.assertFalse(p["remplacement"])

    def test_annulation_conversion_longue(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie annulation")
        args = {"source": {"type": "fichiers", "chemins": [self.video_longue]}}
        rid = c.envoyer("conversion_mp4", args)
        # On attend que ffmpeg travaille vraiment (pourcentage > 0).
        c.attendre(lambda e: e.get("id") == rid and e.get("type") == "progress"
                   and (e.get("details") or {}).get("element", {}).get("pct") not in (None, 0), 60)
        # Une 2e tâche longue pendant ce temps -> OCCUPE ; même id -> ID_DUPLIQUE.
        e = self.assertErreur(c.appeler("conversion_mp4", args), "OCCUPE")
        self.assertEqual(e["details"]["tache"], rid)
        # (l'erreur ID_DUPLIQUE porte id null : sinon le client croirait que SA
        #  conversion en cours a échoué)
        c.envoyer("info", None, rid=rid)
        e = c.attendre(lambda ev: ev.get("type") == "error" and ev.get("code") == "ID_DUPLIQUE", 10)
        self.assertIsNone(e["id"])
        self.assertEqual(e["details"]["id"], rid)
        # Même règle pour les commandes de contrôle : un « ping » avec l'id de la conversion
        # ne doit PAS répondre sous cet id (sinon deux événements finaux pour une requête).
        c.envoyer("ping", None, rid=rid)
        c.attendre(lambda ev: ev.get("type") == "error" and ev.get("code") == "ID_DUPLIQUE"
                   and ev["details"].get("cmd") == "ping", 10)
        self.assertEqual(c.de(rid, "result"), [])
        # Les commandes rapides marchent PENDANT la conversion.
        etat = self.assertResultat(c.appeler("etat", None, 10))
        self.assertTrue(etat["occupe"])
        self.assertEqual(etat["tache"]["id"], rid)
        # Annulation : la tâche doit finir en moins de 2 s.
        t0 = time.monotonic()
        r = self.assertResultat(c.appeler("annuler", {"cible": rid}, 10))
        self.assertEqual(r["etat"], "annulation_demandee")
        d = self.assertResultat(c.fin(rid, 10))
        duree = time.monotonic() - t0
        self.assertLess(duree, 2.0, f"annulation trop lente : {duree:.2f} s")
        self.assertTrue(d["arrete"])
        self.assertEqual(d["traites"], 0)
        self.assertEqual(d["bilan"]["titre"], "Interrompu")
        # Pas de fichier à moitié converti.
        self.assertFalse(os.path.exists(os.path.join(base, "media (mp4)", "longue vidéo.mp4")))
        logs = [l["texte"] for l in c.de(rid, "log")]
        self.assertTrue(any("⛔ arrêté pendant : longue vidéo.avi" in l for l in logs), logs)
        self.assertTrue(any(l["niveau"] == "arret" for l in c.de(rid, "log")))
        # Annuler encore : idempotent.
        r2 = self.assertResultat(c.appeler("annuler", {"cible": rid}, 10))
        self.assertEqual(r2["etat"], "deja_terminee")
        # La place est libre : une nouvelle tâche longue est acceptée.
        self.assertFalse(self.assertResultat(c.appeler("etat"))["occupe"])

    # ----------------------------------------------------------------- erreurs
    def test_erreurs(self):
        c = self.moteur()
        self.nouvelle_sortie(c, "Sortie erreurs")
        e = self.assertErreur(c.appeler("commande_qui_n_existe_pas"), "COMMANDE_INCONNUE")
        self.assertEqual(e["details"]["cmd"], "commande_qui_n_existe_pas")
        # Ligne illisible -> erreur sans id, et le moteur continue.
        c.envoyer_brut(b"ceci n'est pas du JSON\n")
        c.attendre(lambda ev: ev.get("type") == "error" and ev.get("code") == "JSON_INVALIDE", 10)
        c.envoyer_brut(b'{"cmd":"ping"}\n')
        c.attendre(lambda ev: ev.get("type") == "error" and ev.get("id") is None
                   and (ev.get("details") or {}).get("champ") == "id", 10)
        self.assertResultat(c.appeler("ping"))
        e = self.assertErreur(c.appeler("conversion_mp4", {}), "ARGUMENTS_INVALIDES")
        self.assertEqual(e["details"]["champ"], "source")
        self.assertErreur(c.appeler("conversion_mp4", {"source": {"type": "dossier",
                                                                  "chemin": "relatif"}}),
                          "ARGUMENTS_INVALIDES")
        absent = os.path.join(self.tmp, "n'existe pas é")
        e = self.assertErreur(c.appeler("conversion_mp4", {"source": {"type": "dossier",
                                                                      "chemin": absent}}),
                              "SOURCE_INTROUVABLE")
        self.assertEqual(e["details"]["chemins"], [absent])
        self.assertErreur(c.appeler("conversion_mp4", {"source": {"type": "dossier",
                                                                  "chemin": self.vide}}),
                          "SOURCE_VIDE")
        self.assertErreur(c.appeler("ouvrir_dans_explorateur", {"chemin": self.video_avi}),
                          "CHEMIN_REFUSE")
        self.assertErreur(c.appeler("annuler", {}), "ARGUMENTS_INVALIDES")
        self.assertEqual(self.assertResultat(c.appeler("annuler", {"cible": "x"}))["etat"],
                         "deja_terminee")
        if sys.platform == "win32":
            # « \\Users\\x » dépend du lecteur courant : refusé (Python 3.10 à 3.12 le disait absolu).
            e = self.assertErreur(c.appeler("conversion_mp4", {"source": {
                "type": "dossier", "chemin": "\\Users\\x"}}), "ARGUMENTS_INVALIDES")
            self.assertEqual(e["details"]["champ"], "source.chemin")
            # Chemin trop long pour Windows : message clair, pas « introuvable ».
            long = os.path.join(self.tmp, *(["dossier au nom assez long"] * 12))
            e = self.assertErreur(c.appeler("conversion_mp4", {"source": {
                "type": "dossier", "chemin": long}}), "CHEMIN_TROP_LONG")
            self.assertEqual(e["details"]["chemins"], [long])
        # Ligne avec un BOM UTF-8 au début : acceptée.
        c.envoyer_brut(b'\xef\xbb\xbf{"id":"bom-1","cmd":"ping"}\n')
        self.assertResultat(c.fin("bom-1", 10))
        # NaN n'est pas du JSON : refusé, mais l'erreur porte l'id (lu au début de la ligne).
        c.envoyer_brut(b'{"id":"nan-1","cmd":"quitter","args":{"delai_s":NaN}}\n')
        self.assertErreur(c.fin("nan-1", 10), "JSON_INVALIDE")
        # Ligne de plus de 16 Mo : TROP_GROS, avec son id (sinon l'interface attendrait toujours).
        c.envoyer_brut(b'{"id":"gros-1","cmd":"conversion_mp4","args":{"x":"'
                       + b"a" * (17 * 1024 * 1024) + b'"}}\n')
        self.assertErreur(c.fin("gros-1", 30), "TROP_GROS")
        self.assertResultat(c.appeler("ping"))          # le moteur continue

    def test_stdout_reste_propre(self):
        """print(), stderr, écriture brute sur le fd 1 et sous-processus : rien ne
        doit casser le JSON. Et un enfant (comme ffmpeg) lit une entrée VIDE."""
        c = self.moteur()
        rid = c.envoyer("_diagnostic_bruit")
        d = self.assertResultat(c.fin(rid, 60))
        self.assertEqual(d["octets_lus_par_enfant"], 0)
        logs = c.de(rid, "log")
        textes = [l["texte"] for l in logs]
        self.assertIn("bruit print é ⛔ 漢字", textes)
        self.assertIn("début de ligne… fin de ligne", textes)
        self.assertTrue(any(l["flux"] == "stderr" and l["texte"] == "bruit stderr ⚠️"
                            and l["niveau"] == "avertissement" for l in logs))
        self.assertFalse(any("BRUIT" in t for t in textes))
        self.assertResultat(c.appeler("ping"))
        self.assertEqual(c.lignes_invalides, [])

    # ----------------------------------------------------------------- images / métadonnées
    def test_conversion_images_et_remplacement(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie images")
        args = {"source": {"type": "dossier", "chemin": self.images}, "format": "jpg"}
        d = self.assertResultat(c.appeler("conversion_images", args, 120))
        sortie = os.path.join(base, "images (jpg)")
        self.assertEqual(d["sortie"], sortie)
        self.assertEqual(d["traites"], 3)
        self.assertTrue(os.path.isfile(os.path.join(sortie, "1 photo ☀.jpg")))
        self.assertTrue(d["bilan"]["message"].startswith("✅ 3 image(s) en .jpg traité(s) !"))
        # La sortie existe : « preparer » prévient, la commande refuse sans « remplacer ».
        p = self.assertResultat(c.appeler("preparer", {"commande": "conversion_images",
                                                       "args": args}))
        self.assertTrue(p["existe"])
        self.assertTrue(p["remplacement"])
        self.assertEqual(p["nb_medias"], 3)
        self.assertErreur(c.appeler("conversion_images", args), "SORTIE_EXISTE")
        temoin = os.path.join(sortie, "ancien.txt")
        open(temoin, "w").close()
        # « remplacer » doit être le CHEMIN confirmé, pas un simple true.
        e = self.assertErreur(c.appeler("conversion_images", dict(args, remplacer=True)),
                              "ARGUMENTS_INVALIDES")
        self.assertEqual(e["details"]["champ"], "remplacer")
        # Un AUTRE chemin que la vraie sortie : rien n'est supprimé.
        e = self.assertErreur(c.appeler("conversion_images", dict(
            args, remplacer=os.path.join(base, "autre dossier"))), "SORTIE_EXISTE")
        self.assertEqual(e["details"]["sortie"], sortie)
        self.assertTrue(os.path.exists(temoin))
        # Un fichier OUVERT dans la sortie (visionneuse…) : refus clair, rien d'effacé.
        with open(temoin, "rb"):
            e = self.assertErreur(c.appeler("conversion_images", dict(args, remplacer=p["sortie"])),
                                  "SORTIE_VERROUILLEE")
        self.assertEqual(e["details"]["sortie"], sortie)
        self.assertTrue(os.path.exists(temoin))
        self.assertTrue(os.path.isfile(os.path.join(sortie, "1 photo ☀.jpg")))
        # Le chemin EXACT renvoyé par preparer : remplacement.
        d = self.assertResultat(c.appeler("conversion_images", dict(args, remplacer=p["sortie"]), 120))
        self.assertEqual(d["traites"], 3)
        self.assertFalse(os.path.exists(temoin))        # dossier bien REMPLACÉ
        # … et aucune copie « .ancien-… » ne traîne à côté.
        self.assertEqual([n for n in os.listdir(base) if ".ancien-" in n], [])
        # Source DANS la sortie : refusé (sinon rmtree la détruirait).
        self.assertErreur(c.appeler("conversion_images", {
            "source": {"type": "dossier", "chemin": sortie}, "remplacer": sortie}),
            "SOURCE_DANS_SORTIE")

    def test_annuler_juste_apres_le_lancement_ne_supprime_rien(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie annulation immédiate")
        sortie = os.path.join(base, "images (jpg)")
        os.makedirs(sortie)
        anciens = [os.path.join(sortie, f"ancienne {i}.jpg") for i in (1, 2, 3)]
        for f in anciens:
            open(f, "w").close()
        # La tâche ET l'annulation dans la même écriture : l'annulation arrive pendant que
        # la tâche prépare son travail (import de PIL, comptage…), avant tout remplacement.
        req = {"id": "img-1", "cmd": "conversion_images",
               "args": {"source": {"type": "dossier", "chemin": self.images}, "format": "jpg",
                        "remplacer": sortie}}
        ann = {"id": "ann-1", "cmd": "annuler", "args": {"cible": "img-1"}}
        c.envoyer_brut((json.dumps(req) + "\n" + json.dumps(ann) + "\n").encode("utf-8"))
        self.assertEqual(self.assertResultat(c.fin("ann-1", 10))["etat"], "annulation_demandee")
        d = self.assertResultat(c.fin("img-1", 60))
        self.assertTrue(d["arrete"])
        self.assertEqual(d["traites"], 0)
        self.assertEqual(d["bilan"]["titre"], "Interrompu")
        for f in anciens:
            self.assertTrue(os.path.exists(f), "une ancienne image a été supprimée")
        # Le journal « Annulation demandée » porte l'id de la tâche, et arrive AVANT sa fin.
        evs = c.de("img-1")
        i_log = next(i for i, e in enumerate(evs)
                     if e["type"] == "log" and "Annulation demandée" in e["texte"])
        self.assertLess(i_log, len(evs) - 1)
        self.assertIn(evs[-1]["type"], FINAUX)

    def test_metadonnees_fichiers(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie métadonnées")
        fichiers = [os.path.join(self.images, f) for f in sorted(os.listdir(self.images))]
        # « renommer » omis : true par défaut (case « recommandé » de l'ancienne app).
        d = self.assertResultat(c.appeler("metadonnees", {
            "source": {"type": "fichiers", "chemins": fichiers}}, 120))
        sortie = os.path.join(base, "media (métadonnées changées)")
        self.assertEqual(d["sortie"], sortie)
        self.assertEqual(d["traites"], 3)
        self.assertFalse(d["arrete"])
        self.assertEqual(sorted(os.listdir(os.path.join(sortie, "images"))),
                         ["1.jpg", "2.jpg", "3.jpg"])
        self.assertEqual(d["bilan"]["titre"], "Métadonnées changées")

    # ----------------------------------------------------------------- compteur d'activité
    def test_activite_comptee_apres_une_conversion(self):
        from datetime import date
        appdata, home = self.profil_isole("Activité")
        c = self.moteur(appdata=appdata, home=home)
        # Profil neuf : tout à zéro, rien n'est partagé (pas de licence -> aucun envoi).
        d = self.assertResultat(c.appeler("activite_lire"))
        zero = {"images": 0, "videos": 0, "metadonnees": 0, "total": 0}
        for bloc in ("aujourd_hui", "semaine", "mois", "total"):
            self.assertEqual(d[bloc], zero)
        self.assertIsNone(d["depuis"])
        self.assertFalse(d["partage"])
        # Une vraie conversion de 3 images -> +3 « images » aujourd'hui (date LOCALE).
        r = self.assertResultat(c.appeler("conversion_images", {
            "source": {"type": "dossier", "chemin": self.images}, "format": "png"}, 120))
        self.assertEqual(r["traites"], 3)
        d = self.assertResultat(c.appeler("activite_lire"))
        trois = {"images": 3, "videos": 0, "metadonnees": 0, "total": 3}
        for bloc in ("aujourd_hui", "semaine", "mois", "total"):
            self.assertEqual(d[bloc], trois, bloc)
        # Les MÊMES images reconverties (autre format) : déjà comptées, le compteur ne bouge pas.
        r = self.assertResultat(c.appeler("conversion_images", {
            "source": {"type": "dossier", "chemin": self.images}, "format": "jpg"}, 120))
        self.assertEqual(r["traites"], 3)
        d = self.assertResultat(c.appeler("activite_lire"))
        self.assertEqual(d["aujourd_hui"], trois)
        aujourd_hui = date.today().isoformat()
        self.assertEqual(d["depuis"], aujourd_hui)
        self.assertFalse(d["partage"])
        # Le fichier est dans le APPDATA TEMPORAIRE ; rien n'a été « envoyé ».
        with open(os.path.join(appdata, "HelpVA", "activite.json"), encoding="utf-8") as f:
            fichier = json.load(f)
        self.assertEqual(fichier["jours"][aujourd_hui]["images"], 3)
        self.assertEqual(fichier["envoye"], {})
        self.assertFalse(os.path.exists(os.path.join(appdata, "HelpVA", "licence.key")))

    # ----------------------------------------------------------------- calendrier / ranger
    def test_calendrier_et_ranger(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie rangement")
        cal = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "story"},
                                         {"heure": "19h00", "type": "reel"}]}}
        s = self.assertResultat(c.appeler("calendrier_sauver", {"calendrier": cal}))
        self.assertEqual(s["semaines"], 1)
        self.assertEqual(s["compte"]["story"], 1)
        lu = self.assertResultat(c.appeler("calendrier_lire"))
        self.assertEqual(lu["calendrier"], cal)
        self.assertTrue(lu["personnalise"])
        # Une heure qui sortirait du dossier de sortie (« ..\\ ») est refusée.
        self.assertErreur(c.appeler("calendrier_sauver", {"calendrier": {
            "semaine-01": {"jour-1": [{"heure": "..\\pirate", "type": "reel"}]}}}),
            "ARGUMENTS_INVALIDES")
        # Noms réservés par Windows (impossible d'en faire un dossier) et espaces de fin.
        for nom in ("CON", "nul", "Com1.txt", "LPT9", "jour 1 "):
            self.assertErreur(c.appeler("calendrier_sauver", {"calendrier": {
                "semaine-01": {nom: [{"heure": "12h00", "type": "reel"}]}}}),
                "ARGUMENTS_INVALIDES")
        self.assertResultat(c.appeler("calendrier_sauver", {"calendrier": {   # « CONSEIL » est permis
            "semaine-01": {"CONSEIL": [{"heure": "12h00", "type": "reel"}]}}}))
        self.assertResultat(c.appeler("calendrier_sauver", {"calendrier": cal}))
        self.assertGreater(self.assertResultat(c.appeler("calendrier_defaut"))["semaines"], 1)

        sources = {"story": self.images, "reel": self.videos}
        a = self.assertResultat(c.appeler("ranger_analyser", {"sources": sources,
                                                              "types": ["story", "reel"]}))
        self.assertTrue(a["pret"])
        self.assertEqual(a["actifs"], ["reel", "story"])
        self.assertEqual(a["types"]["story"]["trouves"], 3)
        self.assertEqual(a["types"]["reel"]["trouves"], 1)     # seul le .avi est à la racine
        self.assertIn("À ranger :", a["message_confirmation"])
        d = self.assertResultat(c.appeler("ranger_lancer", {
            "sources": sources, "types": ["story", "reel"], "aleatoire": False}, 120))
        sortie = os.path.join(base, "ranger")
        self.assertEqual(d["sortie"], sortie)
        self.assertEqual(d["creneaux"], 2)
        self.assertFalse(d["arrete"])
        creneau = os.path.join(sortie, "semaine-01", "jour-1", "1_12h00_story")
        self.assertTrue(os.path.isfile(os.path.join(creneau, "1 photo ☀.png")))
        self.assertTrue(os.path.isfile(os.path.join(sortie, "semaine-01", "jour-1",
                                                    "2_19h00_reel", "clip é 01.avi")))
        self.assertTrue(d["bilan"]["message"].startswith("Médias rangés !"))
        self.assertIn("📦 2 média(s) en trop", d["bilan"]["message"])
        # Relancer sans « remplacer » -> SORTIE_EXISTE.
        self.assertErreur(c.appeler("ranger_lancer", {"sources": sources,
                                                      "types": ["story", "reel"]}),
                          "SORTIE_EXISTE")
        # preparer annonce CE dossier ; relancer avec ce chemin le remplace.
        p = self.assertResultat(c.appeler("preparer", {"commande": "ranger_lancer", "args": {
            "sources": sources, "types": ["story", "reel"]}}))
        self.assertEqual(p["sortie"], sortie)
        self.assertTrue(p["remplacement"])
        d = self.assertResultat(c.appeler("ranger_lancer", {
            "sources": sources, "types": ["story", "reel"], "remplacer": p["sortie"]}, 120))
        self.assertEqual(d["creneaux"], 2)

        # Calendrier écrit par l'ANCIENNE app avec un nom réservé : refusé AVANT de toucher
        # à la sortie (sinon : ancienne sortie supprimée, puis plantage).
        with open(os.path.join(self.appdata, "HelpVA", "calendrier_utilisateur.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"semaine-01": {"CON": [{"heure": "12h00", "type": "story"}]}}, f)
        a = self.assertResultat(c.appeler("ranger_analyser", {"sources": sources,
                                                              "types": ["story"]}))
        self.assertFalse(a["pret"])
        self.assertIn("CON", a["calendrier_erreur"])
        self.assertErreur(c.appeler("ranger_lancer", {"sources": sources, "types": ["story"],
                                                      "remplacer": sortie}),
                          "CALENDRIER_INVALIDE")
        # L'ancienne sortie est intacte (ordre aléatoire au 2e rangement : on vérifie juste le contenu).
        self.assertTrue(os.listdir(creneau), "l'ancienne sortie a été supprimée")
        self.assertResultat(c.appeler("calendrier_sauver", {"calendrier": cal}))

        # Dossier de sortie perso INACCESSIBLE (clé USB retirée…) : preparer annonce le MÊME
        # dossier de repli que celui que ranger_lancer remplacera (Bureau\HelpVA\ranger).
        fichier = os.path.join(self.tmp, "un fichier.txt")
        open(fichier, "w").close()
        chemin_params = os.path.join(self.appdata, "HelpVA", "parametres.json")
        with open(chemin_params, encoding="utf-8") as f:
            params = json.load(f)
        params["dossier_sortie"] = os.path.join(fichier, "sous-dossier impossible")
        with open(chemin_params, "w", encoding="utf-8") as f:
            json.dump(params, f)
        repli = os.path.join(self.home, "Desktop", "HelpVA", "ranger")
        p = self.assertResultat(c.appeler("preparer", {"commande": "ranger_lancer", "args": {
            "sources": sources, "types": ["story", "reel"]}}))
        self.assertEqual(p["sortie"], repli)
        os.makedirs(repli, exist_ok=True)
        temoin = os.path.join(repli, "témoin.txt")
        open(temoin, "w").close()
        p = self.assertResultat(c.appeler("preparer", {"commande": "ranger_lancer", "args": {
            "sources": sources, "types": ["story", "reel"]}}))
        self.assertTrue(p["remplacement"])
        d = self.assertResultat(c.appeler("ranger_lancer", {
            "sources": sources, "types": ["story", "reel"], "remplacer": p["sortie"]}, 120))
        self.assertEqual(d["sortie"], repli)
        self.assertFalse(os.path.exists(temoin))

    # ----------------------------------------------------------------- comptes du Ranger
    def test_comptes_migration_et_persistance(self):
        appdata, home = self.profil_isole("Profil comptes")
        donnees = os.path.join(appdata, "HelpVA")
        os.makedirs(donnees)
        cal = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "story"}]}}
        with open(os.path.join(donnees, "calendrier_utilisateur.json"), "w", encoding="utf-8") as f:
            json.dump(cal, f)
        fichier = os.path.join(donnees, "comptes_ranger.json")
        c = self.moteur(appdata=appdata, home=home)

        # 1re ouverture : « Compte 1 » reprend le calendrier déjà enregistré, sans rien écrire.
        v = self.assertResultat(c.appeler("comptes_lire"))
        self.assertEqual(v["max"], 50)
        self.assertEqual(len(v["comptes"]), 1)
        c1 = v["comptes"][0]
        self.assertEqual((c1["id"], c1["nom"], c1["sources"]), ("c1", "Compte 1", {}))
        self.assertEqual(c1["calendrier"], cal)
        self.assertTrue(c1["vue"]["personnalise"])
        self.assertEqual((c1["vue"]["semaines"], c1["vue"]["creneaux"]), (1, 1))
        self.assertEqual(c1["vue"]["compte"]["story"], 1)
        self.assertFalse(os.path.exists(fichier))

        # Enregistrer : calendrier identique à l'origine -> null, id absent -> créé,
        # espaces de bord retirés, dossier vide = pas encore choisi.
        origine = self.assertResultat(c.appeler("calendrier_defaut"))["calendrier"]
        cal2 = {"semaine-01": {"jour-1": [{"heure": "10h00", "type": "story"}],
                               "jour-2": [{"heure": "11h00", "type": "reel"}]}}
        comptes = [{"id": "c1", "nom": "Compte 1", "sources": {"story": self.images, "reel": ""},
                    "calendrier": origine},
                   {"nom": "  @marie ☀  ", "sources": {}, "calendrier": cal2}]
        s = self.assertResultat(c.appeler("comptes_sauver", {"comptes": comptes}))
        self.assertEqual(s["message"], "Enregistré.")
        a, b = s["comptes"]
        self.assertIsNone(a["calendrier"])
        self.assertFalse(a["vue"]["personnalise"])
        self.assertEqual(a["vue"]["calendrier"], origine)
        self.assertEqual(a["vue"]["semaines"], len(origine))
        self.assertEqual(a["sources"], {"story": self.images})
        self.assertEqual((b["id"], b["nom"]), ("c2", "@marie ☀"))
        self.assertEqual(b["calendrier"], cal2)
        self.assertTrue(b["vue"]["personnalise"])
        self.assertEqual(b["vue"]["creneaux"], 2)
        # Le fichier : format documenté, écrit d'un coup (aucun .tmp ne traîne).
        with open(fichier, encoding="utf-8") as f:
            ecrit = json.load(f)
        self.assertEqual(ecrit["version"], 1)
        self.assertEqual([x["id"] for x in ecrit["comptes"]], ["c1", "c2"])
        self.assertIsNone(ecrit["comptes"][0]["calendrier"])
        self.assertEqual([n for n in os.listdir(donnees) if n.endswith(".tmp")], [])

        # Persistance : un AUTRE moteur relit la même chose ; le calendrier global n'a pas bougé.
        c2 = self.moteur(appdata=appdata, home=home)
        v = self.assertResultat(c2.appeler("comptes_lire"))
        self.assertEqual([(x["id"], x["nom"]) for x in v["comptes"]],
                         [("c1", "Compte 1"), ("c2", "@marie ☀")])
        self.assertEqual(v["comptes"][1]["calendrier"], cal2)
        self.assertEqual(self.assertResultat(c2.appeler("calendrier_lire"))["calendrier"], cal)
        # Fichier modifié à la main (id en double) : chaque compte garde un id unique.
        ecrit["comptes"][1]["id"] = "c1"
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(ecrit, f)
        v = self.assertResultat(c2.appeler("comptes_lire"))
        self.assertEqual(len({x["id"] for x in v["comptes"]}), 2)
        # Ids que le moteur refuserait (espace au bord, plus de 64 caractères) : remplacés à la
        # lecture, sinon chaque comptes_sauver de la liste lue échouerait.
        ecrit["comptes"][0]["id"], ecrit["comptes"][1]["id"] = "c1 ", "x" * 70
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(ecrit, f)
        v = self.assertResultat(c2.appeler("comptes_lire"))
        self.assertEqual([x["id"] for x in v["comptes"]], ["c1", "c2"])
        self.assertResultat(c2.appeler("comptes_sauver", {"comptes": [
            {k: x[k] for k in ("id", "nom", "sources", "calendrier")} for x in v["comptes"]]}))
        # Fichier illisible : MIS DE CÔTÉ (pas écrasé au prochain enregistrement), puis retour à
        # la migration (« Compte 1 »), sans planter.
        with open(fichier, "w", encoding="utf-8") as f:
            f.write("{pas du json")
        v = self.assertResultat(c2.appeler("comptes_lire"))
        self.assertEqual([x["nom"] for x in v["comptes"]], ["Compte 1"])
        self.assertEqual(v["comptes"][0]["calendrier"], cal)
        self.assertFalse(os.path.exists(fichier))
        copies = [n for n in os.listdir(donnees) if n.startswith("comptes_ranger.illisible-")]
        self.assertEqual(len(copies), 1, os.listdir(donnees))
        with open(os.path.join(donnees, copies[0]), encoding="utf-8") as f:
            self.assertEqual(f.read(), "{pas du json")

        # Aucun calendrier enregistré nulle part -> calendrier null (= celui d'origine).
        # (En dev, emplacement copierait calendrier_utilisateur.json de la racine du dépôt :
        #  on pointe l'ancien emplacement vers un dossier vide.)
        appdata2, _home2 = self.profil_isole("Profil comptes vierge")
        ancien = os.path.join(self.tmp, "Profil comptes vierge", "ancien emplacement")
        os.makedirs(ancien)
        code = ("import sys, json; sys.path.insert(0, %r)\n"
                "from agent import emplacement, comptes\n"
                "emplacement.dossier_exe = lambda: %r\n"
                "print(json.dumps(comptes.charger_comptes()))\n"
                ) % (os.path.dirname(DOSSIER_ENGINE), ancien)
        r = subprocess.run([sys.executable, "-c", code], env=self.env(appdata=appdata2),
                           cwd=self.tmp, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1]),
                         [{"id": "c1", "nom": "Compte 1", "sources": {}, "calendrier": None}])
        self.assertFalse(os.path.exists(os.path.join(appdata2, "HelpVA", "comptes_ranger.json")))

    def test_comptes_sauver_refuse_et_nomme_le_compte(self):
        appdata, home = self.profil_isole("Profil validation comptes")
        c = self.moteur(appdata=appdata, home=home)
        bon = {"id": "c1", "nom": "Compte 1", "sources": {}, "calendrier": None}
        self.assertResultat(c.appeler("comptes_sauver", {"comptes": [bon]}))

        def refus(comptes, *morceaux, compte="?"):
            e = self.assertErreur(c.appeler("comptes_sauver", {"comptes": comptes}),
                                  "ARGUMENTS_INVALIDES")
            for m in morceaux:
                self.assertIn(m, e["message"])
            if compte != "?":
                self.assertEqual(e["details"]["compte"], compte, e)
            return e

        refus([], "au moins 1 compte")
        refus("Compte 1", "au moins 1 compte")
        refus([dict(bon, id=f"c{i}", nom=f"Compte {i}") for i in range(1, 52)],
              "50 comptes au maximum")
        # Noms en double SANS tenir compte de la casse (même dossier pour Windows).
        refus([bon, {"id": "c2", "nom": "compte 1"}], "Compte n°2", "déjà utilisé", compte="c2")
        # Noms impossibles comme nom de dossier Windows, vides, trop longs.
        for nom in ("CON", "nul.txt", "a/b", "deux:points", "fin.", "   ", "x" * 41, 12,
                    # réservés aussi (Windows 10 refuse les exposants ; COM0/LPT0 : doc Microsoft)
                    "COM¹", "lpt³", "CONIN$", "conout$.txt", "COM0", "LPT0"):
            refus([bon, {"id": "c2", "nom": nom}], "Compte n°2", compte="c2")
        # « COMPTE~1 » = le nom court du dossier « Compte 1 » : les deux comptes partageraient
        # le même dossier de sortie.
        refus([bon, {"id": "c2", "nom": "COMPTE~1"}], "Compte n°2", "nom court", compte="c2")
        refus([bon, dict(bon, nom="Autre")], "Compte n°2", "identifiant", compte="c1")
        # Compte SANS id refusé : details.compte = null (pas un id inventé que l'interface ignore).
        refus([bon, {"nom": "a/b"}], "Compte n°2", compte=None)
        # Dossiers : le message NOMME le compte fautif.
        refus([bon, {"id": "c2", "nom": "@marie", "sources": {"reel": "relatif"}}],
              "@marie : ", "réels", "ABSOLU", compte="c2")
        refus([bon, {"id": "c2", "nom": "@marie", "sources": {"tiktok": self.images}}],
              "@marie : ", "tiktok", compte="c2")
        # Calendrier invalide d'un compte (heure qui sortirait du dossier, nom réservé, vide).
        for mauvais, morceau in (
                ({"semaine-01": {"jour-1": [{"heure": "..\\x", "type": "reel"}]}}, "Créneau invalide"),
                ({"semaine-01": {"CON": [{"heure": "12h00", "type": "reel"}]}}, "CON"),
                ({}, "au moins 1 semaine")):
            refus([bon, {"id": "c2", "nom": "@marie", "calendrier": mauvais}],
                  "@marie : ", morceau, compte="c2")
        # Aucun de ces refus n'a rien écrit.
        v = self.assertResultat(c.appeler("comptes_lire"))
        self.assertEqual([x["nom"] for x in v["comptes"]], ["Compte 1"])
        # 50 comptes : accepté (et « CONSEIL » est un nom permis).
        cinquante = [dict(bon, id=f"c{i}", nom=f"Compte {i}") for i in range(1, 51)]
        cinquante[1]["nom"] = "CONSEIL"
        v = self.assertResultat(c.appeler("comptes_sauver", {"comptes": cinquante}))
        self.assertEqual(len(v["comptes"]), 50)
        self.assertEqual(v["comptes"][1]["nom"], "CONSEIL")

    def test_comptes_calendrier_herite_invalide(self):
        """Calendrier écrit par l'ANCIENNE app, que le moteur refuserait aujourd'hui : il ne bloque
        ni le choix d'un dossier, ni « + », ni un renommage. Seul le rangement est refusé."""
        appdata, home = self.profil_isole("Profil calendrier hérité")
        donnees = os.path.join(appdata, "HelpVA")
        os.makedirs(donnees)
        herite = {"semaine-01": {"jour-1": [{"heure": "12h15 ", "type": "story"}],
                                 "CON": [{"heure": "13h00", "type": "story"}]}}
        with open(os.path.join(donnees, "calendrier_utilisateur.json"), "w", encoding="utf-8") as f:
            json.dump(herite, f)
        c = self.moteur(appdata=appdata, home=home)
        self.assertEqual(self.assertResultat(c.appeler("comptes_lire"))["comptes"][0]["calendrier"],
                         herite)
        # Choisir un dossier, « + » (copie du calendrier du compte 1), renommer : acceptés.
        liste = [{"id": "c1", "nom": "Compte 1", "sources": {"story": self.images},
                  "calendrier": herite}]
        v = self.assertResultat(c.appeler("comptes_sauver", {"comptes": liste}))
        self.assertEqual(v["comptes"][0]["calendrier"], herite)
        liste.append({"id": "c2", "nom": "Compte 2", "sources": {}, "calendrier": herite})
        self.assertResultat(c.appeler("comptes_sauver", {"comptes": liste}))
        liste[1]["nom"] = "@marie"
        v = self.assertResultat(c.appeler("comptes_sauver", {"comptes": liste}))
        self.assertEqual([x["nom"] for x in v["comptes"]], ["Compte 1", "@marie"])
        # Le rangement, lui, reste refusé tant que le calendrier n'est pas corrigé.
        a = self.assertResultat(c.appeler("ranger_analyser", {"comptes": liste, "types": ["story"]}))
        self.assertFalse(a["pret"])
        self.assertIn("12h15 ", a["comptes"][0]["calendrier_erreur"])
        # Un calendrier MODIFIÉ est vérifié en entier : encore invalide -> refusé, rien d'écrit.
        modifie = json.loads(json.dumps(herite))
        modifie["semaine-01"]["jour-1"].append({"heure": "18h00", "type": "reel"})
        e = self.assertErreur(c.appeler("comptes_sauver", {"comptes": [
            liste[0], dict(liste[1], calendrier=modifie)]}), "ARGUMENTS_INVALIDES")
        self.assertTrue(e["message"].startswith("@marie : "), e["message"])
        self.assertEqual(e["details"]["compte"], "c2")
        # Corrigé dans l'éditeur : accepté.
        corrige = {"semaine-01": {"jour-1": [{"heure": "12h15", "type": "story"}]}}
        v = self.assertResultat(c.appeler("comptes_sauver", {"comptes": [
            liste[0], dict(liste[1], calendrier=corrige)]}))
        self.assertEqual(v["comptes"][1]["calendrier"], corrige)

    def test_ranger_plusieurs_comptes(self):
        appdata, home = self.profil_isole("Profil multi-comptes")
        c = self.moteur(appdata=appdata, home=home)
        base = self.nouvelle_sortie(c, "Sortie multi-comptes é")
        sortie = os.path.join(base, "ranger")
        images_marie = os.path.join(self.tmp, "Profil multi-comptes", "Images de Marie é")
        os.makedirs(images_marie)
        for i in (1, 2, 3):
            shutil.copy2(os.path.join(self.images, f"{i} photo ☀.png"),
                         os.path.join(images_marie, f"{i} marie.png"))
        cal1 = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "story"},
                                          {"heure": "19h00", "type": "reel"}]}}
        cal2 = {"semaine-01": {"jour-1": [{"heure": "10h00", "type": "story"}]},
                "semaine-02": {"jour-2": [{"heure": "11h00", "type": "story"}]}}
        cal3 = {"semaine-01": {"jour-1": [{"heure": "09h00", "type": "carousel"}]}}
        comptes = [
            {"id": "c1", "nom": "Compte 1", "sources": {"story": self.images, "reel": self.videos},
             "calendrier": cal1},
            {"id": "c7", "nom": "@marie", "sources": {"story": self.images}, "calendrier": cal2},
            {"id": "c3", "nom": "Sans type", "sources": {}, "calendrier": cal3},
        ]
        types = ["story", "reel"]

        # Même dossier d'images pour deux comptes : AVERTISSEMENT, pas un refus.
        a = self.assertResultat(c.appeler("ranger_analyser", {"comptes": comptes, "types": types}))
        self.assertTrue(a["pret"], a)
        self.assertEqual(len(a["partages"]), 1)
        self.assertEqual(os.path.normcase(a["partages"][0]["dossier"]), os.path.normcase(self.images))
        self.assertEqual([(u["id"], u["nom"], u["type"]) for u in a["partages"][0]["comptes"]],
                         [("c1", "Compte 1", "story"), ("c7", "@marie", "story")])
        self.assertIn("Même dossier pour plusieurs comptes", a["message_confirmation"])

        # Avec ses propres images : plus de partage.
        comptes[1]["sources"] = {"story": images_marie}
        a = self.assertResultat(c.appeler("ranger_analyser", {"comptes": comptes, "types": types}))
        self.assertTrue(a["pret"])
        self.assertEqual(a["partages"], [])
        self.assertEqual(a["sortie"], sortie)
        self.assertEqual([x["sortie"] for x in a["comptes"]],
                         [os.path.join(sortie, n) for n in ("Compte 1", "@marie", "Sans type")])
        # Types actifs d'un compte = types cochés ∩ types de SON calendrier.
        self.assertEqual([x["actifs"] for x in a["comptes"]], [["reel", "story"], ["story"], []])
        self.assertEqual([x["creneaux"] for x in a["comptes"]], [2, 2, 0])
        self.assertEqual(a["actifs"], ["reel", "story"])
        # Champs de tête = somme des comptes.
        self.assertEqual(a["types"]["story"]["creneaux"], 3)
        self.assertEqual(a["types"]["story"]["requis"], 3)
        self.assertEqual(a["types"]["story"]["trouves"], 6)
        self.assertEqual(a["types"]["carousel"]["creneaux"], 1)
        self.assertFalse(a["types"]["carousel"]["actif"])
        self.assertIsNone(a["types"]["story"]["dossier"])
        self.assertTrue(a["types"]["story"]["dossier_valide"])
        self.assertEqual(a["comptes"][1]["types"]["story"]["dossier"], images_marie)
        msg = a["message_confirmation"]
        self.assertIn(f"@marie → {os.path.join('ranger', '@marie')}\n• Stories : 3 image(s) pour 2 "
                      "requise(s)", msg)
        self.assertIn("Sans type : aucun type coché dans son calendrier (ignoré).", msg)

        rid = c.envoyer("ranger_lancer", {"comptes": comptes, "types": types, "aleatoire": False})
        d = self.assertResultat(c.fin(rid, 120))
        self.assertFalse(d["arrete"])
        self.assertEqual(d["sortie"], sortie)
        self.assertEqual(d["creneaux"], 4)
        self.assertEqual(d["types"], ["reel", "story"])
        self.assertEqual(d["besoins"], {"reel": 1, "story": 3})
        self.assertEqual(d["places"], {"reel": 1, "story": 3})
        self.assertEqual(d["surplus"], {"reel": 0, "story": 3})
        self.assertEqual([(x["id"], x["nom"], x["creneaux"], x["aucun_type"]) for x in d["comptes"]],
                         [("c1", "Compte 1", 2, False), ("c7", "@marie", 2, False),
                          ("c3", "Sans type", 0, True)])
        self.assertEqual(d["comptes"][1]["sortie"], os.path.join(sortie, "@marie"))
        # Arborescence : ranger/<nom du compte>/semaine-XX/jour-Y/<créneau>/ + surplus par compte.
        j1 = os.path.join(sortie, "Compte 1", "semaine-01", "jour-1")
        self.assertTrue(os.path.isfile(os.path.join(j1, "1_12h00_story", "1 photo ☀.png")))
        self.assertTrue(os.path.isfile(os.path.join(j1, "2_19h00_reel", "clip é 01.avi")))
        self.assertTrue(os.path.isfile(os.path.join(sortie, "Compte 1", "surplus", "Stories",
                                                    "2 photo ☀.png")))
        m = os.path.join(sortie, "@marie")
        self.assertTrue(os.path.isfile(os.path.join(m, "semaine-01", "jour-1", "1_10h00_story",
                                                    "1 marie.png")))
        self.assertTrue(os.path.isfile(os.path.join(m, "semaine-02", "jour-2", "1_11h00_story",
                                                    "2 marie.png")))
        self.assertTrue(os.path.isfile(os.path.join(m, "surplus", "Stories", "3 marie.png")))
        # Rien d'autre à la racine ; le compte ignoré n'a pas de dossier.
        self.assertEqual(sorted(os.listdir(sortie)), ["@marie", "Compte 1"])

        # Progression : 1re ligne = le compte, fraction GLOBALE qui ne recule jamais.
        prog = c.de(rid, "progress")
        textes = [p["texte"] for p in prog]
        self.assertTrue(any(t.startswith("Compte 1/2 — Compte 1\nSemaine 1/1") for t in textes), textes)
        self.assertTrue(any(t.startswith("Compte 2/2 — @marie\nSemaine 2/2") for t in textes), textes)
        fractions = [p["fraction"] for p in prog if p["fraction"] is not None]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(fractions[-1], 1.0)
        self.assertTrue(any(p["details"]["compte"] == {"index": 2, "total": 2, "id": "c7",
                                                       "nom": "@marie"} for p in prog))
        # Bilan : un bloc par compte.
        msg = d["bilan"]["message"]
        self.assertTrue(msg.startswith("Médias rangés !\n\nCompte 1 :\n• Réels : 1/1 vidéo(s)\n"
                                       "• Stories : 1/1 image(s)\n\n@marie :\n• Stories : 2/2 "
                                       "image(s)\n\nSans type : ignoré"), msg)
        self.assertIn("📦 3 média(s) en trop", msg)
        self.assertFalse(d["bilan"]["erreur"])

        # preparer annonce le dossier « ranger » ENTIER ; relancer avec ce chemin le remplace.
        p = self.assertResultat(c.appeler("preparer", {"commande": "ranger_lancer",
                                                       "args": {"comptes": comptes, "types": types}}))
        self.assertEqual(p["sortie"], sortie)
        self.assertTrue(p["remplacement"])
        self.assertEqual(len(p["analyse"]["comptes"]), 3)
        self.assertErreur(c.appeler("ranger_lancer", {"comptes": comptes, "types": types}),
                          "SORTIE_EXISTE")
        temoin = os.path.join(sortie, "témoin.txt")
        open(temoin, "w").close()
        d = self.assertResultat(c.appeler("ranger_lancer", {
            "comptes": comptes, "types": types, "remplacer": p["sortie"]}, 120))
        self.assertEqual(d["creneaux"], 4)
        self.assertFalse(os.path.exists(temoin))

    def test_ranger_un_seul_compte_arborescence_inchangee(self):
        appdata, home = self.profil_isole("Profil un compte")
        c = self.moteur(appdata=appdata, home=home)
        base = self.nouvelle_sortie(c, "Sortie un compte")
        sortie = os.path.join(base, "ranger")
        cal = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "story"}]}}
        comptes = [{"id": "c1", "nom": "@solo", "sources": {"story": self.images}, "calendrier": cal}]
        a = self.assertResultat(c.appeler("ranger_analyser", {"comptes": comptes,
                                                              "types": ["story"]}))
        self.assertTrue(a["pret"])
        self.assertEqual(a["comptes"][0]["sortie"], sortie)
        self.assertEqual(a["types"]["story"]["dossier"], self.images)
        self.assertTrue(a["types"]["story"]["dossier_valide"])
        self.assertTrue(a["message_confirmation"].startswith(
            "À ranger :\n• Stories : 3 image(s) pour 1 requise(s)\n\nDestination :"), a)
        rid = c.envoyer("ranger_lancer", {"comptes": comptes, "types": ["story"],
                                          "aleatoire": False})
        d = self.assertResultat(c.fin(rid, 120))
        # Arborescence d'AVANT : pas de sous-dossier au nom du compte.
        self.assertTrue(os.path.isfile(os.path.join(sortie, "semaine-01", "jour-1", "1_12h00_story",
                                                    "1 photo ☀.png")))
        self.assertTrue(os.path.isdir(os.path.join(sortie, "surplus", "Stories")))
        self.assertFalse(os.path.exists(os.path.join(sortie, "@solo")))
        self.assertEqual((d["sortie"], d["creneaux"], d["surplus"]), (sortie, 1, {"story": 2}))
        self.assertEqual((d["comptes"][0]["id"], d["comptes"][0]["sortie"]), ("c1", sortie))
        self.assertEqual(d["bilan"]["message"],
                         "Médias rangés !\n\n• Stories : 1/1 image(s)\n\nDossier :\n" + sortie
                         + "\n\n📦 2 média(s) en trop → dossier « surplus ».")
        self.assertFalse(any(p["texte"].startswith("Compte") for p in c.de(rid, "progress")))
        # Calendrier null = celui d'origine.
        a = self.assertResultat(c.appeler("ranger_analyser", {
            "comptes": [dict(comptes[0], calendrier=None)], "types": ["story"]}))
        origine = self.assertResultat(c.appeler("calendrier_defaut"))
        self.assertEqual(a["comptes"][0]["creneaux"], origine["compte"]["story"])
        # Ancien mode (sans « comptes ») : la réponse a aussi ses champs « comptes » / « partages ».
        a = self.assertResultat(c.appeler("ranger_analyser", {"sources": {"story": self.images},
                                                              "types": ["story"]}))
        self.assertEqual([(x["id"], x["sortie"]) for x in a["comptes"]], [("c1", sortie)])
        self.assertEqual(a["partages"], [])

    def test_carrousels_prepares(self):
        appdata, home = self.profil_isole("Profil carrousels")
        c = self.moteur(appdata=appdata, home=home)
        base = self.nouvelle_sortie(c, "Sortie carrousels")
        # 8 images nommées 1…8 (dans le désordre du disque) : 2 carrousels complets + 2 en trop.
        src = os.path.join(appdata, "photos carrousels")
        os.makedirs(src)
        modele = sorted(f for f in os.listdir(self.images) if f.endswith(".png"))[0]
        for i in (3, 1, 10, 2, 5, 4, 6, 7):
            shutil.copy(os.path.join(self.images, modele), os.path.join(src, f"{i}.png"))
        d = self.assertResultat(c.appeler("carrousels_preparer", {"source": src}))
        self.assertEqual(d["sortie"], os.path.join(base, "carrousels"))
        self.assertEqual((d["carrousels"], d["images"], d["en_trop"]), (2, 8, 2))
        self.assertEqual(sorted(os.listdir(os.path.join(d["sortie"], "carrousel-1"))),
                         ["1.png", "2.png", "3.png"])
        self.assertEqual(sorted(os.listdir(os.path.join(d["sortie"], "carrousel-2"))),
                         ["4.png", "5.png", "6.png"])
        # Un 2e passage ne remplace JAMAIS les carrousels retouchés : « carrousels (2) ».
        d2 = self.assertResultat(c.appeler("carrousels_preparer", {"source": src}))
        self.assertEqual(d2["sortie"], os.path.join(base, "carrousels (2)"))
        e = c.appeler("carrousels_preparer", {"source": os.path.join(d["sortie"], "carrousel-1", "x")})
        self.assertEqual(e["type"], "error")
        # Retouche à la main : un carrousel de 2 images, et un 10e (tri numérique) en plus.
        os.remove(os.path.join(d["sortie"], "carrousel-2", "6.png"))
        shutil.copytree(os.path.join(d["sortie"], "carrousel-1"), os.path.join(d["sortie"], "carrousel-10"))
        cal = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "carousel"},
                                         {"heure": "19h00", "type": "carousel"}]}}
        comptes = [{"id": "c1", "nom": "@c", "sources": {"carousel": d["sortie"]}, "calendrier": cal}]
        a = self.assertResultat(c.appeler("ranger_analyser", {"comptes": comptes, "types": ["carousel"]}))
        x = a["types"]["carousel"]
        self.assertEqual((x["carrousels"], x["manque"], x["trouves"]), (3, 0, 8))
        self.assertIn("• Carrousels : 3 carrousel(s) préparé(s) pour 2 requis", a["message_confirmation"])
        rid = c.envoyer("ranger_lancer", {"comptes": comptes, "types": ["carousel"], "aleatoire": False})
        r = self.assertResultat(c.fin(rid, 120))
        jour = os.path.join(base, "ranger", "semaine-01", "jour-1")
        self.assertEqual(sorted(os.listdir(os.path.join(jour, "1_12h00_carousel"))),
                         ["1.png", "2.png", "3.png"])
        self.assertEqual(sorted(os.listdir(os.path.join(jour, "2_19h00_carousel"))),
                         ["4.png", "5.png"])
        self.assertEqual(os.listdir(os.path.join(base, "ranger", "surplus", "Carrousels")), ["carrousel-10"])
        self.assertEqual((r["places"], r["manques"], r["surplus"]), ({"carousel": 5}, {"carousel": 0},
                                                                     {"carousel": 1}))
        # Pas assez de carrousels : il en manque, compté en carrousels × 3.
        comptes[0]["calendrier"] = {"semaine-01": {"jour-1": [{"heure": f"1{i}h00", "type": "carousel"}
                                                              for i in range(5)]}}
        a = self.assertResultat(c.appeler("ranger_analyser", {"comptes": comptes, "types": ["carousel"]}))
        self.assertEqual(a["types"]["carousel"]["manque"], 6)
        self.assertTrue(a["incomplet"])
        # Au hasard + compléter : 3 carrousels pour 3 jours de 2 créneaux. Chaque jour reçoit
        # 2 carrousels DIFFÉRENTS (jamais le même carrousel posté deux fois le même jour), et pas
        # de legende.txt dans les créneaux. (carrousel-10 = copie de carrousel-1 : mêmes noms de
        # fichiers, on le retire pour pouvoir comparer les contenus.)
        shutil.rmtree(os.path.join(d["sortie"], "carrousel-10"))
        comptes[0]["calendrier"] = {"semaine-01": {f"jour-{j}": [{"heure": "12h00", "type": "carousel"},
                                                                 {"heure": "19h00", "type": "carousel"}]
                                                   for j in (1, 2, 3)}}
        for essai in range(5):     # le hasard : plusieurs tirages
            rid = c.envoyer("ranger_lancer", {"comptes": comptes, "types": ["carousel"], "aleatoire": True,
                                              "completer": True, "remplacer": os.path.join(base, "ranger")})
            self.assertResultat(c.fin(rid, 120))
            for j in (1, 2, 3):
                jour = os.path.join(base, "ranger", "semaine-01", f"jour-{j}")
                a_, b_ = (sorted(os.listdir(os.path.join(jour, n)))
                          for n in ("1_12h00_carousel", "2_19h00_carousel"))
                self.assertNotIn("legende.txt", a_ + b_)
                self.assertNotEqual(a_, b_, f"jour-{j}, tirage {essai}")

    def test_ranger_completer(self):
        """Pas assez de médias + completer : TOUS les créneaux sont remplis avec ceux qui sont là ;
        sans completer, comme avant, les derniers restent vides."""
        appdata, home = self.profil_isole("Profil completer")
        c = self.moteur(appdata=appdata, home=home)
        base = self.nouvelle_sortie(c, "Sortie completer")
        caro = os.path.join(appdata, "caro")
        os.makedirs(caro)
        modele = sorted(f for f in os.listdir(self.images) if f.endswith(".png"))[0]
        for i in range(1, 8):          # 7 images : 2 carrousels complets + 1 image seule
            shutil.copy(os.path.join(self.images, modele), os.path.join(caro, f"{i}.png"))
        jour = [{"heure": f"1{i}h00", "type": "story"} for i in range(5)]
        jour += [{"heure": f"2{i}h00", "type": "carousel"} for i in range(3)]
        comptes = [{"id": "c1", "nom": "@c", "sources": {"story": self.images, "carousel": caro},
                    "calendrier": {"semaine-01": {"jour-1": jour}}}]
        args = {"comptes": comptes, "types": ["story", "carousel"], "aleatoire": True}
        sortie = os.path.join(base, "ranger", "semaine-01", "jour-1")

        r = self.assertResultat(c.fin(c.envoyer("ranger_lancer", args), 120))
        self.assertEqual(r["incomplets"], {"story": 2, "carousel": 1})
        self.assertEqual(r["reutilises"], {"story": 0, "carousel": 0})

        r = self.assertResultat(c.fin(c.envoyer("ranger_lancer", dict(args, completer=True,
                                                                        remplacer=os.path.join(base, "ranger"))), 120))
        self.assertEqual(r["incomplets"], {"story": 0, "carousel": 0})
        self.assertEqual(r["manques"], {"story": 0, "carousel": 0})
        self.assertEqual(r["reutilises"], {"story": 2, "carousel": 3})
        # Le 3e carrousel repart du début (1-2-3) plutôt que de mélanger « 7 » avec « 1, 2 » ;
        # la 7e image, jamais placée, va dans « surplus ».
        self.assertEqual(sorted(os.listdir(os.path.join(sortie, "8_22h00_carousel"))),
                         ["1.png", "2.png", "3.png"])
        self.assertEqual(os.listdir(os.path.join(base, "ranger", "surplus", "Carrousels")), ["7.png"])
        for i in range(5):
            self.assertEqual(len([f for f in os.listdir(os.path.join(sortie, f"{i + 1}_1{i}h00_story"))
                                  if f.endswith(".png")]), 1)
        self.assertIn("♻️ 5 média(s) réutilisé(s)", r["bilan"]["message"])

    def test_ranger_plusieurs_comptes_erreurs(self):
        appdata, home = self.profil_isole("Profil erreurs comptes")
        c = self.moteur(appdata=appdata, home=home)
        base = self.nouvelle_sortie(c, "Sortie erreurs comptes")
        sortie = os.path.join(base, "ranger")
        os.makedirs(os.path.join(sortie, "Compte 1"))
        temoin = os.path.join(sortie, "Compte 1", "ancien.txt")
        open(temoin, "w").close()
        cal = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "story"}]}}
        bon = {"id": "c1", "nom": "Compte 1", "sources": {"story": self.images}, "calendrier": cal}

        def args(**second):
            autre = dict({"id": "c2", "nom": "@marie", "sources": {}, "calendrier": cal}, **second)
            return {"comptes": [bon, autre], "types": ["story"], "remplacer": sortie}

        # Dossier manquant (absent ou pas choisi) pour le 2e compte.
        a = self.assertResultat(c.appeler("ranger_analyser", args()))
        self.assertFalse(a["pret"])
        self.assertEqual(a["manquants"], ["story"])
        self.assertEqual([x["manquants"] for x in a["comptes"]], [[], ["story"]])
        e = self.assertErreur(c.appeler("ranger_lancer", args()), "SOURCE_INTROUVABLE")
        self.assertEqual((e["details"]["compte"], e["details"]["types"]), ("c2", ["story"]))
        self.assertIn("« @marie »", e["message"])
        absent = os.path.join(self.tmp, "absent é")
        e = self.assertErreur(c.appeler("ranger_lancer", args(sources={"story": absent})),
                              "SOURCE_INTROUVABLE")
        self.assertEqual((e["details"]["compte"], e["details"]["chemins"]), ("c2", [absent]))

        # Source DANS la sortie (même dans le dossier d'un AUTRE compte) : le remplacement la détruirait.
        dans = os.path.join(sortie, "Compte 1")
        a = self.assertResultat(c.appeler("ranger_analyser", args(sources={"story": dans})))
        self.assertFalse(a["pret"])
        self.assertEqual(a["comptes"][1]["source_dans_sortie"], ["story"])
        e = self.assertErreur(c.appeler("ranger_lancer", args(sources={"story": dans})),
                              "SOURCE_DANS_SORTIE")
        self.assertEqual((e["details"]["compte"], e["details"]["types"]), ("c2", ["story"]))
        self.assertTrue(e["message"].startswith("@marie : "), e["message"])

        # Calendrier invalide d'un compte : signalé par l'analyse, refusé AVANT la sortie.
        mauvais = {"semaine-01": {"CON": [{"heure": "12h00", "type": "story"}]}}
        a = self.assertResultat(c.appeler("ranger_analyser", args(
            sources={"story": self.images}, calendrier=mauvais)))
        self.assertFalse(a["pret"])
        self.assertIsNone(a["comptes"][0]["calendrier_erreur"])
        self.assertIn("CON", a["comptes"][1]["calendrier_erreur"])
        self.assertTrue(a["calendrier_erreur"].startswith("@marie : "))
        e = self.assertErreur(c.appeler("ranger_lancer", args(
            sources={"story": self.images}, calendrier=mauvais)), "CALENDRIER_INVALIDE")
        self.assertEqual(e["details"]["compte"], "c2")

        # Aucun type actif dans aucun compte.
        a = self.assertResultat(c.appeler("ranger_analyser", dict(
            args(sources={"story": self.images}), types=["carousel"])))
        self.assertFalse(a["pret"])
        self.assertEqual(a["actifs"], [])
        e = self.assertErreur(c.appeler("ranger_lancer", dict(
            args(sources={"story": self.images}), types=["carousel"])), "ARGUMENTS_INVALIDES")
        self.assertEqual(e["details"]["champ"], "types")

        # Champs de tête : seulement les comptes qui ont besoin du type. Les stories de « @marie »
        # (calendrier sans story) ne doivent pas faire croire que « Compte 1 » a ses images.
        reels = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "reel"}]}}
        a = self.assertResultat(c.appeler("ranger_analyser", {"types": ["story"], "comptes": [
            dict(bon, sources={"story": self.vide}),
            {"id": "c2", "nom": "@marie", "sources": {"story": self.images}, "calendrier": reels}]}))
        self.assertEqual({k: a["types"]["story"][k] for k in ("requis", "trouves", "manque")},
                         {"requis": 1, "trouves": 0, "manque": 1})

        # Liste de comptes invalide (noms en double) : refus clair, dès l'analyse.
        e = self.assertErreur(c.appeler("ranger_analyser", {"comptes": [
            bon, dict(bon, id="c2", nom="COMPTE 1")]}), "ARGUMENTS_INVALIDES")
        self.assertEqual(e["details"]["compte"], "c2")
        # L'ancienne sortie n'a jamais été touchée.
        self.assertTrue(os.path.exists(temoin))

    def test_ranger_plusieurs_comptes_annulation(self):
        appdata, home = self.profil_isole("Profil annulation comptes")
        c = self.moteur(appdata=appdata, home=home)
        base = self.nouvelle_sortie(c, "Sortie annulation comptes")
        sortie = os.path.join(base, "ranger")
        os.makedirs(sortie)
        open(os.path.join(sortie, "ancien.txt"), "w").close()
        # 3000 créneaux pour le 1er compte : assez long pour annuler PENDANT son rangement.
        gros = {"semaine-01": {f"jour-{j}": [{"heure": f"h{k:03d}", "type": "story"}
                                             for k in range(300)] for j in range(1, 11)}}
        petit = {"semaine-01": {"jour-1": [{"heure": "12h00", "type": "story"}]}}
        comptes = [{"id": "c1", "nom": "Gros compte", "sources": {"story": self.images},
                    "calendrier": gros},
                   {"id": "c2", "nom": "Petit compte", "sources": {"story": self.images},
                    "calendrier": petit}]
        rid = c.envoyer("ranger_lancer", {"comptes": comptes, "types": ["story"],
                                          "remplacer": sortie})
        c.attendre(lambda e: e.get("id") == rid and e.get("type") == "progress", 30)
        r = self.assertResultat(c.appeler("annuler", {"cible": rid}, 10))
        self.assertEqual(r["etat"], "annulation_demandee")
        d = self.assertResultat(c.fin(rid, 60))
        self.assertTrue(d["arrete"])
        self.assertLess(d["creneaux"], 3001)
        # Arrêté DANS le 1er compte ; le 2e n'a jamais commencé (arrêt respecté entre comptes).
        self.assertEqual([(x["id"], x["arrete"]) for x in d["comptes"]],
                         [("c1", True), ("c2", True)])
        self.assertEqual(d["comptes"][1]["creneaux"], 0)
        self.assertFalse(os.path.exists(os.path.join(sortie, "Petit compte")))
        self.assertTrue(d["bilan"]["message"].startswith("Rangement arrêté."), d["bilan"])
        self.assertIn("• Gros compte : ", d["bilan"]["message"])
        self.assertTrue(d["bilan"]["erreur"])
        self.assertFalse(self.assertResultat(c.appeler("etat"))["occupe"])

    # ----------------------------------------------------------------- arrêt
    def test_quitter(self):
        c = self.moteur()
        d = self.assertResultat(c.appeler("quitter", {"delai_s": 2}, 10))
        self.assertTrue(d["ok"])
        self.assertEqual(c.proc.wait(timeout=10), 0)

    def test_fin_de_l_entree_arrete_le_moteur(self):
        c = self.moteur()
        c.proc.stdin.close()                 # l'interface est partie
        self.assertEqual(c.proc.wait(timeout=10), 0)

    @unittest.skipUnless(sys.platform == "win32", "Job Object : Windows uniquement")
    def test_moteur_tue_brutalement_ffmpeg_meurt_aussi(self):
        """Gestionnaire des tâches / plantage : le Job Windows doit tuer ffmpeg avec le moteur."""
        c = self.moteur()
        self.nouvelle_sortie(c, "Sortie job")
        rid = c.envoyer("conversion_mp4", {"source": {"type": "fichiers",
                                                      "chemins": [self.video_longue]}})
        c.attendre(lambda e: e.get("id") == rid and e.get("type") == "progress"
                   and (e.get("details") or {}).get("element", {}).get("pct") not in (None, 0), 60)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={c.proc.pid}' | "
             "Where-Object Name -like 'ffmpeg*').ProcessId"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
        pids = [int(x) for x in r.stdout.split()]
        self.assertTrue(pids, "aucun ffmpeg enfant trouvé")
        c.proc.kill()                        # TerminateProcess : aucun nettoyage possible côté Python
        c.proc.wait(timeout=10)
        fin = time.monotonic() + 5
        while time.monotonic() < fin and any(processus_vivant(p) for p in pids):
            time.sleep(0.1)
        self.assertFalse(any(processus_vivant(p) for p in pids), "ffmpeg orphelin encore vivant")

    def test_quitter_pendant_une_conversion(self):
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie quitter")
        rid = c.envoyer("conversion_mp4", {"source": {"type": "fichiers",
                                                      "chemins": [self.video_longue]}})
        c.attendre(lambda e: e.get("id") == rid and e.get("type") == "progress", 30)
        t0 = time.monotonic()
        q = c.envoyer("quitter", {"delai_s": 5})
        self.assertResultat(c.fin(q, 10))
        self.assertEqual(c.proc.wait(timeout=10), 0)
        self.assertLess(time.monotonic() - t0, 5)
        fin = c.fin(rid, 1)                  # la tâche a bien rendu son « result » avant
        self.assertTrue(fin["data"]["arrete"])
        self.assertFalse(os.path.exists(os.path.join(base, "media (mp4)", "longue vidéo.mp4")))

    def test_quitter_puis_fin_de_l_entree_pendant_une_conversion(self):
        """Le cas NORMAL d'une app qui se ferme : « quitter », puis le tube d'entrée se ferme
        aussitôt. Le moteur doit quand même finir proprement (réponse, fin de tâche, ménage)."""
        c = self.moteur()
        base = self.nouvelle_sortie(c, "Sortie quitter EOF")
        rid = c.envoyer("conversion_mp4", {"source": {"type": "fichiers",
                                                      "chemins": [self.video_longue]}})
        c.attendre(lambda e: e.get("id") == rid and e.get("type") == "progress"
                   and (e.get("details") or {}).get("element", {}).get("pct") not in (None, 0), 60)
        q = c.envoyer("quitter", {"delai_s": 5})
        c.proc.stdin.close()                 # EOF tout de suite après
        self.assertEqual(c.proc.wait(timeout=15), 0)
        self.assertTrue(self.assertResultat(c.fin(q, 5))["ok"])
        self.assertTrue(self.assertResultat(c.fin(rid, 1))["arrete"])
        self.assertFalse(os.path.exists(os.path.join(base, "media (mp4)", "longue vidéo.mp4")),
                         "fichier .mp4 partiel laissé sur le disque")

    def test_enveloppe_de_progression_suit_la_signature_d_agent(self):
        """commandes.py enveloppe agent.progression.texte : même texte, détails relus PAR NOM.
        Lancé dans un sous-processus avec APPDATA temporaire (règle : jamais les vraies données)."""
        code = (
            "import sys, json, inspect; sys.path[:0] = [%r, %r]\n"
            "import commandes\n"
            "from agent import progression\n"
            "orig = progression.texte._helpva_original\n"
            "noms = set(inspect.signature(orig).parameters)\n"
            "attendus = {'quoi','k','total','dossier_i','dossier_n','nom_dossier','fichier','pct',"
            "'groupe','toujours'}\n"
            "a = ('Vidéo', 1, 4, 2, 3, 'Modèle A', 'clip.mov', 43.7)\n"
            "t = progression.texte(*a)\n"
            "t2 = progression.texte('Image', 2, 5, fichier='x.png', toujours=True, dossier_i=1, dossier_n=1)\n"
            "print(json.dumps({'manquants': sorted(attendus - noms), 'meme_texte': t == orig(*a),"
            " 'details': t.details, 'details2': t2.details}))\n"
        ) % (DOSSIER_ENGINE, os.path.dirname(DOSSIER_ENGINE))
        r = subprocess.run([sys.executable, "-c", code], env=self.env(), cwd=self.tmp,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        d = json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
        self.assertEqual(d["manquants"], [], "agent/progression.texte a changé de signature")
        self.assertTrue(d["meme_texte"])
        self.assertEqual(d["details"], {
            "groupe": {"mot": "Dossier", "index": 2, "total": 3, "nom": "Modèle A"},
            "element": {"mot": "Vidéo", "index": 1, "total": 4, "nom": "clip.mov", "pct": 43}})
        self.assertEqual(d["details2"]["groupe"], {"mot": "Dossier", "index": 1, "total": 1,
                                                   "nom": None})
        self.assertEqual(d["details2"]["element"]["nom"], "x.png")

    def test_licence_revérifiée_avant_chaque_traitement(self):
        """Avant un traitement : licence revérifiée en ligne (sauf confirmée il y a < 1 min).
        Refusée -> LICENCE_REFUSEE et licence_ok repasse à False. Tolérance hors-ligne : 6 h.
        Réseau simulé, APPDATA temporaire."""
        code = (
            "import sys, json; sys.path[:0] = [%r, %r]\n"
            "import commandes\n"
            "from agent import licence\n"
            "class M:\n"
            "    maj = []\n"
            "    def generation_licence(self): return 0\n"
            "    def licence_maj(self, ok, g): self.maj.append(ok); return True\n"
            "class C:\n"
            "    moteur = M(); textes = []\n"
            "    def progress(self, t, f=None): self.textes.append(t)\n"
            "appels = []\n"
            "def verifier(st):\n"
            "    def f(): appels.append(1); return st\n"
            "    return f\n"
            "out = {'grace': licence.GRACE_HORS_LIGNE_H}\n"
            "licence.chemin_licence = lambda: sys.executable\n"   # un fichier qui existe
            "licence.confirmee_recemment = lambda s: True\n"
            "licence.verifier = verifier({'ok': False, 'raison': 'revoquee'})\n"
            "commandes.controler_licence_avant_operation(C(), {}); out['recent_appels'] = len(appels)\n"
            "licence.confirmee_recemment = lambda s: False\n"
            "licence.verifier = verifier({'ok': True, 'raison': 'actif'})\n"
            "commandes.controler_licence_avant_operation(C(), {})\n"
            "licence.verifier = verifier({'ok': False, 'raison': 'pas_internet'})\n"
            "try:\n"
            "    commandes.controler_licence_avant_operation(C(), {}); out['code'] = None\n"
            "except commandes.ErreurCommande as e:\n"
            "    out['code'] = e.code; out['raison'] = e.details['statut']['raison']\n"
            "out['appels'] = len(appels); out['maj'] = M.maj; out['textes'] = C.textes\n"
            "print(json.dumps(out))\n"
        ) % (DOSSIER_ENGINE, os.path.dirname(DOSSIER_ENGINE))
        r = subprocess.run([sys.executable, "-c", code], env=self.env(), cwd=self.tmp,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        d = json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
        self.assertEqual(d["grace"], 6)
        self.assertEqual(d["recent_appels"], 0, "confirmée il y a < 1 min : pas d'appel réseau")
        self.assertEqual(d["appels"], 2)
        self.assertEqual(d["maj"], [True, False])
        self.assertEqual(d["code"], "LICENCE_REFUSEE")
        self.assertEqual(d["raison"], "pas_internet")
        self.assertEqual(d["textes"], ["Vérification de la licence…"] * 2)

    def test_offre_gratuite(self):
        """Sans licence : offre gratuite comptée par le serveur (simulé ici, quota 5).
        Mêmes médias -> pas recomptés ; trop de nouveaux -> refusé AVANT de démarrer ;
        quota atteint -> « essai_fini » ; serveur injoignable -> « pas_internet »."""
        dossier = os.path.join(self.tmp, "essai")
        os.makedirs(dossier)
        code = (
            "import sys, os, json; sys.path[:0] = [%r, %r]\n"
            "import commandes\n"
            "from agent import licence, essai\n"
            "D = %r\n"
            "def image(nom):\n"
            "    open(os.path.join(D, nom), 'wb').write(nom.encode() * 50)\n"
            "QUOTA = 5; essai.QUOTA = QUOTA; base = set(); joignable = [True]\n"
            "def rpc(f, corps):\n"
            "    if not joignable[0]: return None\n"
            "    n = len(base)\n"
            "    if f == 'essai_statut':\n"
            "        return {'quota': QUOTA, 'utilises': n, 'restant': QUOTA - n}\n"
            "    neufs = set(corps['p_medias']) - base\n"
            "    if n + len(neufs) > QUOTA:\n"
            "        return {'ok': False, 'quota': QUOTA, 'utilises': n, 'restant': QUOTA - n,"
            " 'nouveaux': len(neufs)}\n"
            "    base.update(neufs)\n"
            "    return {'ok': True, 'quota': QUOTA, 'utilises': len(base),"
            " 'restant': QUOTA - len(base), 'nouveaux': len(neufs)}\n"
            "essai._rpc = rpc\n"
            "licence.verifier = lambda: {'ok': False, 'raison': 'pas_active', 'type': None,"
            " 'expire_le': None, 'jours_restants': None}\n"
            "class M:\n"
            "    maj = []\n"
            "    def generation_licence(self): return 0\n"
            "    def licence_maj(self, ok, g): self.maj.append(ok); return True\n"
            "class C:\n"
            "    moteur = M(); cmd = 'metadonnees'\n"
            "    def progress(self, t, f=None): pass\n"
            "ARGS = {'source': {'type': 'dossier', 'chemin': D}}\n"
            "def lancer():\n"
            "    try:\n"
            "        commandes.controler_licence_avant_operation(C(), ARGS)\n"
            "        return ['ok', len(base)]\n"
            "    except commandes.ErreurCommande as e:\n"
            "        return [e.code, e.details and e.details.get('restant'),"
            " e.details and e.details.get('nouveaux'), len(base)]\n"
            "def statut():\n"
            "    st = commandes._avec_essai(licence.verifier())\n"
            "    return [st['ok'], st['raison'], st['type'], (st['essai'] or {}).get('restant')]\n"
            "out = {'debut': statut()}\n"
            "for n in ('a', 'b', 'c'): image(n + '.png')\n"
            "out['trois'] = lancer(); out['memes'] = lancer()\n"
            "for n in ('d', 'e', 'f'): image(n + '.png')\n"
            "out['six'] = lancer()\n"
            "os.remove(os.path.join(D, 'f.png'))\n"
            "out['cinq'] = lancer(); out['fini'] = statut()\n"
            "for n in 'abcde': os.remove(os.path.join(D, n + '.png'))\n"
            "image('g.png'); out['apres'] = lancer(); out['maj'] = M.maj\n"
            "joignable[0] = False; out['hors_ligne'] = statut()\n"
            "print(json.dumps(out))\n"
        ) % (DOSSIER_ENGINE, os.path.dirname(DOSSIER_ENGINE), dossier)
        r = subprocess.run([sys.executable, "-c", code], env=self.env(), cwd=self.tmp,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        d = json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
        self.assertEqual(d["debut"], [True, "essai_gratuit", "gratuit", 5])
        self.assertEqual(d["trois"], ["ok", 3])
        self.assertEqual(d["memes"], ["ok", 3], "les mêmes médias ne recomptent pas")
        self.assertEqual(d["six"], ["ESSAI_INSUFFISANT", 2, 3, 3], "refusé, rien de réservé")
        self.assertEqual(d["cinq"], ["ok", 5])
        self.assertEqual(d["fini"], [False, "essai_fini", "gratuit", 0])
        self.assertEqual(d["apres"], ["LICENCE_REFUSEE", None, None, 5])
        self.assertEqual(d["hors_ligne"], [False, "pas_internet", "gratuit", None])
        self.assertEqual(d["maj"], [True, True, True, False])


# ═══════════════════════════════════════════════════════════════════════════
#  agent/activite.py directement (dans CE processus, réseau simulé)
# ═══════════════════════════════════════════════════════════════════════════
class TestActivite(unittest.TestCase):
    """Le compteur et l'envoi, sans moteur. APPDATA pointe vers un dossier TEMPORAIRE et
    l'ancien emplacement (à côté de l'exe) aussi : jamais les vraies données. `requests` est
    remplacé par un faux module : on voit chaque appel réseau, aucun ne part vraiment."""

    def setUp(self):
        from unittest import mock
        racine = os.path.dirname(DOSSIER_ENGINE)
        if racine not in sys.path:
            sys.path.insert(0, racine)
        self.tmp = tempfile.mkdtemp(prefix="HelpVA activité é ")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        appdata = os.path.join(self.tmp, "appdata")
        os.makedirs(appdata)
        env = mock.patch.dict(os.environ, {"APPDATA": appdata, "XDG_DATA_HOME": appdata,
                                           "USERPROFILE": self.tmp, "HOME": self.tmp})
        env.start()
        self.addCleanup(env.stop)
        from agent import activite, emplacement
        ancien = mock.patch.object(emplacement, "dossier_exe", lambda: self.tmp)
        ancien.start()
        self.addCleanup(ancien.stop)
        self.activite = activite
        self.dossier = emplacement.dossier_donnees()
        self.assertTrue(self.dossier.startswith(appdata), self.dossier)
        # Faux « requests » : enregistre les appels, répond {"ok": true}.
        self.appels = []
        test = self

        class Reponse:
            def json(self):
                return {"ok": True}

        class FauxRequests:
            @staticmethod
            def post(url, **kw):
                test.appels.append((url, kw))
                return Reponse()
        faux = mock.patch.dict(sys.modules, {"requests": FauxRequests})
        faux.start()
        self.addCleanup(faux.stop)

    def fichier(self):
        with open(os.path.join(self.dossier, "activite.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_sans_licence_aucun_appel_reseau(self):
        self.activite.ajouter("images", 4)
        self.activite.ajouter("videos", 0)      # ignoré
        self.activite.ajouter("videos", -3)     # ignoré
        self.assertFalse(self.activite.envoyer())
        self.assertEqual(self.appels, [])
        self.assertFalse(self.activite.partage())
        r = self.activite.resume()
        self.assertEqual(r["aujourd_hui"], {"images": 4, "videos": 0, "metadonnees": 0,
                                            "total": 4})

    def test_memes_medias_comptes_une_seule_fois(self):
        src = os.path.join(self.dossier, "src")
        os.makedirs(src)
        chemins = []
        for i in range(3):
            p = os.path.join(src, f"{i}.jpg")
            with open(p, "wb") as f:
                f.write(bytes([i]) * 1000)
            chemins.append(p)
        copie = os.path.join(src, "copie renommée.jpg")      # doublon de 0.jpg
        with open(copie, "wb") as f:
            f.write(bytes([0]) * 1000)
        self.assertEqual(self.activite.ajouter_medias("images", chemins + [copie], 4), 3)
        self.assertEqual(self.activite.ajouter_medias("images", chemins, 3), 0)
        # Autre catégorie : comptée à part (le même média peut être converti PUIS modifié).
        self.assertEqual(self.activite.ajouter_medias("metadonnees", chemins, 3), 3)
        # Arrêt en cours de route : seuls les n premiers nouveaux sont comptés et marqués.
        autres = []
        for i in range(3, 6):
            p = os.path.join(src, f"{i}.jpg")
            with open(p, "wb") as f:
                f.write(bytes([i]) * 1000)
            autres.append(p)
        self.assertEqual(self.activite.ajouter_medias("images", autres, 1), 1)
        self.assertEqual(self.activite.ajouter_medias("images", autres, 3), 2)
        self.assertEqual(self.activite.resume()["aujourd_hui"]["images"], 6)

    def test_envoi_avec_licence_seulement_ce_qui_a_change(self):
        from datetime import date
        with open(os.path.join(self.dossier, "licence.key"), "w", encoding="utf-8") as f:
            f.write("LICENCE-DE-TEST.signature\n")
        self.assertTrue(self.activite.partage())
        self.activite.ajouter("metadonnees", 5)
        self.activite.ajouter("videos", 2)
        self.assertTrue(self.activite.envoyer())
        self.assertEqual(len(self.appels), 1)
        url, kw = self.appels[0]
        self.assertTrue(url.endswith("/functions/v1/admin"), url)
        self.assertEqual(kw["timeout"], 8)
        aujourd_hui = date.today().isoformat()
        self.assertEqual(kw["json"], {"action": "activite", "licence": "LICENCE-DE-TEST.signature",
                                      "jours": [{"jour": aujourd_hui, "images": 0, "videos": 2,
                                                 "metadonnees": 5}]})
        self.assertEqual(self.fichier()["envoye"][aujourd_hui]["metadonnees"], 5)
        # Rien de nouveau : aucun appel.
        self.assertTrue(self.activite.envoyer())
        self.assertEqual(len(self.appels), 1)
        # Nouveau traitement : le jour repart, avec ses valeurs ABSOLUES.
        self.activite.ajouter("metadonnees", 1)
        self.assertTrue(self.activite.envoyer())
        self.assertEqual(self.appels[1][1]["json"]["jours"][0]["metadonnees"], 6)

    def test_purge_des_vieux_jours_total_conserve(self):
        from datetime import date, timedelta
        vieux = (date.today() - timedelta(days=500)).isoformat()
        recent = (date.today() - timedelta(days=3)).isoformat()
        with open(os.path.join(self.dossier, "activite.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "jours": {vieux: {"images": 10}, recent: {"videos": 2}},
                       "envoye": {vieux: {"images": 10}}}, f)
        self.activite.ajouter("images", 1)
        d = self.fichier()
        self.assertNotIn(vieux, d["jours"])
        self.assertNotIn(vieux, d["envoye"])
        self.assertIn(recent, d["jours"])
        r = self.activite.resume()
        self.assertEqual(r["total"]["images"], 11)          # le jour purgé compte encore
        self.assertEqual(r["total"]["total"], 13)
        self.assertEqual(r["semaine"]["total"], 3)          # 2 vidéos (J-3) + 1 image
        self.assertEqual(r["depuis"], vieux)

    def test_fichier_illisible_mis_de_cote(self):
        with open(os.path.join(self.dossier, "activite.json"), "w", encoding="utf-8") as f:
            f.write("{pas du json")
        r = self.activite.resume()
        self.assertEqual(r["total"]["total"], 0)
        self.assertIsNone(r["depuis"])
        mis_de_cote = [n for n in os.listdir(self.dossier) if n.startswith("activite.illisible-")]
        self.assertEqual(len(mis_de_cote), 1)
        self.activite.ajouter("images", 2)                  # on repart de zéro, sans planter
        self.assertEqual(self.activite.resume()["total"]["images"], 2)


# ═══════════════════════════════════════════════════════════════════════════
#  Le pont de développement (HTTP + SSE)
# ═══════════════════════════════════════════════════════════════════════════
class TestPontDev(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="HelpVA pont é ")
        appdata = os.path.join(self.tmp, "appdata")
        home = os.path.join(self.tmp, "home")
        os.makedirs(appdata)
        os.makedirs(home)
        env = dict(os.environ, APPDATA=appdata, USERPROFILE=home, HOME=home,
                   PYTHONIOENCODING="utf-8")
        self.fichier_jeton = os.path.join(self.tmp, "jeton.txt")
        self.donnees = os.path.join(self.tmp, "données dev")
        self.proc = subprocess.Popen(
            [sys.executable, PONT, "--port", "0", "--fichier-jeton", self.fichier_jeton,
             "--donnees", self.donnees],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        self.addCleanup(self._fermer)
        self.port = None
        fin = time.monotonic() + 20
        self.sortie = []
        while time.monotonic() < fin:
            ligne = self.proc.stdout.readline().decode("utf-8", "replace")
            if not ligne:
                break
            self.sortie.append(ligne)
            if "http://127.0.0.1:" in ligne:
                self.port = int(ligne.rsplit(":", 1)[1].strip())
                break
        self.assertIsNotNone(self.port, "".join(self.sortie))
        threading.Thread(target=lambda: [None for _ in self.proc.stdout], daemon=True).start()
        with open(self.fichier_jeton, encoding="utf-8") as f:
            self.jeton = f.read().strip()
        self.base = f"http://127.0.0.1:{self.port}"

    def _fermer(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        self.proc.stdout.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def requete(self, chemin, methode="GET", corps=None, entetes=None):
        req = urllib.request.Request(self.base + chemin, method=methode, data=corps,
                                     headers=entetes or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_pont(self):
        jeton = {"X-HelpVA-Token": self.jeton}
        # Sans jeton / mauvaise origine -> refus.
        self.assertEqual(self.requete("/health")[0], 401)
        self.assertEqual(self.requete("/health", entetes={"X-HelpVA-Token": "faux"})[0], 401)
        self.assertEqual(self.requete("/health", entetes=dict(jeton, Origin="https://pirate.example"))[0],
                         403)
        # Preflight CORS depuis Vite.
        code, entetes, _ = self.requete("/cmd", "OPTIONS", entetes={
            "Origin": "http://localhost:1420", "Access-Control-Request-Method": "POST"})
        self.assertEqual(code, 204)
        self.assertEqual(entetes.get("Access-Control-Allow-Origin"), "http://localhost:1420")
        # Santé : le moteur tourne.
        fin = time.monotonic() + 20
        while True:
            code, _, corps = self.requete("/health", entetes=jeton)
            sante = json.loads(corps)
            if sante.get("pret") or time.monotonic() > fin:
                break
            time.sleep(0.2)
        self.assertEqual(code, 200)
        self.assertTrue(sante["moteur_vivant"])
        self.assertEqual(sante["pret"]["protocole"], 1)
        pid_moteur = sante["pid_moteur"]

        # Flux SSE (jeton dans l'URL, comme le fera EventSource) + une commande.
        recus = []
        pret_sse = threading.Event()

        def ecouter():
            try:
                with urllib.request.urlopen(self.base + "/events?token=" + self.jeton,
                                            timeout=20) as r:
                    pret_sse.set()
                    for brut in r:
                        ligne = brut.decode("utf-8").strip()
                        if ligne.startswith("data: "):
                            recus.append(json.loads(ligne[6:]))
            except OSError:
                pass        # normal : le pont est tué à la fin du test
        threading.Thread(target=ecouter, daemon=True).start()
        self.assertTrue(pret_sse.wait(10))
        code, _, corps = self.requete("/cmd", "POST",
                                      json.dumps({"id": "p-1", "cmd": "ping"}).encode(),
                                      dict(jeton, **{"Content-Type": "application/json"}))
        self.assertEqual(code, 202, corps)
        fin = time.monotonic() + 10
        while time.monotonic() < fin and not any(e.get("id") == "p-1" for e in recus):
            time.sleep(0.05)
        self.assertIn({"id": "p-1", "type": "result", "data": {"pong": True}}, recus)
        self.assertTrue(any(e.get("type") == "pret" for e in recus))   # « pret » rejoué
        # Le moteur du pont travaille dans le dossier de données de TEST (--donnees).
        self.requete("/cmd", "POST", json.dumps({"id": "p-2", "cmd": "info"}).encode(),
                     dict(jeton, **{"Content-Type": "application/json"}))
        fin = time.monotonic() + 10
        while time.monotonic() < fin and not any(e.get("id") == "p-2" for e in recus):
            time.sleep(0.05)
        info = next(e for e in recus if e.get("id") == "p-2")["data"]
        self.assertTrue(os.path.normcase(info["dossier_donnees"]).startswith(
            os.path.normcase(self.donnees)), info["dossier_donnees"])
        self.assertTrue(os.path.normcase(info["dossier_sortie_defaut"]).startswith(
            os.path.normcase(self.donnees)), info["dossier_sortie_defaut"])
        # Requête mal formée -> 400.
        self.assertEqual(self.requete("/cmd", "POST", b"{}", jeton)[0], 400)

        # Pont tué brutalement -> le moteur voit la fin de son entrée et s'arrête seul.
        self.proc.kill()
        self.proc.wait(timeout=10)
        fin = time.monotonic() + 10
        while time.monotonic() < fin and processus_vivant(pid_moteur):
            time.sleep(0.1)
        self.assertFalse(processus_vivant(pid_moteur), "le moteur est resté orphelin")


if __name__ == "__main__":
    unittest.main()
