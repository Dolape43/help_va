# -*- mode: python ; coding: utf-8 -*-
# Spec de build macOS -> produit HelpVA.app
# À lancer SUR UN MAC :  pyinstaller --noconfirm --clean HelpVA_mac.spec
from PyInstaller.utils.hooks import collect_all

datas = [
    ('assets', 'assets'),
]
binaries = []
hiddenimports = [
    'agent.horloge', 'agent.licence', 'agent.version', 'agent.emplacement',
    'agent.config', 'agent.parametres', 'agent.drive', 'agent.calendrier',
    'agent.ranger', 'agent.unicite', 'agent.conversion',
    'agent.polices', 'gdown',
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
    upx=False,                 # UPX déconseillé sur macOS
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,             # app fenêtrée (pas de terminal)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,          # None = arch du Mac qui build (mettre 'universal2' si voulu)
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.icns',
)

# Emballe l'exécutable dans un vrai bundle macOS .app
app = BUNDLE(
    exe,
    name='HelpVA.app',
    icon='assets/logo.icns',
    bundle_identifier='com.helpva.app',
    info_plist={
        'CFBundleName': 'HelpVA',
        'CFBundleDisplayName': 'HelpVA',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    },
)
