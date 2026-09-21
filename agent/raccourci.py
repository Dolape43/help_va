"""
Raccourci HelpVA sur le Bureau.

  - Windows : raccourci « HelpVA.lnk » vers l'exe (créé via WScript.Shell).
  - macOS   : lien « HelpVA.app » vers l'application.

Utilisé seulement par la version installée (exe / .app) : en développement,
`chemin_application()` renvoie None et rien n'est créé.
"""

import os
import subprocess
import sys
import tempfile

NOM = "HelpVA"


def chemin_application():
    """Chemin de l'application lancée (exe Windows ou bundle .app), None en dev."""
    if not getattr(sys, "frozen", False):
        return None
    exe = os.path.abspath(sys.executable)
    if sys.platform == "darwin":
        p = exe
        while p and p != os.path.dirname(p):
            if p.endswith(".app"):
                return p
            p = os.path.dirname(p)
        return None
    return exe


def dossier_bureau() -> str:
    """Vrai dossier du Bureau (suit la redirection OneDrive sous Windows)."""
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            # CSIDL_DESKTOPDIRECTORY = 0x10
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def chemin_raccourci(bureau: str = None) -> str:
    bureau = bureau or dossier_bureau()
    return os.path.join(bureau, NOM + (".lnk" if sys.platform == "win32" else ".app"))


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p)).rstrip("\\/")


def situation(app: str, bureau: str = None) -> str:
    """Où se trouve l'application ?
      - "sur_bureau"  : déjà sur le Bureau -> pas besoin de raccourci ;
      - "temporaire"  : lancée depuis un zip non extrait, l'image disque (.dmg)
                        ou la quarantaine macOS -> emplacement provisoire ;
      - "ok"          : emplacement normal.
    """
    bureau = bureau or dossier_bureau()
    if _norm(os.path.dirname(app)) == _norm(bureau):
        return "sur_bureau"
    p = os.path.abspath(app).replace("\\", "/").lower()
    tmp = os.path.abspath(tempfile.gettempdir()).replace("\\", "/").lower().rstrip("/")
    if p.startswith(tmp + "/") or "/apptranslocation/" in p:
        return "temporaire"
    if sys.platform == "darwin" and p.startswith("/volumes/"):
        # Image disque (.dmg) = volume en LECTURE SEULE -> provisoire.
        # Un disque externe (inscriptible) est un emplacement fixe.
        racine = "/".join(os.path.abspath(app).split("/")[:3])     # /Volumes/<nom>
        try:
            if os.statvfs(racine).f_flag & getattr(os, "ST_RDONLY", 1):
                return "temporaire"
        except Exception:
            return "temporaire"
    return "ok"


def _powershell() -> str:
    """Chemin COMPLET de PowerShell (jamais « powershell » tout court : un faux
    powershell.exe posé à côté de HelpVA pourrait être lancé à sa place)."""
    racine = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return os.path.join(racine, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


_SCRIPT_WIN = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try {
  $w = New-Object -ComObject WScript.Shell
  if ($env:HV_VERIF -eq '1') {
    foreach ($f in Get-ChildItem -LiteralPath $env:HV_BUREAU -Filter *.lnk -ErrorAction SilentlyContinue) {
      try { if ($w.CreateShortcut($f.FullName).TargetPath -ieq $env:HV_APP) { exit 3 } } catch {}
    }
  }
  $s = $w.CreateShortcut($env:HV_LIEN)
  $s.TargetPath = $env:HV_APP
  $s.WorkingDirectory = [System.IO.Path]::GetDirectoryName($env:HV_APP)
  $s.IconLocation = $env:HV_APP + ',0'
  $s.Description = 'HelpVA'
  $s.Save()
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""


def creer(app: str, bureau: str = None, verifier_existant: bool = False):
    """Crée (ou remplace) le raccourci vers `app`.

    verifier_existant=True : si un raccourci vers HelpVA existe déjà sur le
    Bureau (même sous un autre nom, ex. « HelpVA.exe - Raccourci »), on n'en
    crée pas un 2e.
    Renvoie (chemin, deja_present). Lève RuntimeError (message lisible) en cas d'échec.
    """
    bureau = bureau or dossier_bureau()
    lien = chemin_raccourci(bureau)
    if sys.platform == "win32":
        # Chemins passés par variables d'environnement : aucun souci de
        # guillemets / apostrophes / accents dans les noms de dossiers.
        env = dict(os.environ, HV_LIEN=lien, HV_APP=app, HV_BUREAU=bureau,
                   HV_VERIF="1" if verifier_existant else "0")
        try:
            r = subprocess.run(
                [_powershell(), "-NoProfile", "-NonInteractive", "-Command", _SCRIPT_WIN],
                env=env, capture_output=True, timeout=40,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        except subprocess.TimeoutExpired:
            raise RuntimeError("Windows n'a pas répondu à temps.")
        except OSError:
            raise RuntimeError("PowerShell est introuvable sur ce PC.")
        if r.returncode == 3:
            return lien, True
        if r.returncode != 0 or not os.path.exists(lien):
            lignes = [l.strip() for l in r.stderr.decode("utf-8", "replace").splitlines() if l.strip()]
            raise RuntimeError(lignes[0] if lignes else "Création du raccourci impossible.")
        return lien, False

    if sys.platform == "darwin":
        reel = os.path.realpath(app)
        if verifier_existant:
            try:
                for nom in os.listdir(bureau):
                    c = os.path.join(bureau, nom)
                    if os.path.islink(c) and os.path.realpath(c) == reel:
                        return c, True
            except OSError:
                pass
        if os.path.realpath(lien) == reel:
            raise RuntimeError("HelpVA est déjà sur le Bureau.")
        if os.path.islink(lien):
            os.remove(lien)
        elif os.path.exists(lien):
            raise RuntimeError("Un élément « HelpVA.app » existe déjà sur le Bureau.")
        try:
            os.symlink(app, lien)
        except OSError as e:
            raise RuntimeError(f"Accès au Bureau refusé ({e.strerror}).")
        return lien, False

    raise RuntimeError("Système non pris en charge.")


def a_faire(app: str, deja_cree: bool, cible_connue: str, bureau: str = None) -> str:
    """Décide quoi faire au lancement :
      "creer"    : 1er lancement, pas encore de raccourci ;
      "maj"      : notre raccourci existe mais l'app a été déplacée ;
      "sur_bureau" / "temporaire" : voir situation() ;
      ""         : rien (déjà fait, ou raccourci supprimé exprès par l'utilisateur).
    """
    s = situation(app, bureau)
    if s != "ok":
        return s
    existe = os.path.lexists(chemin_raccourci(bureau))
    if not deja_cree:
        return "" if existe else "creer"
    if existe and cible_connue and _norm(cible_connue) != _norm(app):
        return "maj"
    return ""
