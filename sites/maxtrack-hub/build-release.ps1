param(
    [Parameter(Mandatory)] [string]$Origin,
    [Parameter(Mandatory)] [string]$SigningKey,
    [Parameter(Mandatory)] [string]$LicensePublicKey,
    [string]$Version = '0.4.0',
    [int]$AndroidVersionCode = 7,
    [string]$Destination = $PSScriptRoot,
    [string]$PythonExe,
    [string]$Compiler,
    [string]$WorkDirectory,
    [string]$AndroidKeyStore,
    [string]$AndroidKeyAlias,
    [switch]$TestBuild,
    [switch]$WindowsOnly
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$key = (Resolve-Path -LiteralPath $SigningKey).Path
$licensePublic = (Resolve-Path -LiteralPath $LicensePublicKey).Path
$target = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
if ($TestBuild -and $target -eq $PSScriptRoot) {
    throw 'Informe um Destination separado para preparar uma versão de teste.'
}
if ($AndroidKeyStore) { $AndroidKeyStore = (Resolve-Path -LiteralPath $AndroidKeyStore).Path }
if (!$WindowsOnly -and !$TestBuild -and (!$AndroidKeyStore -or !$AndroidKeyAlias -or !$env:MAXGPS_ANDROID_STORE_PASSWORD)) {
    throw 'A release comercial exige a chave de assinatura Android, o alias e MAXGPS_ANDROID_STORE_PASSWORD.'
}
if ($Version -notmatch '^(0|[1-9][0-9]{0,3})(\.(0|[1-9][0-9]{0,3})){2}$' -or $AndroidVersionCode -lt 7) {
    throw 'Informe uma versão de três componentes e AndroidVersionCode igual ou superior a 7.'
}

function Invoke-ReleaseTool([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Falha em $Program (código $LASTEXITCODE)." }
}

Push-Location $root
try {
    if (!$Compiler) {
        $Compiler = @('build/inno-map-voice/ISCC.exe', 'vendor/inno/ISCC.exe') |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (!$Compiler) { throw 'Informe o caminho de ISCC.exe (Inno Setup).' }
    $Compiler = (Resolve-Path -LiteralPath $Compiler).Path
    if (!$PythonExe) {
        $runtime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
        $PythonExe = if (Test-Path -LiteralPath $runtime) { $runtime } else { '.build-venv/Scripts/python.exe' }
    }
    $PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
    $sitePackages = (Resolve-Path '.build-venv/Lib/site-packages').Path
    $paths = @(
        'dist/MaxTrackPro/MaxTrackPro.exe',
        'dist/installer-tools/MaxTrackETS2Setup.exe',
        'dist/MaxHub/telemetry/MaxTrackHubTelemetry.dll',
        'dist/MaxHub/map-tools/map-builder.zip',
        'dist/MaxHub/voice/piper.exe'
    )
    foreach ($path in $paths) {
        if (!(Test-Path -LiteralPath $path)) { throw "Arquivo exigido pela release ausente: $path." }
    }
    if (!$WorkDirectory) { $WorkDirectory = "build/commercial/$Version" }
    $work = (New-Item -ItemType Directory -Force $WorkDirectory).FullName
    $config = Join-Path $work 'store-config.json'
    $release = Join-Path $PSScriptRoot 'release.mjs'
    Invoke-ReleaseTool 'node' @($release, 'config', $key, $licensePublic, $Origin, $Version, $config)

    $previousHome = $env:PYTHONHOME
    $previousPath = $env:PYTHONPATH
    try {
        $env:PYTHONHOME = $null
        $env:PYTHONPATH = $sitePackages
        $assets = (Resolve-Path 'hub/web').Path + ';hub/web'
        $icon = (Resolve-Path 'installer/MaxTrackPro.ico').Path
        Invoke-ReleaseTool $PythonExe @('-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
            '--name', 'MaxHub', '--paths', '.', '--icon', $icon, '--add-data', $assets,
            '--add-data', ($config + ';hub'), '--distpath', $work, '--specpath', 'build',
            '--workpath', 'build/commercial/pyinstaller', 'hub/desktop.py')
        Invoke-ReleaseTool $PythonExe @('-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
            '--name', 'MaxTrackETS2Setup', '--distpath', $work, '--specpath', 'build',
            '--workpath', 'build/commercial/pyinstaller', 'ets2_install.py')

        $legacy = (Resolve-Path 'build/fps-package').Path
        $legacyPython = Join-Path $legacy 'python.exe'
        $internal = (Resolve-Path 'dist/MaxTrackPro/_internal').Path
        $stdlib = 'C:/Program Files/Android/Android Studio/plugins/android-ndk/resources/lldb/lib'
        $env:PYTHONHOME = $legacy
        $env:PYTHONPATH = "$stdlib;$internal;$sitePackages"
        Invoke-ReleaseTool $legacyPython @((Join-Path $root 'installer/patch_legacy_maxtrack.py'),
            (Join-Path $legacy 'MaxTrackPro-original.exe'), (Join-Path $work 'MaxTrackPro.exe'), $config)
    } finally {
        $env:PYTHONHOME = $previousHome
        $env:PYTHONPATH = $previousPath
    }

    if ($WindowsOnly) {
        $existingApk = Join-Path $PSScriptRoot 'functions/private/MaxGPS-Android.apk'
        Copy-Item -LiteralPath $existingApk -Destination (Join-Path $work 'MaxGPS-Android.apk')
    } else {
        $android = @{
            OutputDirectory = $work
            VersionName = $Version
            VersionCode = $AndroidVersionCode
            KeyStore = $AndroidKeyStore
            KeyAlias = $AndroidKeyAlias
        }
        & (Join-Path $root 'hub/build-android.ps1') @android
    }
    Invoke-ReleaseTool $Compiler @('/DMaxHub', "/DHubVersion=$Version", "/DCommerceBuild=$work",
        "/O$work", '/Qp', (Join-Path $root 'installer/MaxTrackPro.iss'))
    $exe = Join-Path $work 'MaxHub-Setup.exe'
    $apk = Join-Path $work 'MaxGPS-Android.apk'
    if ((Get-Item -LiteralPath $exe).VersionInfo.ProductVersion.Trim() -ne $Version) {
        throw 'A versão nos metadados do instalador não corresponde à versão da release.'
    }
    Invoke-ReleaseTool 'node' @($release, 'stage', $key, $config, $exe, $apk, $target)
} finally {
    Pop-Location
}
