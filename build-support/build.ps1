param(
    [Parameter(Mandatory)] [string]$Version,
    [Parameter(Mandatory)] [int]$AndroidVersionCode,
    [string]$Origin = 'https://maxhub-ets2.web.app',
    [string]$PythonExe = 'python',
    [string]$JavaHome = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^(0|[1-9][0-9]{0,3})(\.(0|[1-9][0-9]{0,3})){2}$' -or $AndroidVersionCode -lt 8) {
    throw 'Use uma versão nova, como 0.4.3, e código Android igual ou superior a 8.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
function Run([string]$Tool, [string[]]$Arguments) {
    & $Tool @Arguments
    if ($LASTEXITCODE) { throw "Falha em $Tool." }
}
if (!$JavaHome) { $JavaHome = 'C:/Program Files/Android/Android Studio/jbr' }
if (!(Test-Path (Join-Path $JavaHome 'bin/javac.exe'))) { throw 'Informe JavaHome ou JAVA_HOME com JDK 17 ou superior.' }
Run $PythonExe @('-c', 'import sys; assert sys.version_info[:2] == (3,11), "Use Python 3.11."')
& "$PSScriptRoot/restore.ps1"
Run $PythonExe @('-m', 'pip', 'install', '-r', 'requirements-build.txt')
Run $PythonExe @('-m', 'unittest', 'discover', '-s', 'tests')
Run npm.cmd @('--prefix', 'sites/maxtrack-hub/functions', 'ci')
Run npm.cmd @('--prefix', 'sites/maxtrack-hub/functions', 'test')
$keys = Join-Path $root 'build/signing-restored'
$work = (New-Item -ItemType Directory -Force "build/portable-release/$Version").FullName
$config = Join-Path $work 'store-config.json'
$site = Join-Path $root 'sites/maxtrack-hub'
Run node @("$site/release.mjs", 'config', "$keys/maxhub-update.pem", "$keys/maxhub-license-public.pem", $Origin, $Version, $config)

# Build both native plugins with the local Visual Studio toolchain.
Run cmake @('-S', 'bridge', '-B', 'build/portable-bridge', '-A', 'x64')
Run cmake @('--build', 'build/portable-bridge', '--config', 'Release')
Run ctest @('--test-dir', 'build/portable-bridge', '-C', 'Release', '--output-on-failure')
Run cmake @('-S', 'build-support/telemetry', '-B', 'build/portable-telemetry', '-A', 'x64')
Run cmake @('--build', 'build/portable-telemetry', '--config', 'Release')
New-Item -ItemType Directory -Force 'dist/MaxHub/telemetry' | Out-Null
Copy-Item 'build/portable-telemetry/Release/MaxTrackHubTelemetry.dll' 'dist/MaxHub/telemetry/' -Force
Copy-Item 'vendor/scs_sdk/sdk_license.txt' 'dist/MaxHub/telemetry/' -Force

Run $PythonExe @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
    '--name', 'MaxTrackPro', '--icon', 'installer/MaxTrackPro.ico', '--collect-all', 'mediapipe',
    '--add-data', "$config;hub", '--distpath', "$work/track", 'maxtrack.py')
$track = Join-Path $work 'track/MaxTrackPro'
New-Item -ItemType Directory -Force "$track/bridge" | Out-Null
Copy-Item 'build/portable-bridge/Release/MaxTrackBridge.dll','vendor/scs_sdk/sdk_license.txt' "$track/bridge/" -Force
Run $PythonExe @('installer/collect_notices.py', "$track/THIRD_PARTY_NOTICES")
$selfTest = Join-Path $work 'maxtrack-self-test.json'
$boot = [Diagnostics.ProcessStartInfo]::new((Join-Path $track 'MaxTrackPro.exe'))
$boot.UseShellExecute = $false
$boot.CreateNoWindow = $true
$boot.ArgumentList.Add('--self-test')
$boot.ArgumentList.Add($selfTest)
$process = [Diagnostics.Process]::Start($boot)
if (!$process.WaitForExit(60000)) { $process.Kill(); throw 'Autoteste do MaxTrack excedeu o prazo.' }
if ($process.ExitCode -ne 0 -or !(Test-Path $selfTest) -or (Get-Content $selfTest -Raw | ConvertFrom-Json).status -ne 'passed') {
    throw 'O MaxTrack empacotado falhou no autoteste.'
}
Run $PythonExe @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'MaxHub',
    '--paths', '.', '--icon', 'installer/MaxTrackPro.ico', '--add-data', 'hub/web;hub/web',
    '--add-data', "$config;hub", '--distpath', $work, 'hub/desktop.py')
Run $PythonExe @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
    '--name', 'MaxTrackETS2Setup', '--distpath', $work, 'ets2_install.py')

$env:MAXGPS_ANDROID_STORE_PASSWORD = Get-Content "$keys/android-password.txt" -Raw
try {
    & './hub/build-android.ps1' -SdkRoot '' -JavaHome $JavaHome -OutputDirectory $work -KeyStore "$keys/maxgps.p12" -KeyAlias maxgps -VersionName $Version -VersionCode $AndroidVersionCode
} finally { Remove-Item Env:MAXGPS_ANDROID_STORE_PASSWORD -ErrorAction SilentlyContinue }
Run 'build/portable-inno/ISCC.exe' @('/DMaxHub', "/DHubVersion=$Version", "/DCommerceBuild=$work", "/DFreshTrackBuild=$track", "/O$work", '/Qp', 'installer/MaxTrackPro.iss')
Run node @("$site/release.mjs", 'stage', "$keys/maxhub-update.pem", $config, "$work/MaxHub-Setup.exe", "$work/MaxGPS-Android.apk", $site)

# Bundle the site and functions, including private APK, ready for the owner's deploy.
$deploy = (New-Item -ItemType Directory -Force "$work/deploy/maxtrack-hub").FullName
foreach ($name in 'public','functions') {
    & robocopy "$site/$name" "$deploy/$name" /E /XD node_modules .npm-cache /XF '.env*' .secret.local '*.log' /NFL /NDL /NJH /NJS
    if ($LASTEXITCODE -ge 8) { throw 'Falha ao montar o pacote de deploy.' }
}
Copy-Item "$site/firebase.json","$site/firestore.rules","$site/firestore.indexes.json","$site/README.md" $deploy -Force
@{projects=@{default='maxhub-ets2'}} | ConvertTo-Json | Set-Content "$deploy/.firebaserc" -Encoding ascii
@("STORE_ORIGIN=$Origin", 'MP_SANDBOX=false') | Set-Content "$deploy/functions/.env.maxhub-ets2" -Encoding ascii
Compress-Archive -Path "$work/deploy/*" -DestinationPath "$work/MaxHub-$Version-deploy.zip" -Force
Write-Output "Pacote para baixar e publicar: $work/MaxHub-$Version-deploy.zip"
