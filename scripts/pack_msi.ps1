Param(
  [string]$Version = '0.1.0',
  [switch]$SignBinaries,
  [string]$CertThumbprint,
  [string]$CertPath,
  [string]$CertPassword,
  [string]$TimestampUrl = 'http://timestamp.digicert.com'
)
$ErrorActionPreference = 'Stop'

# Resolve paths
$scriptDir = if ($PSBoundParameters.ContainsKey('PSScriptRoot') -and $PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$root = (Resolve-Path (Join-Path $scriptDir '..')).Path
$dist = Join-Path $root 'dist'
$app  = Join-Path $dist 'PeachClient'
$installerDir = Join-Path $root 'installer'
$wxs = Join-Path $installerDir 'PeachClient.wxs'
$wixOut = Join-Path $dist 'msi'
New-Item -ItemType Directory -Path $wixOut -Force | Out-Null

# Check WiX tools
function Resolve-WiXTool {
  param([string]$exeName)
  $cmd = Get-Command $exeName -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $candidates = @(
    'C:\Program Files (x86)\WiX Toolset v3.14\bin',
    'C:\Program Files (x86)\WiX Toolset v3.11\bin',
    'C:\Program Files\WiX Toolset v3.14\bin',
    'C:\Program Files\WiX Toolset v3.11\bin'
  )
  foreach ($dir in $candidates) {
    $p = Join-Path $dir $exeName
    if (Test-Path $p) { return $p }
  }
  # Search Chocolatey install tree as a fallback
  $found = Get-ChildItem 'C:\ProgramData\chocolatey\lib\wixtoolset*' -Recurse -Include $exeName -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($found) { return $found.FullName }
  return $null
}

$heatPath = Resolve-WiXTool 'heat.exe'
$candlePath = Resolve-WiXTool 'candle.exe'
$lightPath = Resolve-WiXTool 'light.exe'
if (-not $heatPath -or -not $candlePath -or -not $lightPath) {
  throw "WiX Toolset not found. Ensure WiX v3.x is installed (heat.exe/candle.exe/light.exe)."
}

if (-not (Test-Path $app)) {
  throw "Missing app folder: $app. Build with PyInstaller first."
}

# 1) Harvest dist/PeachClient into a ComponentGroup PeachClientGroup
$harvestWxs = Join-Path $installerDir 'PeachClient.harvest.wxs'
& $heatPath dir $app -gg -sreg -srd -scom -sfrag -suid -dr INSTALLDIR -cg PeachClientGroup -var var.AppSource -out $harvestWxs | Write-Host

# 2) Compile
$defines = @('-dAppSource=' + $app, '-dVersion=' + $Version)
$wixobj1 = Join-Path $wixOut 'PeachClient.wixobj'
$wixobj2 = Join-Path $wixOut 'PeachClient.harvest.wixobj'
& $candlePath @defines -o $wixobj1 $wxs | Write-Host
& $candlePath @defines -o $wixobj2 $harvestWxs | Write-Host

# 3) Link
$msi = Join-Path $wixOut ("PeachClient-" + $Version + '.msi')
& $lightPath -o $msi $wixobj1 $wixobj2 -ext WixUIExtension | Write-Host

Write-Host "MSI built: $msi"

# 4) Optional signing of app binaries and MSI
function Invoke-SignFile {
  param([string]$PathToSign)
  $signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if (-not $signtool) { throw "signtool.exe not found in PATH (install Windows SDK)." }
  $args = @('sign','/fd','sha256','/tr', $TimestampUrl, '/td','sha256')
  if ($CertThumbprint) {
    $args += @('/sha1', $CertThumbprint)
  } elseif ($CertPath) {
    $args += @('/f', $CertPath)
    if ($CertPassword) { $args += @('/p', $CertPassword) }
  } else {
    throw 'Provide -CertThumbprint or -CertPath (with optional -CertPassword) to sign.'
  }
  $args += @($PathToSign)
  & $signtool.Source @args | Write-Host
}

if ($SignBinaries) {
  try {
    # Sign primary EXE if present
    $mainExe = Join-Path $app 'PeachClient.exe'
    if (Test-Path $mainExe) { Write-Host "Signing EXE: $mainExe"; Invoke-SignFile -PathToSign $mainExe }
    # Optionally sign DLLs in app directory (best effort)
    Get-ChildItem -Path $app -Recurse -Include *.dll -File -ErrorAction SilentlyContinue | ForEach-Object {
      Write-Host "Signing DLL: $($_.FullName)"
      Invoke-SignFile -PathToSign $_.FullName
    }
  } catch {
    Write-Warning "Binary signing failed: $($_.Exception.Message)"
  }
}

if ($CertThumbprint -or $CertPath) {
  try {
    Write-Host "Signing MSI: $msi"
    Invoke-SignFile -PathToSign $msi
  } catch {
    Write-Warning "MSI signing failed: $($_.Exception.Message)"
  }
}
