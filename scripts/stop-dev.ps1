$ErrorActionPreference = "SilentlyContinue"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidFile = Join-Path $root ".dev\pids.json"

if (-not (Test-Path $pidFile)) {
  Write-Host "No dev PID file found."
  exit 0
}

$items = Get-Content -Raw -Path $pidFile | ConvertFrom-Json
if ($null -eq $items) {
  Write-Host "No dev processes recorded."
  exit 0
}
if ($items -isnot [array]) {
  $items = @($items)
}

function Stop-ProcessTree([int]$Pid) {
  $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $Pid }
  foreach ($child in $children) {
    Stop-ProcessTree ([int]$child.ProcessId)
  }
  Stop-Process -Id $Pid -Force
}

foreach ($item in $items) {
  if ($item.pid) {
    Stop-ProcessTree ([int]$item.pid)
    Write-Host "Stopped $($item.name) pid=$($item.pid)"
  }
}

Remove-Item -Path $pidFile -Force
Write-Host "AIHR dev services stopped."
