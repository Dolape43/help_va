"""
Charge la police Poppins EMBARQUÉE pour l'application, sans l'installer sur le
PC de l'utilisateur (enregistrement au niveau du process courant).

Windows : AddFontResourceExW (GDI) avec le drapeau FR_PRIVATE.
macOS   : CTFontManagerRegisterFontsForURL (portée process).
Linux   : non géré (repli sur la police système).

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
    except Exception:
        return False
    return ok > 0
