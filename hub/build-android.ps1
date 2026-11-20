param(
    [string]$SdkRoot = $env:ANDROID_HOME,
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$OutputDirectory = 'dist',
    [string]$KeyStore,
    [string]$KeyAlias,
    [string]$VersionName,
    [int]$VersionCode
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!$JavaHome) { $JavaHome = 'C:\Program Files\Android\Android Studio\jbr' }
if ($SdkRoot) {
    $platform = Join-Path $SdkRoot 'platforms/android-35/android.jar'
    $tools = Join-Path $SdkRoot 'build-tools/35.0.0'
} else {
    $platform = 'build/android-tools/platform/android-35/android.jar'
    $tools = 'build/android-tools/build-tools/android-15'
}
if (!(Test-Path $platform) -or !(Test-Path (Join-Path $tools 'aapt2.exe'))) {
    throw 'Instale Android Platform 35 e Build Tools 35.0.0 ou informe -SdkRoot.'
}
$env:JAVA_HOME = $JavaHome
$env:Path = (Join-Path $JavaHome 'bin') + ';' + $env:Path
$work = Join-Path $PWD 'build/max-gps-apk'
$classes = Join-Path $work 'classes'
$dex = Join-Path $work 'dex'
New-Item -ItemType Directory -Force $work,$classes,$dex,$OutputDirectory | Out-Null
$resources = Join-Path $work 'resources.zip'
$unsigned = Join-Path $work 'unsigned.apk'
$aligned = Join-Path $work 'aligned.apk'
$signed = Join-Path (Resolve-Path $OutputDirectory).Path 'MaxGPS-Android.apk'
$developmentKey = !$KeyStore
if ($developmentKey) {
    $KeyStore = Join-Path (Resolve-Path 'build').Path 'max-gps-development.p12'
    $KeyAlias = 'max-gps-dev'
} elseif (!(Test-Path -LiteralPath $KeyStore) -or !$KeyAlias -or !$env:MAXGPS_ANDROID_STORE_PASSWORD) {
    throw 'Informe KeyStore, KeyAlias e MAXGPS_ANDROID_STORE_PASSWORD para a versão comercial.'
}
function Invoke-Build([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program falhou com código $LASTEXITCODE." }
}
Invoke-Build (Join-Path $tools 'aapt2.exe') @('compile','--dir','hub/android/res','-o',$resources)
$versionArgs = @()
if ($VersionName -or $VersionCode) { $versionArgs += '--replace-version' }
if ($VersionName) { $versionArgs += @('--version-name', $VersionName) }
if ($VersionCode) { $versionArgs += @('--version-code', [string]$VersionCode) }
Invoke-Build (Join-Path $tools 'aapt2.exe') (@('link','-o',$unsigned,'--manifest','hub/android/AndroidManifest.xml','-I',$platform) + $versionArgs + $resources)
Get-ChildItem -LiteralPath $classes -Filter '*.class' -File -Recurse | Remove-Item
$sources = @(Get-ChildItem -Path 'hub/android/src' -Filter '*.java' -File -Recurse | ForEach-Object FullName)
Invoke-Build (Join-Path $JavaHome 'bin/javac.exe') (@('-encoding','UTF-8','--release','8','-classpath',$platform,'-d',$classes) + $sources)
$classFiles = @(Get-ChildItem -LiteralPath $classes -Filter '*.class' -File -Recurse | ForEach-Object FullName)
Invoke-Build (Join-Path $tools 'd8.bat') (@('--lib',$platform,'--min-api','26','--output',$dex) + $classFiles)
Push-Location $dex
try { Invoke-Build (Join-Path $JavaHome 'bin/jar.exe') @('uf',$unsigned,'classes.dex') }
finally { Pop-Location }
Invoke-Build (Join-Path $tools 'zipalign.exe') @('-f','-p','4',$unsigned,$aligned)
if ($developmentKey -and !(Test-Path -LiteralPath $KeyStore)) {
    Invoke-Build (Join-Path $JavaHome 'bin/keytool.exe') @('-genkeypair','-keystore',$KeyStore,'-storetype','PKCS12','-storepass','android','-keypass','android','-alias','max-gps-dev','-keyalg','RSA','-keysize','2048','-validity','3650','-dname','CN=Max GPS Development')
}
$storePassword = if ($developmentKey) { 'pass:android' } else { 'env:MAXGPS_ANDROID_STORE_PASSWORD' }
$keyPassword = if (!$developmentKey -and $env:MAXGPS_ANDROID_KEY_PASSWORD) {
    @('--key-pass', 'env:MAXGPS_ANDROID_KEY_PASSWORD')
} else { @('--key-pass', $storePassword) }
Invoke-Build (Join-Path $tools 'apksigner.bat') (@('sign','--ks',$KeyStore,'--ks-pass',$storePassword,'--ks-key-alias',$KeyAlias) + $keyPassword + @('--out',$signed,$aligned))
Invoke-Build (Join-Path $tools 'apksigner.bat') @('verify','--verbose',$signed)
Write-Output $signed
