param(
  [switch]$NoAgent,
  [switch]$NoBrowser,
  [switch]$Window
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$agent = Join-Path $root "agent-service"

$go = Join-Path $env:TEMP "codex-go-1.24.1\go\bin\go.exe"
if (-not (Test-Path $go)) {
  $goCmd = Get-Command go -ErrorAction SilentlyContinue
  if ($goCmd) {
    $go = $goCmd.Source
  } else {
    throw "Go not found. Install Go or restore $go"
  }
}

$npm = (Get-Command npm -ErrorAction Stop).Source
$agentPython = Join-Path $agent ".venv\Scripts\python.exe"
if (-not $NoAgent -and -not (Test-Path $agentPython)) {
  throw "Agent Python venv not found: $agentPython"
}

$stateDir = Join-Path $root ".dev"
$logDir = Join-Path $stateDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$runId = Get-Date -Format "yyyyMMdd-HHmmss"

function Start-DevWindow([string]$Title, [string]$WorkDir, [string]$Command) {
  $quotedTitle = $Title.Replace('"', '\"')
  $quotedWorkDir = $WorkDir.Replace("'", "''")
  $fullCommand = "cd '$quotedWorkDir'; `$Host.UI.RawUI.WindowTitle = `"$quotedTitle`"; $Command"
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($fullCommand))
  Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded)
}

function Start-DevBackground([string]$Name, [string]$WorkDir, [string]$Command) {
  $quotedWorkDir = $WorkDir.Replace("'", "''")
  $fullCommand = "cd '$quotedWorkDir'; $Command"
  $stdout = Join-Path $logDir "$runId-$Name.out.log"
  $stderr = Join-Path $logDir "$runId-$Name.err.log"
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($fullCommand))
  $proc = Start-Process powershell.exe `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded) `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru
  [pscustomobject]@{ name = $Name; pid = $proc.Id; stdout = $stdout; stderr = $stderr }
}

$started = @()

if ($Window) {
  Start-DevWindow "AIHR backend :8080" $backend "& `"$go`" run ."
  Start-DevWindow "AIHR frontend :3000" $frontend "& `"$npm`" run dev"
} else {
  $started += Start-DevBackground "backend" $backend "& `"$go`" run ."
  $started += Start-DevBackground "frontend" $frontend "& `"$npm`" run dev"
}

if (-not $NoAgent) {
  if ($Window) {
    Start-DevWindow "AIHR agent-service :8090" $agent "& `"$agentPython`" -m uvicorn app.main:app --host 127.0.0.1 --port 8090"
  } else {
    $started += Start-DevBackground "agent-service" $agent "& `"$agentPython`" -m uvicorn app.main:app --host 127.0.0.1 --port 8090"
  }
}

if (-not $Window) {
  $started | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 -Path (Join-Path $stateDir "pids.json")
}

if (-not $NoBrowser) {
  Start-Sleep -Seconds 3
  Start-Process "http://localhost:3000/agent/login"
}

Write-Host "Started AIHR dev services."
Write-Host "Backend:  http://127.0.0.1:8080"
Write-Host "Frontend: http://localhost:3000/agent/login"
if (-not $NoAgent) { Write-Host "Agent:    http://127.0.0.1:8090/health" }
if (-not $Window) {
  Write-Host "Logs:     $logDir"
  Write-Host "Stop:     powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1"
}



