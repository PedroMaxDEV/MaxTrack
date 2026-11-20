param(
    [string]$PythonExe = '.build-venv/Scripts/python.exe',
    [string]$Compiler = 'vendor/inno/ISCC.exe',
    [switch]$SkipInstaller
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$destination = Join-Path $PWD 'dist/MaxHub'
$telemetry = Join-Path $destination 'telemetry'
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $PWD 'build/zig-cache'
$env:ZIG_LOCAL_CACHE_DIR = $env:ZIG_GLOBAL_CACHE_DIR
New-Item -ItemType Directory -Force $telemetry | Out-Null
$dll = Join-Path $telemetry 'MaxTrackHubTelemetry.dll'
$gcc = Get-Command g++.exe -ErrorAction SilentlyContinue
if ($gcc -and (& $gcc.Source -dumpmachine) -match '^x86_64.*mingw') {
    & $gcc.Source -shared -O2 -std=c++17 -static -static-libgcc -static-libstdc++ -Ivendor/scs_sdk/include hub/telemetry.cpp -lws2_32 -o $dll
} else {
    $zig = 'vendor/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    & $zig c++ -shared -O2 -std=c++17 -Ivendor/scs_sdk/include hub/telemetry.cpp -lws2_32 -o $dll
}
if ($LASTEXITCODE) { throw 'Falha ao compilar a DLL de telemetria.' }
Copy-Item vendor/scs_sdk/sdk_license.txt $telemetry
$assets = (Resolve-Path 'hub/web').Path + ';hub/web'
& $PythonExe -m PyInstaller --noconfirm --onefile --windowed --name MaxHub --paths . --icon (Resolve-Path installer/MaxTrackPro.ico).Path --add-data $assets --distpath $destination --specpath build hub/desktop.py
if ($LASTEXITCODE) { throw 'Falha ao empacotar o Max Hub.' }
if (!$SkipInstaller) {
    if (!(Test-Path 'dist/MaxTrackPro/MaxTrackPro.exe') -or !(Test-Path 'dist/installer-tools/MaxTrackETS2Setup.exe')) {
        throw 'Gere também o MaxTrack Pro e o assistente MaxTrackETS2Setup antes de compilar o instalador completo.'
    }
    & $Compiler /DMaxHub /Qp (Resolve-Path 'installer/MaxTrackPro.iss').Path
    if ($LASTEXITCODE) { throw 'Falha ao gerar o instalador do Max Hub.' }
}
