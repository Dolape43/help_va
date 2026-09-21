# Générer HelpVA pour macOS

> ⚠️ Le build Mac **doit être fait sur un Mac** (PyInstaller ne compile pas
> pour un autre OS). Windows ne peut pas produire le `.app`.

## 0. Récupérer le projet sur le Mac
Le plus simple : cloner le dépôt (il contient déjà `config.py`, les `assets`, etc.) :

```bash
git clone https://github.com/Dolape43/help_va.git
cd help_va
```

(Alternative : copier tout le dossier du projet via une clé USB.)

## 1. Préparer le Mac (une seule fois)
Installer **Python 3.11** (python.org), puis à la racine du projet :

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller customtkinter cryptography imageio-ffmpeg \
    gdown pillow pillow-heif numpy requests
```

(Le `venv` isole les paquets — recommandé. Une fois activé, ton terminal affiche `(venv)`.)

### Vérifier que ça tourne avant de builder
```bash
python3 app_ctk.py
```
Si l'app s'ouvre, tu peux builder.

## 2. Lancer le build
Toujours à la racine (là où est `HelpVA_mac.spec`) :

```bash
pyinstaller --noconfirm --clean HelpVA_mac.spec
```

Résultat : **`dist/HelpVA.app`**.

## 3. Tester
```bash
open dist/HelpVA.app
```
Au 1er lancement, macOS peut afficher « développeur non identifié » →
**clic droit sur l'app → Ouvrir → Ouvrir** (voir signature ci-dessous).

## 4. Distribuer aux clients : créer un .dmg
```bash
hdiutil create -volname "HelpVA" -srcfolder dist/HelpVA.app -ov -format UDZO HelpVA.dmg
```
Tu envoies le `HelpVA.dmg` ; le client l'ouvre et glisse HelpVA dans Applications.

## 5. (Optionnel) Signer / notariser
Pour éviter l'avertissement Gatekeeper chez tes clients : compte
**Apple Developer (99 $/an)** puis :
```bash
codesign --deep --force --options runtime --sign "Developer ID Application: TON NOM (TEAMID)" dist/HelpVA.app
xcrun notarytool submit HelpVA.dmg --apple-id TON_EMAIL --team-id TEAMID --wait
xcrun stapler staple HelpVA.dmg
```
Sans ça, l'app marche quand même (clic droit → Ouvrir au 1er lancement).

## Notes
- Puce **Apple Silicon (M1/M2/M3…)** vs **Intel** : l'app produite correspond à
  l'architecture du Mac qui build. Pour un `.app` qui marche sur les deux, mettre
  `target_arch='universal2'` dans `HelpVA_mac.spec` (nécessite un Python universal2).
- Le code est **multiplateforme** : l'empreinte licence utilise l'UUID matériel
  Apple, et les données vont dans `~/Library/Application Support/HelpVA`.
- Une licence est **liée à la machine** : l'empreinte d'un Mac ≠ celle d'un PC.
  Chaque client active avec **son** code (l'empreinte est gérée automatiquement).
- Icône : `assets/logo.icns` (déjà fourni, utilisé par `HelpVA_mac.spec`).
- `config.py` est bien inclus (URL + clé anon Supabase) → l'activation par code
  fonctionne dans le `.app`.
