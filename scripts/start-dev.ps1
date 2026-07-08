param(
  [switch]$NoAgent,
  [switch]$NoBrowser,
  [switch]$Window,
  [string]$Url = "http://localhost:3000/agent/dashboard?page=dashboard"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$agent = Join-Path $root "agent-service"

function Normalize-ProcessPathEnv() {
  $envs = [Environment]::GetEnvironmentVariables("Process")
  if ($envs.Contains("Path") -and $envs.Contains("PATH")) {
    $pathValue = [string]$envs["Path"]
    if ([string]::IsNullOrWhiteSpace($pathValue)) {
      $pathValue = [string]$envs["PATH"]
    }
    [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
    [Environment]::SetEnvironmentVariable("Path", $pathValue, "Process")
  }
}

Normalize-ProcessPathEnv

$projectGo = Join-Path $root ".dev\tools\go\bin\go.exe"
$go = $projectGo
if (-not (Test-Path $go)) {
  $go = Join-Path $env:TEMP "codex-go-1.24.1\go\bin\go.exe"
}
if (-not (Test-Path $go)) {
  $goCmd = Get-Command go -ErrorAction SilentlyContinue
  if ($goCmd) {
    $go = $goCmd.Source
  } else {
    throw "Go not found. Install Go, restore $go, or put portable Go at $projectGo"
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

function Test-PortListening([int]$Port) {
  [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

$started = @()

if (Test-PortListening 8080) {
  Write-Host "Backend already running on :8080"
} elseif ($Window) {
  Start-DevWindow "AIHR backend :8080" $backend "& `"$go`" run ."
} else {
  $started += Start-DevBackground "backend" $backend "& `"$go`" run ."
}

if (Test-PortListening 3000) {
  Write-Host "Frontend already running on :3000"
} elseif ($Window) {
  Start-DevWindow "AIHR frontend :3000" $frontend "& `"$npm`" run dev"
} else {
  $started += Start-DevBackground "frontend" $frontend "& `"$npm`" run dev"
}

if (-not $NoAgent) {
  if (Test-PortListening 8090) {
    Write-Host "Agent already running on :8090"
  } elseif ($Window) {
    Start-DevWindow "AIHR agent-service :8090" $agent "& `"$agentPython`" -m uvicorn app.main:app --host 127.0.0.1 --port 8090"
  } else {
    $started += Start-DevBackground "agent-service" $agent "& `"$agentPython`" -m uvicorn app.main:app --host 127.0.0.1 --port 8090"
  }
}

if (-not $Window -and $started.Count -gt 0) {
  $started | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 -Path (Join-Path $stateDir "pids.json")
}

if (-not $NoBrowser) {
  Start-Sleep -Seconds 3
  Start-Process $Url
}

Write-Host "Started AIHR dev services."
Write-Host "Backend:  http://127.0.0.1:8080"
Write-Host "Frontend: $Url"
if (-not $NoAgent) { Write-Host "Agent:    http://127.0.0.1:8090/health" }
if (-not $Window) {
  Write-Host "Logs:     $logDir"
  Write-Host "Stop:     powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1"
}



