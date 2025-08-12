Param(
  [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'

# Determine repo root relative to this script's directory (scripts\..)
$scriptDir = if ($PSBoundParameters.ContainsKey('PSScriptRoot') -and $PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$root = (Resolve-Path (Join-Path $scriptDir '..')).Path
Set-Location $root

# 1) Build (unless skipped)
if (-not $NoBuild) {
  Write-Host "Building with PyInstaller..."
  py -m PyInstaller -y PeachClient.spec
}

# 2) Prepare version and paths
$iss = Join-Path $root 'installer\PeachClient.iss'
$version = '0.0.0'
if (Test-Path $iss) {
  $m = Select-String -Path $iss -Pattern '^#define\s+MyAppVersion\s+"([^"]+)"' -AllMatches | Select-Object -First 1
  if ($m) { $version = $m.Matches[0].Groups[1].Value }
}
$distDir = Join-Path $root 'dist'
$appDir  = Join-Path $distDir 'PeachClient'
$zipOut  = Join-Path $distDir ("PeachClient-$version.zip")
$instOutDir = Join-Path $distDir 'installer'
New-Item -ItemType Directory -Path $instOutDir -Force | Out-Null

if (-not (Test-Path $appDir)) {
  throw "App directory not found: $appDir. Build step may have failed."
}

# 3) Create ZIP
if (Test-Path $zipOut) { Remove-Item -LiteralPath $zipOut -Force }
Write-Host "Creating ZIP: $zipOut"
Compress-Archive -Path (Join-Path $appDir '*') -DestinationPath $zipOut -Force

# 4) Build Installer via Inno Setup (if available)
$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue)
if ($iscc) {
  Write-Host "Building installer with Inno Setup..."
  & $iscc.Source $iss | Write-Host
  Write-Host "Installer output directory: $instOutDir"
} else {
  Write-Warning "Inno Setup 'iscc.exe' not found in PATH. Skipping installer. Install Inno Setup 6 and rerun."
}

Write-Host "Packaging complete."
