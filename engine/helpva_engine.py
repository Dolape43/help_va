"""
Moteur HelpVA — programme « sidecar » SANS interface.

L'interface (Tauri + React) lance ce programme et lui parle par ses tubes :
  - elle ÉCRIT des requêtes sur notre entrée (stdin), une ligne JSON par requête ;
  - nous ÉCRIVONS des événements sur notre sortie (stdout), une ligne JSON chacun.

    → {"id":"c-12","cmd":"conversion_mp4","args":{"source":{...}}}
    ← {"id":"c-12","type":"progress","fraction":0.38,"texte":"Vidéo 1/4 · clip.mov — 43 %",...}
    ← {"id":"c-12","type":"log","flux":"stdout","niveau":"info","texte":"[convert] (1/4) clip.mov…"}
    ← {"id":"c-12","type":"result","data":{...}}        (ou "type":"error")

Le cerveau reste dans agent/ (le même code que l'ancienne app CustomTkinter).
Ce fichier ne fait que la « plomberie » : lire, répartir, répondre.
Les commandes elles-mêmes sont dans commandes.py.

Le protocole complet est décrit dans README.md (même dossier).
"""

# ═══════════════════════════════════════════════════════════════════════════
#  1. PROTECTION DE STDOUT — À FAIRE AVANT TOUT AUTRE IMPORT
# ═══════════════════════════════════════════════════════════════════════════
# Pourquoi si tôt ? stdout est RÉSERVÉ au protocole : une seule ligne parasite
# (un print() oublié, un message d'une bibliothèque en C, ffmpeg qui écrit…)
# et l'interface reçoit du JSON cassé. On met donc de côté une copie PRIVÉE des
# vrais tubes, puis on branche les descripteurs 0 et 1 sur « nul » (os.devnull) :
#   - une écriture parasite sur le fd 1 part à la poubelle ;
#   - un sous-processus (ffmpeg) hérite d'une entrée VIDE et ne peut donc pas
#     « voler » des octets de nos commandes (sous Windows, ffmpeg lit stdin
#     pour ses raccourcis clavier q / ?).
import os
import sys


def _proteger_canaux():
    fd_sortie = os.dup(1)          # copie privée du tube de sortie
    fd_entree = os.dup(0)          # copie privée du tube d'entrée
    sortie = os.fdopen(fd_sortie, "wb", buffering=0)   # pas de tampon : chaque ligne part tout de suite
    entree = os.fdopen(fd_entree, "rb")                # tamponné : readline() efficace
    nul = os.open(os.devnull, os.O_RDWR)
    os.dup2(nul, 0)
    os.dup2(nul, 1)
    os.close(nul)
    if sys.platform == "win32":
        # Les sous-processus Windows héritent des « poignées standard » du
        # processus (GetStdHandle), pas des fd du C. On les repointe aussi sur
        # « nul », pour être certain que ffmpeg ne voie jamais nos tubes.
        try:
            import ctypes
            import msvcrt
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
            k32.SetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF), msvcrt.get_osfhandle(0))  # STD_INPUT
            k32.SetStdHandle(wintypes.DWORD(-11 & 0xFFFFFFFF), msvcrt.get_osfhandle(1))  # STD_OUTPUT
        except Exception:
            pass
    return entree, sortie


CANAL_ENTREE, CANAL_SORTIE = _proteger_canaux()

# ═══════════════════════════════════════════════════════════════════════════
#  2. Imports (légers seulement : PIL, numpy, cryptography… sont importés plus
#     tard, à la première commande qui en a besoin -> « pret » part très vite)
# ═══════════════════════════════════════════════════════════════════════════
import io                                      # noqa: E402
import json                                    # noqa: E402
import math                                    # noqa: E402
import platform                                # noqa: E402
import re                                      # noqa: E402
import signal                                  # noqa: E402
import threading                               # noqa: E402
import time                                    # noqa: E402
import traceback                               # noqa: E402
from concurrent.futures import ThreadPoolExecutor   # noqa: E402
from datetime import date, datetime            # noqa: E402

GELE = bool(getattr(sys, "frozen", False))     # True dans l'exe PyInstaller

if not GELE:
    # En développement : on rend importables agent/ (racine du dépôt) et
    # commandes.py (ce dossier), d'où que le script soit lancé.
    _ICI = os.path.dirname(os.path.abspath(__file__))
    for _p in (_ICI, os.path.dirname(_ICI)):
        if _p not in sys.path:
            sys.path.insert(0, _p)

import commandes                               # noqa: E402
from commandes import ErreurCommande, LONGUE, RESEAU   # noqa: E402

PROTOCOLE = 1                       # change SEULEMENT si le format devient incompatible
TAILLE_MAX_LIGNE = 16 * 1024 * 1024  # 16 Mo (une sélection de 3 000 fichiers ≈ 500 Ko)
DELAI_ARRET_S = 5.0                 # temps laissé à la tâche longue pour s'arrêter
DELAI_CRITIQUE_S = 30.0             # temps laissé à une commande CRITIQUE (licence_activer…)

# Pour retrouver l'id d'une ligne qu'on ne peut pas lire en entier (trop grosse, JSON
# cassé) : {"id":"c-12", … en tout début de ligne (après un éventuel BOM UTF-8).
_ID_EN_TETE = re.compile(rb'\s*(?:\xef\xbb\xbf)?\s*\{\s*"id"\s*:\s*"([^"\\]{1,200})"')

# Commandes de CONTRÔLE : exécutées tout de suite, jamais mises en file d'attente
# (sinon « annuler » attendrait la fin de ce qu'il doit annuler…).
CONTROLE = ("annuler", "etat", "ping", "quitter")

# Le fil (thread) courant sait pour quelle requête il travaille : c'est ce qui
# permet de rattacher un print() au bon « id ».
_local = threading.local()


# ═══════════════════════════════════════════════════════════════════════════
#  3. Petits outils
# ═══════════════════════════════════════════════════════════════════════════
def _json_par_defaut(obj):
    """Ce que json ne sait pas écrire tout seul (dates de licence, ensembles…)."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    return str(obj)


def _sans_nan(obj):
    """NaN / Infinity -> null : JSON.parse (côté interface) refuse ces valeurs."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sans_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sans_nan(v) for v in obj]
    return obj


def _refuser_constante(nom):
    """json.loads accepte NaN / Infinity par défaut (ce n'est pas du JSON standard) : on refuse."""
    raise ValueError(f"valeur non autorisée : {nom}")


def encoder(evenement: dict) -> bytes:
    """Un événement -> UNE ligne JSON 100 % ASCII (voir README)."""
    try:
        texte = json.dumps(evenement, ensure_ascii=True, separators=(",", ":"),
                           default=_json_par_defaut, allow_nan=False)
    except ValueError:
        texte = json.dumps(_sans_nan(evenement), ensure_ascii=True, separators=(",", ":"),
                           default=_json_par_defaut, allow_nan=False)
    return texte.encode("ascii") + b"\n"


def niveau_du_texte(texte: str) -> str:
    """Niveau d'une ligne de journal, déduit des symboles qu'utilise agent/."""
    if "⛔" in texte:
        return "arret"
    if "[ERREUR]" in texte:
        return "erreur"
    if "✅" in texte:
        return "succes"
    if any(m in texte for m in ("⚠", "[!]", "❌", "⏭")):
        return "avertissement"
    return "info"


def _attacher_job_windows():
    """Place le moteur dans un « Job » Windows qui tue ses enfants avec lui.

    Si le moteur est tué brutalement (Gestionnaire des tâches, plantage de
    l'interface…), Windows tue aussi les ffmpeg lancés par lui. Sans ça, un
    ffmpeg orphelin continuerait seul, à 100 % de CPU. Aucune dépendance : ctypes.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class LIMITES_BASE(ctypes.Structure):          # JOBOBJECT_BASIC_LIMIT_INFORMATION
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class LIMITES_ETENDUES(ctypes.Structure):      # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
            _fields_ = [("BasicLimitInformation", LIMITES_BASE),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                ctypes.c_void_p, wintypes.DWORD]
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = LIMITES_ETENDUES()
        info.BasicLimitInformation.LimitFlags = 0x2000     # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None
        if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
            return None
        return job      # on garde la poignée OUVERTE : elle se ferme à notre mort -> enfants tués
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  4. print() -> événements « log »
# ═══════════════════════════════════════════════════════════════════════════
class FluxJournal(io.TextIOBase):
    """Remplace sys.stdout / sys.stderr : chaque LIGNE écrite devient un événement log.

    print("abc") appelle write("abc") PUIS write("\\n") : on garde donc le début
    de ligne en mémoire, PAR FIL (threading.local), jusqu'au « \\n ». Deux fils
    qui écrivent en même temps ne mélangent ainsi jamais leurs lignes.
    """

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, moteur, flux: str):
        super().__init__()
        self._moteur = moteur
        self._flux = flux
        self._tampons = threading.local()

    def writable(self):
        return True

    def isatty(self):
        return False

    def write(self, texte):
        if not isinstance(texte, str):
            texte = str(texte)
        if not texte:
            return 0
        tampon = getattr(self._tampons, "texte", "") + texte
        *lignes, reste = tampon.split("\n")
        if len(reste) > 64 * 1024:          # ligne géante sans « \n » : on l'émet quand même
            lignes.append(reste)
            reste = ""
        self._tampons.texte = reste
        for ligne in lignes:
            self._moteur.journal(self._flux, ligne.rstrip("\r"))
        return len(texte)

    def flush(self):
        pass

    def vider(self):
        """Émet le morceau de ligne resté en mémoire pour CE fil (fin de commande)."""
        reste = getattr(self._tampons, "texte", "")
        if reste:
            self._tampons.texte = ""
            self._moteur.journal(self._flux, reste)


# ═══════════════════════════════════════════════════════════════════════════
#  5. Le moteur : lecture, répartition, tâches
# ═══════════════════════════════════════════════════════════════════════════
class Tache:
    """Une tâche LONGUE en cours (conversion, métadonnées, rangement)."""

    def __init__(self, id_req: str, cmd: str):
        self.id = id_req
        self.cmd = cmd
        self.annulee = threading.Event()     # le « drapeau » lu par doit_arreter()
        self.debut = time.monotonic()
        self.thread = None
        self.derniere_progression = None


class Contexte:
    """Ce qu'une commande reçoit pour parler au moteur (voir commandes.py)."""

    def __init__(self, moteur, id_req: str, cmd: str, tache: Tache = None):
        self.moteur = moteur
        self.id = id_req
        self.cmd = cmd
        self.tache = tache

    def doit_arreter(self) -> bool:
        """À passer tel quel aux fonctions d'agent/ (paramètre doit_arreter)."""
        return self.tache is not None and self.tache.annulee.is_set()

    def progress(self, texte, fraction=None):
        """À passer tel quel aux fonctions d'agent/ (paramètre progress)."""
        self.moteur.progression(self, texte, fraction)


class Moteur:
    def __init__(self):
        self._verrou = threading.Lock()          # protège tache / en_cours / arret
        self._verrou_sortie = threading.Lock()   # une ligne entière à la fois sur stdout
        self.tache = None                        # tâche longue en cours (une seule)
        self.en_cours = {}                       # id -> cmd, pour toutes les requêtes en cours
        self.arret = False
        self._arret_lance = False
        self.sortie_cassee = False
        self.protocole = PROTOCOLE
        self.licence_ok = False                  # devient True quand licence_statut dit ok
        # « Génération » de la licence : +1 à chaque résiliation / activation. Une
        # vérification lente ne modifie licence_ok que si la génération n'a pas bougé
        # depuis son début (sinon un vieux « ok » écraserait une résiliation récente).
        self._generation_licence = 0
        # Contournement de licence : SEULEMENT en développement (jamais dans l'exe).
        self.sans_licence = (not GELE and os.environ.get("HELPVA_MOTEUR_SANS_LICENCE") == "1")
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rapide")
        # Groupe de fils À PART pour le réseau (licence_*) : hors-ligne, une vérification
        # peut durer ~40 s ; elle ne doit jamais bloquer preparer, parametres_lire…
        self.pool_reseau = ThreadPoolExecutor(max_workers=4, thread_name_prefix="reseau")
        self.flux_stdout = FluxJournal(self, "stdout")
        self.flux_stderr = FluxJournal(self, "stderr")

    # ----------------------------------------------------------- licence (état de session)
    def generation_licence(self) -> int:
        with self._verrou:
            return self._generation_licence

    def licence_maj(self, ok: bool, generation: int, nouvelle_generation: bool = False) -> bool:
        """licence_ok = ok, SEULEMENT si aucune résiliation/activation n'a eu lieu depuis
        `generation`. Renvoie True si la valeur a été appliquée."""
        with self._verrou:
            if generation != self._generation_licence:
                return False
            self.licence_ok = ok
            if nouvelle_generation:
                self._generation_licence += 1
            return True

    def licence_reinitialiser(self) -> None:
        with self._verrou:
            self._generation_licence += 1
            self.licence_ok = False

    # ----------------------------------------------------------- émission
    def _ecrire(self, ligne: bytes) -> None:
        """Écrit une ligne déjà encodée. À appeler EN TENANT self._verrou_sortie."""
        if self.sortie_cassee:
            return
        try:
            vue = memoryview(ligne)
            while vue:
                n = CANAL_SORTIE.write(vue)
                vue = vue[n or 0:]
        except (OSError, ValueError):
            # L'interface a fermé le tube : plus personne à qui parler.
            self.sortie_cassee = True

    def emettre(self, evenement: dict) -> None:
        """Écrit UNE ligne JSON sur le vrai stdout (100 % ASCII, voir README)."""
        ligne = encoder(evenement)
        with self._verrou_sortie:
            self._ecrire(ligne)

    def erreur(self, id_req, code: str, message: str, details=None) -> None:
        self.emettre({"id": id_req, "type": "error", "code": code,
                      "message": message, "details": details})

    def id_courant(self):
        """id de la requête pour laquelle le fil courant travaille.

        Fil d'une commande -> son id. Sinon (fils internes d'agent/, par ex. le
        traitement d'images en parallèle) -> l'id de la tâche longue en cours."""
        rid = getattr(_local, "id", None)
        if rid is None:
            t = self.tache
            rid = t.id if t is not None else None
        return rid

    def journal(self, flux: str, texte: str, niveau: str = None, id_req="auto") -> None:
        self.emettre({"id": self.id_courant() if id_req == "auto" else id_req,
                      "type": "log", "flux": flux,
                      "niveau": niveau or niveau_du_texte(texte), "texte": texte})

    def progression(self, ctx: Contexte, texte, fraction=None) -> None:
        details = getattr(texte, "details", None)
        if fraction is not None:
            try:
                fraction = round(max(0.0, min(1.0, float(fraction))), 4)
            except (TypeError, ValueError):
                fraction = None
        ev = {"id": ctx.id, "type": "progress", "fraction": fraction,
              "texte": str(texte), "details": details}
        if ctx.tache is not None:
            ctx.tache.derniere_progression = {"fraction": fraction, "texte": str(texte),
                                              "details": details}
        self.emettre(ev)

    # ----------------------------------------------------------- démarrage
    def evenement_pret(self) -> dict:
        from agent import version
        return {"id": None, "type": "pret", "nom": version.NOM, "version": version.VERSION,
                "protocole": PROTOCOLE, "pid": os.getpid(),
                "python": platform.python_version(), "frozen": GELE}

    # ----------------------------------------------------------- boucle principale
    def boucle(self) -> None:
        self.emettre(self.evenement_pret())
        # Compteurs d'activité restés en attente (hors-ligne la dernière fois) : envoyés
        # quelques secondes après le démarrage, en arrière-plan. Sans licence : rien ne part.
        commandes.lancer_envoi_activite(delai_s=5.0)
        while True:
            try:
                ligne = self._lire_ligne()
            except (OSError, ValueError):
                ligne = None
            if ligne is None:            # fin de l'entrée : l'interface est partie
                break
            if isinstance(ligne, tuple) and ligne[0] is _TROP_GROS:
                self.erreur(self._id_lisible(ligne[1]), "TROP_GROS",
                            f"Requête trop grosse (plus de {TAILLE_MAX_LIGNE // (1024 * 1024)} Mo).")
                continue
            try:
                self.traiter_ligne(ligne)
            except Exception as e:      # filet de sécurité : la boucle ne doit JAMAIS mourir
                self.journal("stderr", traceback.format_exc(), "erreur", id_req=None)
                self.erreur(None, "ERREUR_INTERNE", str(e) or e.__class__.__name__)
        # EOF : même arrêt que « quitter », mais sans réponse (personne n'écoute).
        # Si un « quitter » a déjà lancé l'arrêt, arreter() ATTEND ici sa fin (os._exit) :
        # surtout ne pas laisser main() se terminer, Python tuerait la tâche en plein ménage.
        self.arreter(DELAI_ARRET_S, None)

    def _lire_ligne(self):
        donnees = CANAL_ENTREE.readline(TAILLE_MAX_LIGNE + 1)
        if not donnees:
            return None
        if len(donnees) > TAILLE_MAX_LIGNE and not donnees.endswith(b"\n"):
            debut = donnees[:400]        # pour retrouver l'id de la requête
            # On jette la suite de cette ligne géante, jusqu'au prochain « \n ».
            while True:
                suite = CANAL_ENTREE.readline(1024 * 1024)
                if not suite or suite.endswith(b"\n"):
                    break
            return (_TROP_GROS, debut)
        return donnees

    def _id_lisible(self, debut: bytes):
        """L'id lu au début d'une ligne illisible, pour que l'interface sache QUELLE requête
        a échoué (sinon une tâche longue, sans délai côté interface, attendrait pour toujours).
        None si on ne le trouve pas, ou s'il appartient à une requête EN COURS (on ne doit
        pas « terminer » cette dernière à sa place)."""
        m = _ID_EN_TETE.match(debut or b"")
        if not m:
            return None
        try:
            rid = m.group(1).decode("utf-8")
        except UnicodeDecodeError:
            return None
        with self._verrou:
            return None if rid in self.en_cours else rid

    def traiter_ligne(self, donnees: bytes) -> None:
        brut = donnees.strip()
        if not brut:
            return                       # ligne vide : ignorée
        try:
            # utf-8-sig : accepte un BOM UTF-8 en début de ligne (certains outils Windows en ajoutent un).
            req = json.loads(brut.decode("utf-8-sig"), parse_constant=_refuser_constante)
        except (UnicodeDecodeError, ValueError):
            self.erreur(self._id_lisible(brut[:400]), "JSON_INVALIDE",
                        "Ligne illisible (JSON invalide).")
            return
        if not isinstance(req, dict):
            self.erreur(None, "JSON_INVALIDE", "La requête doit être un objet JSON.")
            return
        rid = req.get("id")
        if not isinstance(rid, str) or not rid or len(rid) > 200:
            self.erreur(None, "ARGUMENTS_INVALIDES", "Champ « id » absent ou invalide.",
                        {"champ": "id"})
            return
        cmd = req.get("cmd")
        args = req.get("args")
        if args is None:
            args = {}
        if not isinstance(cmd, str) or not cmd:
            self.erreur(rid, "ARGUMENTS_INVALIDES", "Champ « cmd » absent ou invalide.",
                        {"champ": "cmd"})
            return
        if not isinstance(args, dict):
            self.erreur(rid, "ARGUMENTS_INVALIDES", "« args » doit être un objet.",
                        {"champ": "args"})
            return
        if self.arret:
            self.erreur(rid, "ARRET_EN_COURS", "Le moteur est en train de s'arrêter.")
            return

        if cmd in CONTROLE:
            # Même contrôle d'id que les autres commandes : un « ping » qui réutilise l'id
            # d'une conversion en cours recevrait sinon SON résultat sous cet id, et l'interface
            # croirait la conversion finie (deux événements finaux pour une même requête).
            with self._verrou:
                deja = rid in self.en_cours
            if deja:
                self.erreur(None, "ID_DUPLIQUE", f"L'id « {rid} » est déjà en cours.",
                            {"id": rid, "cmd": cmd})
                return
            self._controle(rid, cmd, args)
            return

        entree = commandes.COMMANDES.get(cmd)
        if entree is None:
            self.erreur(rid, "COMMANDE_INCONNUE", f"Commande inconnue : {cmd}", {"cmd": cmd})
            return
        fonction, nature = entree

        with self._verrou:
            if rid in self.en_cours:
                # id null (et l'id fautif dans details) : sinon le client croirait
                # que la requête DÉJÀ en cours avec cet id vient d'échouer.
                self.erreur(None, "ID_DUPLIQUE", f"L'id « {rid} » est déjà en cours.",
                            {"id": rid, "cmd": cmd})
                return
            if nature == LONGUE:
                # Test ET armement SOUS VERROU, AVANT de lancer le fil : deux
                # requêtes très rapprochées -> l'une acceptée, l'autre OCCUPE
                # (comme self.occupe dans app_ctk.py).
                if self.tache is not None:
                    self.erreur(rid, "OCCUPE", "Une action est déjà en cours, patientez…",
                                {"tache": self.tache.id, "cmd": self.tache.cmd})
                    return
                if not (self.licence_ok or self.sans_licence):
                    self.erreur(rid, "LICENCE_REQUISE",
                                "Licence non vérifiée : appelez d'abord licence_statut.")
                    return
                tache = Tache(rid, cmd)
                self.tache = tache
            else:
                tache = None
            self.en_cours[rid] = cmd

        try:
            if tache is not None:
                th = threading.Thread(target=self._executer,
                                      args=(rid, cmd, fonction, args, tache),
                                      name=f"longue-{rid}", daemon=True)
                tache.thread = th
                th.start()
            elif nature == RESEAU:
                self.pool_reseau.submit(self._executer, rid, cmd, fonction, args, None)
            else:
                self.pool.submit(self._executer, rid, cmd, fonction, args, None)
        except Exception as e:
            # Fil impossible à créer (« can't start new thread »…) : on DÉFAIT la
            # réservation, sinon le moteur répondrait OCCUPE pour toujours.
            with self._verrou:
                self.en_cours.pop(rid, None)
                if tache is not None and self.tache is tache:
                    self.tache = None
            self.erreur(rid, "ERREUR_INTERNE", f"Impossible de lancer la commande : {e}")

    # ----------------------------------------------------------- exécution d'une commande
    def _executer(self, rid, cmd, fonction, args, tache) -> None:
        _local.id = rid
        final = None
        try:
            ctx = Contexte(self, rid, cmd, tache)
            try:
                data = fonction(ctx, args)
                final = {"id": rid, "type": "result", "data": {} if data is None else data}
            except ErreurCommande as e:
                final = {"id": rid, "type": "error", "code": e.code, "message": e.message,
                         "details": e.details}
            except BaseException as e:
                # BaseException : même un SystemExit lancé par une bibliothèque devient une
                # erreur propre (sinon : pas de réponse, et la place resterait prise).
                final = {"id": rid, "type": "error", "code": "ERREUR_INTERNE",
                         "message": str(e) or e.__class__.__name__, "details": None}
                self.journal("stderr", traceback.format_exc().rstrip(), "erreur")
            # Les morceaux de lignes restés en mémoire partent AVANT l'événement final.
            self.flux_stdout.vider()
            self.flux_stderr.vider()
        except BaseException:
            pass        # le ménage ci-dessous et l'événement final partent quand même
        finally:
            # On libère la place AVANT d'annoncer la fin : une interface qui relance
            # aussitôt une tâche ne doit pas recevoir OCCUPE. Dans un « finally » : la
            # place est TOUJOURS rendue, quoi qu'il arrive au-dessus.
            with self._verrou:
                self.en_cours.pop(rid, None)
                if tache is not None and self.tache is tache:
                    self.tache = None
            _local.id = None
            if final is None:
                final = {"id": rid, "type": "error", "code": "ERREUR_INTERNE",
                         "message": "Erreur inattendue dans le moteur.", "details": None}
            self.emettre(final)

    # ----------------------------------------------------------- commandes de contrôle
    def _controle(self, rid, cmd, args) -> None:
        if cmd == "ping":
            self.emettre({"id": rid, "type": "result", "data": {"pong": True}})
        elif cmd == "etat":
            t = self.tache
            info = None
            if t is not None:
                info = {"id": t.id, "cmd": t.cmd,
                        "depuis_s": round(time.monotonic() - t.debut, 1),
                        "annulation_demandee": t.annulee.is_set(),
                        "derniere_progression": t.derniere_progression}
            self.emettre({"id": rid, "type": "result",
                          "data": {"occupe": t is not None, "tache": info,
                                   "licence_ok": self.licence_ok}})
        elif cmd == "annuler":
            cible = args.get("cible")
            if not isinstance(cible, str) or not cible:
                self.erreur(rid, "ARGUMENTS_INVALIDES", "« cible » doit être l'id à annuler.",
                            {"champ": "cible"})
                return
            with self._verrou:
                t = self.tache
                if t is not None and t.id == cible:
                    if not t.annulee.is_set():
                        # Le journal part AVANT de lever le drapeau, sous l'id de la tâche :
                        # il arrive donc toujours avant son événement final (jamais après,
                        # ni avec id null si la tâche finit très vite).
                        self.journal("stdout", "⛔ Annulation demandée — arrêt de l'opération…",
                                     "arret", id_req=cible)
                    t.annulee.set()          # idempotent : deux annuler = pas de souci
                    etat = "annulation_demandee"
                elif cible in self.en_cours:
                    etat = "non_annulable"   # commande rapide : elle finit toute seule
                else:
                    etat = "deja_terminee"
            self.emettre({"id": rid, "type": "result", "data": {"etat": etat}})
        elif cmd == "quitter":
            delai = args.get("delai_s", DELAI_ARRET_S)
            if (not isinstance(delai, (int, float)) or isinstance(delai, bool)
                    or not math.isfinite(delai) or delai < 0):
                delai = DELAI_ARRET_S
            # Dans un fil à part : la boucle continue de lire et répond
            # ARRET_EN_COURS aux requêtes qui arriveraient entre-temps.
            with self._verrou:
                self.arret = True
            threading.Thread(target=self.arreter, args=(min(float(delai), 60.0), rid),
                             name="arret", daemon=True).start()

    # ----------------------------------------------------------- arrêt propre
    def arreter(self, delai: float, rid_reponse) -> None:
        """Arrêt propre, puis os._exit(0). Ne REVIENT JAMAIS.

        Deux appelants possibles : le fil « arret » (commande quitter) et le fil principal
        (fin de l'entrée). Le premier fait le travail ; le second ATTEND qu'il ait fini.
        Pourquoi ne pas simplement revenir ? Si le fil principal revenait, main() se
        terminerait et Python tuerait aussitôt les fils « daemon » : la tâche en cours
        (fichier .mp4 à moitié écrit laissé sur le disque) et le fil « arret » lui-même
        (pas de réponse à quitter)."""
        with self._verrou:
            deja = self._arret_lance
            self._arret_lance = True
            self.arret = True
            t = self.tache
        if deja:
            while True:                      # l'autre appelant finira par os._exit
                time.sleep(1)
        try:
            debut = time.monotonic()
            limite = debut + delai
            limite_critique = debut + max(delai, DELAI_CRITIQUE_S)
            terminee = True
            if t is not None:
                t.annulee.set()              # ffmpeg est tué en < 0,2 s par agent/conversion
                if t.thread is not None:
                    t.thread.join(delai)
                    terminee = not t.thread.is_alive()
            # On laisse aussi aux commandes rapides déjà lancées le temps de répondre
            # (dans la limite du délai) : utile quand on pilote le moteur à la main,
            # par ex.  echo {"id":"1","cmd":"info"} | python helpva_engine.py
            # Les commandes CRITIQUES (licence_activer…) ont droit à plus de temps : coupée
            # au milieu, une activation pourrait consommer le code sans écrire licence.key.
            while True:
                with self._verrou:
                    autres = [c for r, c in self.en_cours.items() if r != rid_reponse]
                if not autres:
                    break
                critique = any(c in commandes.CRITIQUES for c in autres)
                if time.monotonic() >= (limite_critique if critique else limite):
                    break
                time.sleep(0.05)
            if rid_reponse is not None:
                ligne = encoder({"id": rid_reponse, "type": "result",
                                 "data": {"ok": True, "tache_terminee": terminee}})
                # On écrit la réponse ET on quitte en GARDANT le verrou de sortie :
                # aucun autre fil ne peut commencer une ligne qui serait coupée en deux.
                with self._verrou_sortie:
                    self._ecrire(ligne)
                    os._exit(0)
        finally:
            # Quoi qu'il arrive au-dessus (même une erreur imprévue), le moteur s'arrête.
            # os._exit : on n'attend pas les commandes rapides restantes (une vérification
            # de licence hors-ligne peut durer ~40 s). Le Job Windows nettoie les enfants.
            os._exit(0)


_TROP_GROS = object()


def main() -> None:
    moteur = Moteur()
    sys.stdout = moteur.flux_stdout
    sys.stderr = moteur.flux_stderr
    # Plantage dur (erreur en C) : la trace part sur le VRAI stderr, que Tauri
    # garde à part pour le rapport de plantage.
    try:
        import faulthandler
        if sys.__stderr__ is not None:
            faulthandler.enable(file=sys.__stderr__, all_threads=True)
    except Exception:
        pass
    globals()["_JOB"] = _attacher_job_windows()
    # Ctrl+C dans la console qui a lancé le moteur (le pont de dev, par ex.) : on
    # l'IGNORE. Sinon KeyboardInterrupt couperait tout, sans annuler proprement la
    # conversion (fichier .mp4 à moitié écrit). Seuls « quitter » et la fin de
    # l'entrée (EOF) arrêtent le moteur, toujours proprement.
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        pass
    try:
        moteur.boucle()
    except BaseException:
        try:
            os.write(2, traceback.format_exc().encode("utf-8", "replace"))
        except Exception:
            pass
        os._exit(1)


if __name__ == "__main__":
    main()
