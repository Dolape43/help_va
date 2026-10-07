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
            ffmpeg("-f", "lavfi", "-i", f"testsrc=size=96x64:rate=1:duration=1",
                   "-frames:v", "1", os.path.join(cls.images, f"{i} photo ☀.png"))
        cls.vide = os.path.join(cls.tmp, "Dossier vide")
        os.makedirs(cls.vide)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ----------------------------------------------------------------- outils
    def env(self, sans_licence: bool = True) -> dict:
        env = dict(os.environ)
        env.update({"APPDATA": self.appdata, "USERPROFILE": self.home, "HOME": self.home,
                    "XDG_DATA_HOME": self.appdata, "HELPVA_MOTEUR_TESTS": "1"})
        env.pop("HELPVA_MOTEUR_SANS_LICENCE", None)
        if sans_licence:
            env["HELPVA_MOTEUR_SANS_LICENCE"] = "1"
        return env

    def moteur(self, sans_licence: bool = True) -> ClientMoteur:
        c = ClientMoteur(self.env(sans_licence), cwd=self.tmp)
        self.addCleanup(self._verifier_et_fermer, c)
        return c

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

    # ----------------------------------------------------------------- licence
    def test_licence_requise_sans_contournement(self):
        c = self.moteur(sans_licence=False)
        st = self.assertResultat(c.appeler("licence_statut"))
        self.assertFalse(st["ok"])
        self.assertEqual(st["raison"], "pas_active")
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
