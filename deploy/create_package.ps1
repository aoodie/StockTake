$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot\.."
$out = Join-Path $root "stocktake-deploy.zip"
$stage = Join-Path $env:TEMP ("stocktake-deploy-" + [guid]::NewGuid().ToString())

if (Test-Path $out) {
    Remove-Item $out
}

New-Item -ItemType Directory -Force $stage | Out-Null
New-Item -ItemType Directory -Force (Join-Path $stage "backend") | Out-Null

Copy-Item -Recurse (Join-Path $root "backend\app") (Join-Path $stage "backend\app")
Copy-Item -Recurse (Join-Path $root "backend\static") (Join-Path $stage "backend\static")
Copy-Item -Recurse (Join-Path $root "backend\tests") (Join-Path $stage "backend\tests")
Copy-Item (Join-Path $root "backend\requirements.txt") (Join-Path $stage "backend\requirements.txt")
Copy-Item -Recurse (Join-Path $root "deploy") (Join-Path $stage "deploy")
Copy-Item (Join-Path $root "README.md") (Join-Path $stage "README.md")

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $out
Remove-Item -Recurse -Force $stage
Write-Host "Created $out"
