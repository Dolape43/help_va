# Construit l'installeur Windows de HelpVA : dist\HelpVA-Setup-<version>.exe
#
#   1) PyInstaller (mode dossier)  -> dist\HelpVA\
#   2) Inno Setup 7                 -> dist\HelpVA-Setup-<version>.exe
#
# Lancer depuis la racine du projet :
#   powershell -ExecutionPolicy Bypass -File tools\build_setup.ps1
#
# Prérequis : pip install -r requirements.txt pyinstaller
#             Inno Setup 7 (https://jrsoftware.org/isdl.php)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Version : un seul endroit, agent\version.py
$version = (Select-String -Path "agent\version.py" -Pattern 'VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "== HelpVA $version =="

# Inno Setup 7 : installé pour l'utilisateur ou pour tous
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 7 introuvable. Installez-le : https://jrsoftware.org/isdl.php" }

Write-Host "`n[1/2] Build PyInstaller (mode dossier)..."
pyinstaller --noconfirm --clean HelpVA.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué." }

Write-Host "`n[2/2] Installeur Inno Setup..."
& $iscc "/DAppVersion=$version" "installer\HelpVA.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup a échoué." }

Write-Host "`nOK : dist\HelpVA-Setup-$version.exe"
