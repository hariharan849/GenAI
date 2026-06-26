<#
.SYNOPSIS
    Build IDCardGenerator.exe with PyInstaller.

.PARAMETER Clean
    Delete dist\ and build\ before building.

.PARAMETER OpenOutput
    Open the output folder in Explorer after a successful build.

.EXAMPLE
    .\build.ps1              # incremental build
    .\build.ps1 -Clean       # full clean build
    .\build.ps1 -Clean -OpenOutput
#>
param(
    [switch]$Clean,
    [switch]$OpenOutput
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPy = ".\venv\Scripts\python.exe"

# ── pre-flight checks ─────────────────────────────────────────────────────────
if (-not (Test-Path $venvPy)) {
    Write-Error @"
Virtual environment not found.
Create it first:
  python -m venv venv
  .\venv\Scripts\pip install -r requirements.txt
"@
    exit 1
}

# ── optional clean ────────────────────────────────────────────────────────────
if ($Clean) {
    Write-Host "Cleaning previous build artifacts..." -ForegroundColor Yellow
    foreach ($dir in "dist", "build") {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir
            Write-Host "  Removed: $dir"
        }
    }
}

# ── ensure PyInstaller is present ─────────────────────────────────────────────
Write-Host "Checking PyInstaller..." -ForegroundColor Cyan
& $venvPy -m pip install --quiet --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Error "pip install pyinstaller failed"; exit 1 }

# ── run PyInstaller ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Building IDCardGenerator (this takes 1-3 minutes)..." -ForegroundColor Cyan
Write-Host ""

& $venvPy -m PyInstaller IDCardGenerator.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# ── report ────────────────────────────────────────────────────────────────────
$exePath   = "dist\IDCardGenerator\IDCardGenerator.exe"
$distDir   = "dist\IDCardGenerator"

if (-not (Test-Path $exePath)) {
    Write-Error "Build finished but executable not found at: $exePath"
    exit 1
}

$exeSizeMB   = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
$totalSizeMB = [math]::Round(
    (Get-ChildItem $distDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB, 0)

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host " Build successful!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  EXE   : $((Get-Item $exePath).FullName)"
Write-Host "  EXE size    : $exeSizeMB MB"
Write-Host "  Total folder: $totalSizeMB MB"
Write-Host ""
Write-Host "DISTRIBUTE the entire folder:" -ForegroundColor Cyan
Write-Host "  $((Get-Item $distDir).FullName)"
Write-Host ""
Write-Host "IMPORTANT - Tesseract OCR is NOT bundled." -ForegroundColor Yellow
Write-Host "  Target machines need it for OCR auto-detection (optional feature)."
Write-Host "  Installer: https://github.com/UB-Mannheim/tesseract/wiki"
Write-Host "  Default path expected: C:\Program Files\Tesseract-OCR\tesseract.exe"
Write-Host ""

if ($OpenOutput) {
    explorer $distDir
}
