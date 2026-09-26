# -*- mode: python ; coding: utf-8 -*-
# Spec de build Linux -> produit dist/HelpVA (exécutable unique).
# À lancer SOUS LINUX (ou WSL) : le plus simple est  bash tools/build_linux.sh
# (qui emballe ensuite l'exécutable en AppImage).
from PyInstaller.utils.hooks import collect_all

datas = [
    ('assets', 'assets'),        # logo.png, icônes, polices Poppins
]
binaries = []
hiddenimports = [
    'agent.horloge', 'agent.licence', 'agent.version', 'agent.emplacement',
    'agent.config', 'agent.parametres', 'agent.drive', 'agent.calendrier',
    'agent.ranger', 'agent.unicite', 'agent.conversion',
    'agent.polices', 'gdown', 'PIL._tkinter_finder',
]

for paquet in ('customtkinter', 'cryptography', 'imageio_ffmpeg', 'gdown',
               'pillow_heif'):
    d, b, h = collect_all(paquet)
    datas += d
    binaries += b
    hiddenimports += h


a = Analysis(
    ['app_ctk.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HelpVA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX déconseillé : casse souvent les .so Linux
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
