param(
  [ValidateSet("job", "recommend", "search", "chat", "intent", "interact", "talent", "props", "toolbox", "more")]
  [string]$Menu = "job",
  [int]$ChromeToolbarOffsetY = 40,
  [switch]$DryRun
)

$points = @{
  job = @(100, 170)
  recommend = @(105, 207)
  search = @(85, 240)
  chat = @(85, 273)
  intent = @(105, 338)
  interact = @(85, 405)
  talent = @(105, 470)
  props = @(85, 538)
  toolbox = @(100, 605)
  more = @(85, 671)
}

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class BossClickWin32 {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

  [DllImport("user32.dll")]
  public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

  [DllImport("user32.dll")]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int processId);

  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern int GetWindowTextLength(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();

  [DllImport("user32.dll")]
  public static extern bool ShowWindow(IntPtr hWnd, int command);

  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

  [DllImport("user32.dll")]
  public static extern bool SetCursorPos(int x, int y);

  [DllImport("user32.dll")]
  public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);

  public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
  }

  public static string GetTitle(IntPtr hWnd) {
    int len = GetWindowTextLength(hWnd);
    if (len <= 0) return "";
    var sb = new StringBuilder(len + 1);
    GetWindowText(hWnd, sb, sb.Capacity);
    return sb.ToString();
  }
}
"@

$bossWindow = $null
[BossClickWin32]::EnumWindows({
  param([IntPtr]$hWnd, [IntPtr]$lParam)
  if (-not [BossClickWin32]::IsWindowVisible($hWnd)) { return $true }
  $windowPid = 0
  [BossClickWin32]::GetWindowThreadProcessId($hWnd, [ref]$windowPid) | Out-Null
  $proc = Get-Process -Id $windowPid -ErrorAction SilentlyContinue
  if ($proc -and $proc.ProcessName -eq "chrome") {
    $title = [BossClickWin32]::GetTitle($hWnd)
    if ($title -match "BOSS|zhipin") {
      $script:bossWindow = [pscustomobject]@{ Process = $proc; Handle = $hWnd; Title = $title }
      return $false
    }
  }
  return $true
}, [IntPtr]::Zero) | Out-Null

if (-not $bossWindow) {
  throw "Chrome window not found. Open the BOSS tab first."
}

$rect = New-Object BossClickWin32+RECT
[BossClickWin32]::ShowWindow($bossWindow.Handle, 9) | Out-Null
[BossClickWin32]::SetForegroundWindow($bossWindow.Handle) | Out-Null
Start-Sleep -Milliseconds 300
[IntPtr]$foreground = [BossClickWin32]::GetForegroundWindow()
if ($foreground -ne $bossWindow.Handle) {
  throw "BOSS Chrome window is not foreground. Click the BOSS Chrome window once, then rerun this script."
}
[BossClickWin32]::GetWindowRect($bossWindow.Handle, [ref]$rect) | Out-Null
$point = $points[$Menu]
$x = $rect.Left + $point[0]
$y = $rect.Top + $ChromeToolbarOffsetY + $point[1]

# ponytail: coordinate fallback for BOSS pages that block DevTools/DOM reads; replace with DOM locators if the page becomes stable.
"window='$($bossWindow.Title)' menu='$Menu' click=($x,$y) toolbarOffsetY=$ChromeToolbarOffsetY"

if ($DryRun) {
  return
}

[BossClickWin32]::SetForegroundWindow($bossWindow.Handle) | Out-Null
Start-Sleep -Milliseconds 200
[BossClickWin32]::SetCursorPos($x, $y) | Out-Null
Start-Sleep -Milliseconds 100
[BossClickWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[BossClickWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
