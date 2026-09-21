# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# Données embarquées dans l'exe (accessibles via sys._MEIPASS).
datas = [
    ('assets', 'assets'),        # logo.png / logo.ico
]
binaries = []
# Modules importés "à la demande" -> on les force.
hiddenimports = [
    'agent.horloge', 'agent.licence', 'agent.version', 'agent.emplacement',
    'agent.config', 'agent.parametres', 'agent.drive', 'agent.calendrier',
    'agent.ranger', 'agent.unicite', 'agent.conversion',
    'agent.polices', 'gdown',
]

# Paquets à embarquer entièrement :
#  - customtkinter : la nouvelle interface (thèmes/assets internes)
#  - cryptography : vérification de la licence (Ed25519)
#  - imageio_ffmpeg : binaire ffmpeg pour l'uniquisation vidéo
#  - gdown : téléchargement Google Drive (repli)
#  - pillow_heif : lecture des photos iPhone (.heic/.heif) -> binaires natifs
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',
)
