$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$src = Join-Path $PSScriptRoot "WgcCapture.cpp"
$out = Join-Path $PSScriptRoot "wgc-capture.exe"
$obj = Join-Path $PSScriptRoot "WgcCapture.obj"
$sdkVersion = "10.0.26100.0"
$sdkRoot = "C:\Program Files (x86)\Windows Kits\10"
$vsDevCmd = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat"

if (-not (Test-Path $vsDevCmd)) {
  throw "VsDevCmd.bat not found: $vsDevCmd"
}

$includeArgs = @(
  "/I`"$sdkRoot\Include\$sdkVersion\cppwinrt`"",
  "/I`"$sdkRoot\Include\$sdkVersion\winrt`"",
  "/I`"$sdkRoot\Include\$sdkVersion\um`"",
  "/I`"$sdkRoot\Include\$sdkVersion\shared`"",
  "/I`"$sdkRoot\Include\$sdkVersion\ucrt`""
) -join " "

$libArgs = @(
  "/LIBPATH:`"$sdkRoot\Lib\$sdkVersion\um\x64`"",
  "/LIBPATH:`"$sdkRoot\Lib\$sdkVersion\ucrt\x64`""
) -join " "

Remove-Item -LiteralPath $out -Force -ErrorAction SilentlyContinue

$cmd = "`"$vsDevCmd`" -arch=x64 && cl /nologo /EHsc /std:c++20 /permissive- /utf-8 /DUNICODE /D_UNICODE $includeArgs `"$src`" /Fo:`"$obj`" /Fe:`"$out`" /link $libArgs d3d11.lib dxgi.lib windowsapp.lib runtimeobject.lib windowscodecs.lib ole32.lib user32.lib"
cmd.exe /c $cmd
if ($LASTEXITCODE -ne 0) {
  throw "Build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $out)) {
  throw "Build failed; output not found: $out"
}

Write-Host "Built $out"
