# Générer HelpVA pour macOS

> ⚠️ Le build Mac **doit être fait sur un Mac** (PyInstaller ne compile pas
> pour un autre OS). Windows ne peut pas produire le `.app`.

## 1. Préparer le Mac (une seule fois)
Installer Python 3.11 (python.org) puis, dans le Terminal, à la racine du projet :

```bash
python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller customtkinter cryptography imageio-ffmpeg \
    gdown selenium pillow pillow-heif numpy opencv-python requests
```

(Idéalement dans un environnement virtuel : `python3 -m venv venv && source venv/bin/activate`.)

## 2. Lancer le build
Toujours à la racine du projet (là où se trouve `HelpVA_mac.spec`) :

```bash
pyinstaller --noconfirm --clean HelpVA_mac.spec
```

Résultat : **`dist/HelpVA.app`** (l'application).

## 3. Tester
```bash
open dist/HelpVA.app
```
Au 1er lancement, macOS peut afficher « développeur non identifié » :
→ **clic droit sur l'app → Ouvrir → Ouvrir**. (voir signature ci-dessous)

## 4. Distribuer aux clients : créer un .dmg
```bash
hdiutil create -volname "HelpVA" -srcfolder dist/HelpVA.app -ov -format UDZO HelpVA.dmg
```
Tu envoies le `HelpVA.dmg` ; le client l'ouvre et glisse HelpVA dans Applications.

## 5. (Optionnel) Signer / notariser
Pour éviter l'avertissement Gatekeeper chez tes clients, il faut un compte
**Apple Developer (99 $/an)** puis :
```bash
codesign --deep --force --options runtime --sign "Developer ID Application: TON NOM (TEAMID)" dist/HelpVA.app
xcrun notarytool submit HelpVA.dmg --apple-id TON_EMAIL --team-id TEAMID --wait
xcrun stapler staple HelpVA.dmg
```
Sans ça, l'app marche quand même (clic droit → Ouvrir au 1er lancement).

## Notes
- Le code est déjà **multiplateforme** : l'empreinte licence utilise l'UUID
  matériel Apple, et les données vont dans `~/Library/Application Support/HelpVA`.
- Une licence est **liée à la machine** : l'empreinte d'un Mac est différente de
  celle d'un PC Windows (normal). Générer les licences Mac avec l'empreinte du Mac.
- Icône : si `assets/logo.png` ne suffit pas, générer `assets/logo.icns` et
  changer `icon=` dans `HelpVA_mac.spec`.
