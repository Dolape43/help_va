; ─────────────────────────────────────────────────────────────────────────────
; Installeur Windows de HelpVA (Inno Setup 7)
;
; Emballe le dossier dist\HelpVA\ (build PyInstaller en mode dossier) en un
; seul fichier : dist\HelpVA-Setup-<version>.exe
;
; Ne pas compiler à la main : lancer tools\build_setup.ps1, qui fait le build
; PyInstaller puis ce script, avec la version lue dans agent\version.py.
; ─────────────────────────────────────────────────────────────────────────────

#define AppNom   "HelpVA"
#define AppExe   "HelpVA.exe"
#define Source   "..\dist\HelpVA"

; Version passée par tools\build_setup.ps1 (/DAppVersion=1.0.0) ;
; à défaut, lue dans la fiche d'identité de l'exe.
#ifndef AppVersion
  #define AppVersion GetFileProductVersionString(Source + "\" + AppExe)
#endif

[Setup]
; Identifiant UNIQUE de HelpVA pour Windows : NE JAMAIS le changer.
; C'est lui qui fait qu'une nouvelle version remplace l'ancienne au lieu de
; s'installer à côté (et une seule ligne HelpVA dans Paramètres > Applications).
AppId={{FED2668C-B9DA-46D6-94F5-D1E091B5C2E2}
AppName={#AppNom}
AppVersion={#AppVersion}
AppVerName={#AppNom} {#AppVersion}
AppPublisher=HelpVA
; Ajouter AppPublisherURL / AppUpdatesURL seulement quand le domaine du site
; sera acheté : un lien vers un domaine libre pourrait être racheté par un tiers.
AppSupportURL=https://t.me/helpvaLicence
AppCopyright=© HelpVA
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppNom}
VersionInfoDescription=Installation de {#AppNom}

; Installeur 64 bits (HelpVA est une application 64 bits), Windows 10 minimum.
SetupArchitecture=x64
MinVersion=10.0

; Installation SANS droits administrateur par défaut (dans le profil de
; l'utilisateur : %LOCALAPPDATA%\Programs\HelpVA). L'installeur propose
; quand même « Installer pour tous les utilisateurs » (droits admin).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppNom}
DefaultGroupName={#AppNom}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes

; Si HelpVA est ouvert (verrou « HelpVA_Instance » posé par l'app),
; l'installeur et le désinstalleur demandent de le fermer d'abord.
; Global\ : détecte aussi HelpVA ouvert dans une autre session Windows.
AppMutex=HelpVA_Instance,Global\HelpVA_Instance

; Apparence : style moderne, clair ou sombre selon Windows.
WizardStyle=modern dynamic
DisableWelcomePage=no
WizardImageFile=assistant-202.png,assistant-336.png,assistant-430.png
WizardSmallImageFile=logo-58.png,logo-97.png,logo-124.png
; Mêmes images en mode sombre (sinon Inno Setup remet ses images par défaut).
WizardImageFileDynamicDark=assistant-202.png,assistant-336.png,assistant-430.png
WizardSmallImageFileDynamicDark=logo-58.png,logo-97.png,logo-124.png
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppNom}

; Windows en français -> français, en anglais -> anglais, sans question.
; Autre langue de Windows -> petite fenêtre « choisir la langue ».
ShowLanguageDialog=auto

; Fichier produit.
OutputDir=..\dist
OutputBaseFilename=HelpVA-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "french";  MessagesFile: "compiler:Languages\French.isl"; LicenseFile: "licence_fr.txt"
Name: "english"; MessagesFile: "compiler:Default.isl";          LicenseFile: "licence_en.txt"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Mise à jour : on repart d'un dossier _internal propre, pour ne pas garder
; de vieux fichiers d'une version précédente.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppNom}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppNom}";  Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppNom}}"; Flags: nowait postinstall skipifsilent

; Note : la désinstallation NE supprime PAS %APPDATA%\HelpVA (licence,
; paramètres, calendrier) : une réinstallation retrouve tout.
