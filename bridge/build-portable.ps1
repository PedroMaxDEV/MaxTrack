$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $PWD 'build\zig-cache'
$compiler = Join-Path $PWD 'vendor\toolchain\zig-windows-x86_64-0.13.0\zig.exe'
if (!(Test-Path $compiler)) { throw 'Compilador portátil ausente. Use CMake/Visual Studio ou extraia Zig 0.13.0 em vendor/toolchain.' }
New-Item -ItemType Directory -Force build/bridge | Out-Null
& $compiler c++ -shared -O2 -std=c++17 -Ivendor/scs_sdk/include bridge/bridge.cpp -lws2_32 -o build/bridge/MaxTrackBridge.dll
if ($LASTEXITCODE) { throw 'Falha ao compilar DLL' }
& $compiler c++ -O0 -std=c++17 -Ivendor/scs_sdk/include bridge/test_bridge.cpp -lws2_32 -o build/bridge/test_bridge.exe
if ($LASTEXITCODE) { throw 'Falha ao compilar teste' }
& ./build/bridge/test_bridge.exe
if ($LASTEXITCODE) { throw 'Falha no teste nativo' }
