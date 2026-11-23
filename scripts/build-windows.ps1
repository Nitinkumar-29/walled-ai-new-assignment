$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Venv = Join-Path $ProjectRoot ".desktop-venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the project virtual environment." }
}

& $Python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install desktop-app dependencies." }

& $Python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name WalledAI --paths $ProjectRoot `
    --add-data "desktop_app\guard.js;desktop_app" `
    --distpath (Join-Path $ProjectRoot "dist") `
    --workpath (Join-Path $ProjectRoot "build") `
    (Join-Path $ProjectRoot "desktop_app\main.py")
if ($LASTEXITCODE -ne 0) { throw "Could not package Walled AI." }

Write-Host "Built: $ProjectRoot\dist\WalledAI.exe"
