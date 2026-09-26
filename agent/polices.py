"""
Charge la police Poppins EMBARQUÉE pour l'application, sans l'installer sur le
PC de l'utilisateur (enregistrement au niveau du process courant).

Windows : AddFontResourceExW (GDI) avec le drapeau FR_PRIVATE.
macOS   : CTFontManagerRegisterFontsForURL (portée process).
Linux   : copie dans ~/.local/share/fonts/helpva (fontconfig) + fc-cache.

On appelle charger_poppins() AVANT de créer les widgets. Si ça échoue,
l'app retombe simplement sur sa police par défaut (aucun plantage).
"""

import os
import sys
import glob


def _dossier_polices() -> str:
    """Dossier assets/fonts, en dev comme en exe (PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "fonts")


def _charger_linux(ttfs) -> int:
    """Linux (Tk utilise fontconfig) : Poppins est copiée une fois dans le dossier
    de polices de l'utilisateur, puis le cache fontconfig est rafraîchi."""
    import shutil
    import subprocess
    dossier = os.path.join(os.environ.get("XDG_DATA_HOME") or
                           os.path.join(os.path.expanduser("~"), ".local", "share"),
                           "fonts", "helpva")
    os.makedirs(dossier, exist_ok=True)
    copiees = 0
    for t in ttfs:
        dest = os.path.join(dossier, os.path.basename(t))
        if not os.path.exists(dest) or os.path.getsize(dest) != os.path.getsize(t):
            shutil.copy2(t, dest)
            copiees += 1
    if copiees and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", dossier], capture_output=True, timeout=30)
    return len(ttfs)


def charger_poppins() -> bool:
    """Enregistre les .ttf Poppins pour le process. True si au moins une chargée."""
    ttfs = glob.glob(os.path.join(_dossier_polices(), "*.ttf"))
    if not ttfs:
        return False
    ok = 0
    try:
        if sys.platform == "win32":
            import ctypes
            FR_PRIVATE = 0x10
            for t in ttfs:
                if ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(t), FR_PRIVATE, 0):
                    ok += 1
        elif sys.platform == "darwin":
            import ctypes
            import ctypes.util
            cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
            ct = ctypes.CDLL(ctypes.util.find_library("CoreText"))
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
            ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
            ct.CTFontManagerRegisterFontsForURL.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
            for t in ttfs:
                b = t.encode("utf-8")
                url = cf.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)
                if url and ct.CTFontManagerRegisterFontsForURL(url, 1, None):  # 1 = process
                    ok += 1
        else:
            ok = _charger_linux(ttfs)
    except Exception:
        return False
    return ok > 0
