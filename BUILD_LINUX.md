# Générer HelpVA pour Linux

> Comme pour le Mac, le build Linux **doit être fait sous Linux**
> (PyInstaller ne compile pas pour un autre système).
> Pas besoin d'un autre ordinateur : **WSL** (le Linux intégré à Windows) suffit.

Résultat : **`dist/HelpVA-x86_64.AppImage`**, un seul fichier qui fonctionne
sur la plupart des distributions (Ubuntu, Debian, Fedora, Linux Mint…).

## 1. Installer Linux dans Windows (une seule fois)

Dans un terminal **PowerShell en administrateur** :

```bash
wsl --install -d Ubuntu-22.04
```

Redémarrer si demandé, puis ouvrir **Ubuntu** depuis le menu Démarrer et
choisir un nom d'utilisateur + mot de passe.

💡 Ubuntu **22.04** (et non la plus récente) est un choix volontaire : un
programme compilé sur une distribution un peu ancienne marche aussi sur les
plus récentes, l'inverse n'est pas vrai.

## 2. Récupérer le projet dans Ubuntu

```bash
git clone https://github.com/Dolape43/help_va.git
cd help_va
```

(Évitez de builder directement dans `/mnt/c/...` : c'est beaucoup plus lent.)

## 3. Lancer le build

```bash
bash tools/build_linux.sh
```

Le script installe tout ce qu'il faut (Python, Tk, PyInstaller…), compile,
puis emballe l'exécutable en **AppImage**. Compter 5 à 10 minutes la première fois.

## 4. Tester

```bash
./dist/HelpVA-x86_64.AppImage
```

Sous Windows 11, la fenêtre de HelpVA s'ouvre directement (WSLg).

## 5. Distribuer

Envoyer `HelpVA-x86_64.AppImage`. Chez le client :

```bash
chmod +x HelpVA-x86_64.AppImage
./HelpVA-x86_64.AppImage
```

(ou clic droit → Propriétés → « Autoriser l'exécution », puis double-clic).
Si rien ne se passe : `sudo apt install libfuse2` (bibliothèque dont les
AppImage ont besoin sur certaines distributions récentes).

## Notes

- **Données** : `~/.local/share/HelpVA` (licence, paramètres, calendrier).
- **Police Poppins** : copiée au 1er lancement dans `~/.local/share/fonts/helpva`.
- **Licence** : liée à la machine (`/etc/machine-id`), comme sur Windows et Mac.
- **Ouvrir le dossier de sortie** : utilise `xdg-open` (gestionnaire de fichiers).
