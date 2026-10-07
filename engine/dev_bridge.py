"""
Pont de DÉVELOPPEMENT : le moteur HelpVA accessible depuis un navigateur.

Pourquoi : Rust et les outils MSVC ne sont pas encore installés, donc
« tauri dev » ne marche pas. Pour développer l'interface React quand même
(npm run dev -> http://localhost:1420), ce petit serveur fait l'intermédiaire :

    navigateur (React)  --HTTP-->  dev_bridge.py  --stdin/stdout-->  helpva_engine.py
                        <--SSE---                 <---------------

    POST /cmd      envoie une requête {"id","cmd","args"} (réponse 202 immédiate)
    GET  /events   flux SSE : TOUS les événements du moteur (pret, progress, log, result…)
    GET  /health   état du pont et du moteur

Sécurité (même en dev, un serveur local est joignable par n'importe quelle page web) :
  - écoute UNIQUEMENT sur 127.0.0.1 ;
  - un JETON secret, affiché au démarrage et écrit dans engine/.dev_token (ignoré par git),
    est exigé partout (en-tête X-HelpVA-Token, ou ?token= pour EventSource qui ne
    sait pas envoyer d'en-tête) ;
  - CORS : seule l'origine http://localhost:1420 (Vite) est acceptée ;
  - l'en-tête Host doit être 127.0.0.1 ou localhost (protection « DNS rebinding »).

En plus, deux commandes propres au pont (en vrai, Tauri ouvrira ses fenêtres natives) :
  choisir_dossier  {"titre"?}                -> {"chemin": str|null}
  choisir_fichiers {"titre"?, "filtre"?}     -> {"chemins": [str]}
        filtre : "videos" | "images" | "medias" | "tous"

Données : par défaut, le moteur lancé par le pont travaille dans un dossier de TEST,
engine/.donnees_dev (ignoré par git) : APPDATA, USERPROFILE et HOME du moteur y pointent.
Ses paramètres, son calendrier, sa licence et son « Bureau » (dossier de sortie par
défaut) sont donc à part : on ne touche jamais aux vraies données (%APPDATA%\\HelpVA)
ni au vrai Bureau. Pour utiliser exprès le vrai profil : --vraies-donnees.

Lancement (depuis la racine du dépôt) :
    python engine/dev_bridge.py --sans-licence
Options : --port 8765   --sans-licence (dev : autorise les tâches sans licence)
          --donnees DOSSIER (défaut : engine/.donnees_dev)   --vraies-donnees
          --fichier-jeton CHEMIN
Arrêt : Ctrl+C (le moteur est arrêté proprement).
"""

import argparse
import hmac
import json
import os
import queue
import secrets
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ICI = os.path.dirname(os.path.abspath(__file__))
MOTEUR = os.path.join(ICI, "helpva_engine.py")
ORIGINE_AUTORISEE = "http://localhost:1420"
TAILLE_MAX = 16 * 1024 * 1024
COMMANDES_DU_PONT = ("choisir_dossier", "choisir_fichiers")

FILTRES = {
    "videos": [("Vidéos", "*.mov *.mp4 *.m4v *.avi *.mkv *.webm *.mpg *.mpeg *.wmv *.flv"),
               ("Tous", "*.*")],
    "images": [("Images", "*.jpg *.jpeg *.png *.webp *.heic *.heif *.bmp *.tif *.tiff"),
               ("Tous", "*.*")],
    "medias": [("Médias", "*.jpg *.jpeg *.png *.webp *.heic *.heif *.mp4 *.mov *.m4v *.avi *.mkv"),
               ("Tous", "*.*")],
    "tous": [("Tous", "*.*")],
}


def journal(texte: str) -> None:
    """Messages du pont pour le développeur (console)."""
    try:
        print(texte, flush=True)
    except UnicodeEncodeError:
        print(texte.encode("ascii", "replace").decode("ascii"), flush=True)


# ═══════════════════════════════════════════════════════════════════════════
#  Le moteur, vu du pont
# ═══════════════════════════════════════════════════════════════════════════
def environnement_isole(env: dict, donnees: str) -> dict:
    """Environnement du moteur avec un profil de TEST dans `donnees`.

    APPDATA   -> donnees\\AppData   (parametres.json, calendrier, licence.key…)
    USERPROFILE / HOME -> donnees\\Profil  (le « Bureau » : dossier de sortie par défaut)
    """
    appdata = os.path.join(donnees, "AppData")
    profil = os.path.join(donnees, "Profil")
    os.makedirs(appdata, exist_ok=True)
    os.makedirs(os.path.join(profil, "Desktop"), exist_ok=True)
    env = dict(env)
    env.update({"APPDATA": appdata, "USERPROFILE": profil, "HOME": profil,
                "XDG_DATA_HOME": appdata})
    return env


class Pont:
    def __init__(self, sans_licence: bool = False, donnees: str = None):
        env = dict(os.environ)
        if donnees is not None:
            env = environnement_isole(env, donnees)
        if sans_licence:
            env["HELPVA_MOTEUR_SANS_LICENCE"] = "1"
        # Groupe de processus À PART : un Ctrl+C dans cette console n'arrive qu'au pont,
        # qui arrête ensuite le moteur proprement (commande quitter). Sans ça, Windows
        # enverrait aussi Ctrl+C au moteur, coupé en pleine conversion.
        if sys.platform == "win32":
            separe = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            separe = {"start_new_session": True}
        self.proc = subprocess.Popen(
            [sys.executable, MOTEUR], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None,            # les plantages du moteur s'affichent dans cette console
            env=env, cwd=os.path.dirname(ICI), **separe)
        self._verrou_ecriture = threading.Lock()
        self._verrou_clients = threading.Lock()
        self.clients = set()        # une file (queue) par navigateur connecté à /events
        self.pret = None            # dernier événement « pret » (rejoué aux nouveaux clients)
        self._verrou_tk = threading.Lock()
        threading.Thread(target=self._lire_moteur, name="lecture-moteur", daemon=True).start()

    def vivant(self) -> bool:
        return self.proc.poll() is None

    def _lire_moteur(self) -> None:
        for brut in self.proc.stdout:
            try:
                ev = json.loads(brut.decode("utf-8"))
            except ValueError:
                journal(f"[pont] ligne illisible du moteur : {brut[:200]!r}")
                continue
            if ev.get("type") == "pret":
                self.pret = ev
                journal(f"[pont] moteur prêt (pid {ev.get('pid')}, protocole {ev.get('protocole')})")
            self.diffuser(ev)
        code = self.proc.wait()
        journal(f"[pont] le moteur s'est arrêté (code {code}).")
        self.diffuser({"id": None, "type": "moteur_arrete", "code": code})

    def diffuser(self, ev: dict) -> None:
        with self._verrou_clients:
            for f in list(self.clients):
                f.put(ev)

    def envoyer(self, req: dict) -> None:
        ligne = json.dumps(req, ensure_ascii=True, separators=(",", ":")) + "\n"
        with self._verrou_ecriture:
            self.proc.stdin.write(ligne.encode("ascii"))
            self.proc.stdin.flush()

    # ----------------------------------------------- fenêtres de choix (dev uniquement)
    def commande_du_pont(self, req: dict) -> None:
        threading.Thread(target=self._selecteur, args=(req,), daemon=True).start()

    def _selecteur(self, req: dict) -> None:
        rid, cmd, args = req["id"], req["cmd"], req.get("args") or {}
        try:
            titre = str(args.get("titre") or ("Choisir un dossier" if cmd == "choisir_dossier"
                                               else "Choisir des fichiers"))
            filtre = FILTRES.get(args.get("filtre") or "tous", FILTRES["tous"])
            with self._verrou_tk:          # une seule fenêtre à la fois
                import tkinter as tk
                from tkinter import filedialog
                racine = tk.Tk()
                racine.withdraw()
                racine.attributes("-topmost", True)   # devant le navigateur
                racine.update()
                try:
                    if cmd == "choisir_dossier":
                        d = filedialog.askdirectory(parent=racine, title=titre, mustexist=True)
                        data = {"chemin": os.path.normpath(d) if d else None}
                    else:
                        fs = filedialog.askopenfilenames(parent=racine, title=titre,
                                                         filetypes=filtre)
                        data = {"chemins": [os.path.normpath(str(f))
                                            for f in racine.tk.splitlist(fs)]}
                finally:
                    racine.destroy()
            self.diffuser({"id": rid, "type": "result", "data": data})
        except Exception as e:
            self.diffuser({"id": rid, "type": "error", "code": "ERREUR_INTERNE",
                           "message": f"Fenêtre de choix impossible : {e}", "details": None})

    def arreter(self) -> None:
        if self.vivant():
            try:
                self.envoyer({"id": "pont-quitter", "cmd": "quitter", "args": {"delai_s": 5}})
                # 35 s : le moteur attend jusqu'à 30 s une commande critique (licence_activer…).
                self.proc.wait(timeout=35)
            except Exception:
                pass
        if self.vivant():
            self.proc.kill()


# ═══════════════════════════════════════════════════════════════════════════
#  Le serveur HTTP
# ═══════════════════════════════════════════════════════════════════════════
def fabriquer_gestionnaire(pont: Pont, jeton: str, port_reel):
    class Gestionnaire(BaseHTTPRequestHandler):
        server_version = "HelpVA-dev-bridge"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):     # pas de journal HTTP bavard
            pass

        # ----------------------------------------------- outils
        def _cors(self) -> None:
            if self.headers.get("Origin") == ORIGINE_AUTORISEE:
                self.send_header("Access-Control-Allow-Origin", ORIGINE_AUTORISEE)
                self.send_header("Vary", "Origin")

        def _json(self, code: int, obj) -> None:
            corps = json.dumps(obj, ensure_ascii=True).encode("ascii")
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corps)

        def _refus(self, code: int, erreur: str, message: str) -> None:
            self._json(code, {"ok": False, "code": erreur, "message": message})

        def _controles(self, avec_jeton: bool = True) -> bool:
            """Host, Origin et jeton. Renvoie False (et répond) si refusé."""
            hotes = {f"127.0.0.1:{port_reel[0]}", f"localhost:{port_reel[0]}"}
            if self.headers.get("Host") not in hotes:
                self._refus(403, "NON_AUTORISE", "Hôte refusé.")
                return False
            origine = self.headers.get("Origin")
            if origine is not None and origine != ORIGINE_AUTORISEE:
                self._refus(403, "NON_AUTORISE", "Origine refusée.")
                return False
            if not avec_jeton:
                return True
            recu = self.headers.get("X-HelpVA-Token", "")
            if not recu:
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    recu = auth[7:]
            if not recu:
                recu = (parse_qs(urlsplit(self.path).query).get("token") or [""])[0]
            if not hmac.compare_digest(recu.encode("utf-8"), jeton.encode("utf-8")):
                self._refus(401, "NON_AUTORISE", "Jeton absent ou faux (voir engine/.dev_token).")
                return False
            return True

        # ----------------------------------------------- routes
        def do_OPTIONS(self):                   # « preflight » CORS du navigateur
            if not self._controles(avec_jeton=False):
                return
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-HelpVA-Token")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            chemin = urlsplit(self.path).path
            if not self._controles():
                return
            if chemin == "/health":
                self._json(200, {"ok": True, "moteur_vivant": pont.vivant(), "pret": pont.pret,
                                 "pid_moteur": pont.proc.pid})
            elif chemin == "/events":
                self._evenements()
            else:
                self._refus(404, "INTROUVABLE", "Route inconnue.")

        def do_POST(self):
            chemin = urlsplit(self.path).path
            if not self._controles():
                return
            if chemin != "/cmd":
                self._refus(404, "INTROUVABLE", "Route inconnue.")
                return
            try:
                taille = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                taille = -1
            if taille <= 0 or taille > TAILLE_MAX:
                self._refus(400, "TROP_GROS" if taille > TAILLE_MAX else "JSON_INVALIDE",
                            "Corps absent ou trop gros.")
                return
            try:
                req = json.loads(self.rfile.read(taille).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._refus(400, "JSON_INVALIDE", "JSON invalide.")
                return
            if (not isinstance(req, dict) or not isinstance(req.get("id"), str)
                    or not isinstance(req.get("cmd"), str)
                    or not isinstance(req.get("args", {}), (dict, type(None)))):
                self._refus(400, "ARGUMENTS_INVALIDES", "Attendu : {id: str, cmd: str, args: {}}.")
                return
            if req["cmd"] in COMMANDES_DU_PONT:
                pont.commande_du_pont(req)
                self._json(202, {"ok": True, "id": req["id"]})
                return
            if not pont.vivant():
                self._refus(503, "MOTEUR_ARRETE", "Le moteur est arrêté : relancez le pont.")
                return
            try:
                pont.envoyer({"id": req["id"], "cmd": req["cmd"], "args": req.get("args") or {}})
            except OSError:
                self._refus(503, "MOTEUR_ARRETE", "Le moteur ne répond plus.")
                return
            self._json(202, {"ok": True, "id": req["id"]})

        def _evenements(self) -> None:
            """Flux SSE : une ligne « data: <json> » par événement du moteur."""
            file = queue.Queue()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            with pont._verrou_clients:
                pont.clients.add(file)
            try:
                self.wfile.write(b"retry: 2000\n\n")
                if pont.pret is not None:            # le client arrive après « pret » : on le rejoue
                    file.put(pont.pret)
                self.wfile.flush()
                while True:
                    try:
                        ev = file.get(timeout=15)
                        donnees = json.dumps(ev, ensure_ascii=True, separators=(",", ":"))
                        self.wfile.write(b"data: " + donnees.encode("ascii") + b"\n\n")
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")    # garde la connexion ouverte
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                with pont._verrou_clients:
                    pont.clients.discard(file)
                self.close_connection = True

    return Gestionnaire


class Serveur(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # On saute socket.getfqdn() de HTTPServer : sous Windows, cette recherche
        # DNS inverse peut bloquer plusieurs secondes au démarrage.
        import socketserver
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


def main(argv=None) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Pont de développement HelpVA (HTTP + SSE).")
    p.add_argument("--port", type=int, default=8765, help="port (0 = un port libre au hasard)")
    p.add_argument("--fichier-jeton", default=os.path.join(ICI, ".dev_token"))
    p.add_argument("--sans-licence", action="store_true",
                   help="DEV : autorise les tâches longues sans licence activée")
    p.add_argument("--donnees", default=os.path.join(ICI, ".donnees_dev"),
                   help="dossier des données de TEST du moteur (défaut : engine/.donnees_dev)")
    p.add_argument("--vraies-donnees", action="store_true",
                   help="utiliser le VRAI profil (%%APPDATA%%\\HelpVA, vrai Bureau) : à vos risques")
    opts = p.parse_args(argv)

    donnees = None if opts.vraies_donnees else os.path.abspath(opts.donnees)
    jeton = secrets.token_urlsafe(24)
    port_reel = [opts.port]
    pont = Pont(sans_licence=opts.sans_licence, donnees=donnees)
    serveur = Serveur(("127.0.0.1", opts.port), fabriquer_gestionnaire(pont, jeton, port_reel))
    port_reel[0] = serveur.server_address[1]

    with open(opts.fichier_jeton, "w", encoding="utf-8") as f:
        f.write(jeton)
    journal(f"[pont] HelpVA dev bridge : http://127.0.0.1:{port_reel[0]}")
    journal(f"[pont] jeton : {jeton}   (aussi dans {opts.fichier_jeton})")
    if donnees is None:
        journal("[pont] ⚠️ DONNÉES RÉELLES : %APPDATA%\\HelpVA et le vrai Bureau (--vraies-donnees)")
    else:
        journal(f"[pont] données de TEST : {donnees}")
        journal(f"[pont]   (sortie par défaut : {os.path.join(donnees, 'Profil', 'Desktop', 'HelpVA')})")
    journal(f"[pont] origine autorisée : {ORIGINE_AUTORISEE}   —   Ctrl+C pour arrêter")

    def fermer(*_):
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, fermer)
    except Exception:
        pass
    try:
        serveur.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        journal("[pont] arrêt…")
        serveur.server_close()
        pont.arreter()
        try:
            os.remove(opts.fichier_jeton)
        except OSError:
            pass


if __name__ == "__main__":
    main()
