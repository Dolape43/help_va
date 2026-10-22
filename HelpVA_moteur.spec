# -*- mode: python ; coding: utf-8 -*-
# Moteur HelpVA (engine/helpva_engine.py) en UN SEUL .exe, pour la nouvelle interface Tauri.
# Tauri le lance comme « sidecar » et lui parle par stdin/stdout (voir desktop/src/engine/sidecar.ts).
#
#   pyinstaller HelpVA_moteur.spec      ->  dist\helpva-engine.exe
#   puis copie dans desktop\src-tauri\binaries\helpva-engine-x86_64-pc-windows-msvc.exe
#   (Tauri ajoute lui-même le suffixe de la plateforme).
#
# console=True : le plugin shell de Tauri lance le sidecar SANS fenêtre (CREATE_NO_WINDOW), et
# une appli console garde des stdin/stdout normaux (indispensables au protocole JSON-lines).
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets')]          # polices (agent/polices.py), logo
binaries = []
hiddenimports = [
    'commandes',
    'agent.horloge', 'agent.licence', 'agent.version', 'agent.emplacement', 'agent.config',
    'agent.parametres', 'agent.calendrier', 'agent.ranger', 'agent.unicite', 'agent.conversion',
    'agent.polices', 'agent.progression', 'agent.comptes', 'agent.activite',
    'requests', 'numpy', 'PIL',
]
#  - cryptography : vérification de la licence (Ed25519)
#  - imageio_ffmpeg : binaire ffmpeg (conversion MP4, métadonnées des vidéos)
#  - pillow_heif : photos iPhone (.heic/.heif)
for paquet in ('cryptography', 'imageio_ffmpeg', 'pillow_heif'):
    d, b, h = collect_all(paquet)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ['engine/helpva_engine.py'],
    pathex=['engine', '.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'customtkinter', 'matplotlib', 'IPython'],
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
    name='helpva-engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                    # UPX déclenche des faux positifs antivirus
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',
)
