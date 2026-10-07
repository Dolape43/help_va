# -*- mode: python ; coding: utf-8 -*-
# Build Windows en MODE DOSSIER (onedir) -> dist\HelpVA\HelpVA.exe + dist\HelpVA\_internal\
# Ce dossier est ensuite emballé par Inno Setup (installer\HelpVA.iss) en un
# vrai installeur : tools\build_setup.ps1 fait les deux étapes.
# Pourquoi pas un seul .exe (onefile) : il se décompresse dans %TEMP% à chaque
# lancement -> démarrage plus lent et plus de fausses alertes antivirus.
import os
import re

from PyInstaller.utils.hooks import collect_all

# Version lue dans agent/version.py (un seul endroit à modifier).
with open(os.path.join(SPECPATH, 'agent', 'version.py'), encoding='utf-8') as f:
    VERSION = re.search(r'VERSION\s*=\s*"([^"]+)"', f.read()).group(1)
_v = tuple(int(x) for x in VERSION.split('.')) + (0,) * (4 - len(VERSION.split('.')))

# Fiche d'identité de l'exe (clic droit > Propriétés > Détails).
os.makedirs(os.path.join(SPECPATH, 'build'), exist_ok=True)
FICHE_VERSION = os.path.join(SPECPATH, 'build', 'version_info.txt')
with open(FICHE_VERSION, 'w', encoding='utf-8') as f:
    f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={_v}, prodvers={_v}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
      StringStruct('CompanyName', 'HelpVA'),
      StringStruct('FileDescription', 'HelpVA'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'HelpVA'),
      StringStruct('LegalCopyright', '© HelpVA'),
      StringStruct('OriginalFilename', 'HelpVA.exe'),
      StringStruct('ProductName', 'HelpVA'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])])
  ]
)
""")

# Données embarquées (accessibles via sys._MEIPASS = dist\HelpVA\_internal).
datas = [
    ('assets', 'assets'),        # logo.png / logo.ico
]
binaries = []
# Modules importés "à la demande" -> on les force.
hiddenimports = [
    'agent.horloge', 'agent.licence', 'agent.version', 'agent.emplacement',
    'agent.config', 'agent.parametres', 'agent.drive', 'agent.calendrier',
    'agent.ranger', 'agent.unicite', 'agent.conversion',
    'agent.polices', 'agent.progression', 'gdown',
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
    [],
    exclude_binaries=True,        # mode dossier : les DLL vont dans _internal\
    name='HelpVA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                    # UPX déclenche des faux positifs antivirus
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',
    version=FICHE_VERSION,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='HelpVA',
)
