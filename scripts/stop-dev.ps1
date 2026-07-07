param(
  [switch]$Infra,
  [switch]$Milvus
)

$ErrorActionPreference = "SilentlyContinue"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidFile = Join-Path $root ".dev\pids.json"

function Stop-ProcessTree([int]$Pid) {
  $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $Pid }
  foreach ($child in $children) {
    Stop-ProcessTree ([int]$child.ProcessId)
  }
  Stop-Process -Id $Pid -Force
}

function Stop-PortProcess([int]$Port) {
  $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($conn in $connections) {
    if ($conn.OwningProcess) {
      Stop-ProcessTree ([int]$conn.OwningProcess)
      Write-Host "Stopped process on port $Port pid=$($conn.OwningProcess)"
    }
  }
}

if (-not (Test-Path $pidFile)) {
  Write-Host "No dev PID file found."
} else {
  $items = Get-Content -Raw -Path $pidFile | ConvertFrom-Json
  if ($null -eq $items) {
    Write-Host "No dev processes recorded."
  } else {
    if ($items -isnot [array]) {
      $items = @($items)
    }

    foreach ($item in $items) {
      if ($item.pid) {
        Stop-ProcessTree ([int]$item.pid)
        Write-Host "Stopped $($item.name) pid=$($item.pid)"
      }
    }
  }

  Remove-Item -Path $pidFile -Force
}

Stop-PortProcess 8080
Stop-PortProcess 3000
Stop-PortProcess 8090

if ($Infra) {
  docker compose stop mysql
}

if ($Milvus) {
  docker compose -f docker-compose.milvus.yml stop
}

Write-Host "AIHR dev services stopped."
