param(
  [switch]$NoAgent,
  [switch]$NoBrowser,
  [switch]$NoInfra,
  [switch]$WithMilvus,
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
$docker = $null
if (-not $NoInfra) {
  $docker = (Get-Command docker -ErrorAction Stop).Source
}

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

function Wait-ComposeServiceHealthy([string]$Service, [int]$TimeoutSeconds = 90) {
  Write-Host "Waiting for $Service to become healthy..."
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  while ((Get-Date) -lt $deadline) {
    $json = & $docker compose ps $Service --format json 2>$null
    if ($LASTEXITCODE -eq 0 -and $json) {
      $item = $json | ConvertFrom-Json
      if ($item.Health -eq "healthy") {
        Write-Host "$Service is healthy."
        return
      }
    }

    Start-Sleep -Seconds 2
  }

  & $docker compose ps $Service
  throw "Timed out waiting for $Service to become healthy."
}

function Wait-UrlReady([string]$Name, [string]$Url, [int]$TimeoutSeconds = 60) {
  Write-Host "Waiting for $Name..."
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  while ((Get-Date) -lt $deadline) {
    try {
      $res = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 500) {
        Write-Host "$Name is ready."
        return
      }
    } catch {
      if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -lt 500) {
        Write-Host "$Name is ready."
        return
      }
    }

    Start-Sleep -Seconds 2
  }

  throw "Timed out waiting for $Name at $Url. Check logs in $logDir"
}

if (-not $NoInfra) {
  & $docker compose up -d mysql
  Wait-ComposeServiceHealthy "mysql"
  if ($WithMilvus) {
    & $docker compose -f docker-compose.milvus.yml up -d
  }
}

$started = @()
$backendCommand = "& `"$go`" run ."
if ($WithMilvus) {
  $backendCommand = "`$env:MILVUS_DISABLED='false'; `$env:VECTOR_STORE_DISABLED='false'; `$env:MILVUS_REQUIRED='false'; & `"$go`" run ."
}

if ($Window) {
  Start-DevWindow "AIHR backend :8080" $backend $backendCommand
  Start-DevWindow "AIHR frontend :3000" $frontend "& `"$npm`" run dev"
} else {
  $started += Start-DevBackground "backend" $backend $backendCommand
  Wait-UrlReady "backend" "http://127.0.0.1:8080/api/login" 90

  $started += Start-DevBackground "frontend" $frontend "& `"$npm`" run dev"
  Wait-UrlReady "frontend" "http://127.0.0.1:3000/agent/login" 90
}

if (-not $NoAgent) {
  if ($Window) {
    Start-DevWindow "AIHR agent-service :8090" $agent "& `"$agentPython`" -m uvicorn app.main:app --host 127.0.0.1 --port 8090"
  } else {
    $started += Start-DevBackground "agent-service" $agent "& `"$agentPython`" -m uvicorn app.main:app --host 127.0.0.1 --port 8090"
    Wait-UrlReady "agent-service" "http://127.0.0.1:8090/health" 45
  }
}

if (-not $Window) {
  $started | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 -Path (Join-Path $stateDir "pids.json")
}

if (-not $NoBrowser) {
  Start-Process "http://localhost:3000/agent/login"
}

Write-Host "Started AIHR dev services."
Write-Host "Backend:  http://127.0.0.1:8080"
Write-Host "Frontend: http://localhost:3000/agent/login"
if (-not $NoAgent) { Write-Host "Agent:    http://127.0.0.1:8090/health" }
if ($WithMilvus) { Write-Host "Milvus:   127.0.0.1:19530" }
if (-not $Window) {
  Write-Host "Logs:     $logDir"
  Write-Host "Stop:     powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1"
}
