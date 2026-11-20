param([switch]$ResourcesOnly)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
foreach ($name in 'hub-assets', 'android-tools', 'inno') {
    $archive = Join-Path $PSScriptRoot "resources/$name.zip"
    $hash = (Get-Content "$archive.sha256" -Raw).Trim()
    if ((Get-FileHash -LiteralPath $archive).Hash -ne $hash) { throw "Checksum inválido: $name. Execute git lfs pull." }
    Expand-Archive -LiteralPath $archive -DestinationPath $root -Force
}
if (!$ResourcesOnly) {
    $keys = Join-Path $root 'build/signing-restored'
    & node (Join-Path $PSScriptRoot 'signing.mjs') unpack (Join-Path $PSScriptRoot 'signing.enc') $keys
    if ($LASTEXITCODE) { throw 'Não foi possível abrir o pacote de assinatura.' }
}
