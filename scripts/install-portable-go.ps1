param(
  [string]$Version = "1.24.1"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$toolsDir = Join-Path $root ".dev\tools"
$goExe = Join-Path $toolsDir "go\bin\go.exe"
$zipPath = Join-Path $toolsDir "go$Version.windows-amd64.zip"
$url = "https://go.dev/dl/go$Version.windows-amd64.zip"

if (Test-Path -LiteralPath $goExe) {
  Write-Host "Portable Go already installed: $goExe"
  & $goExe version
  exit 0
}

New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

Write-Host "Downloading Go $Version from $url"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zipPath

Write-Host "Extracting Go to $toolsDir"
Expand-Archive -LiteralPath $zipPath -DestinationPath $toolsDir -Force

if (-not (Test-Path -LiteralPath $goExe)) {
  throw "Portable Go install failed: $goExe not found"
}

Write-Host "Portable Go installed: $goExe"
& $goExe version

