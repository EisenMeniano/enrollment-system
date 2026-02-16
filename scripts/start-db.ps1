param(
    [switch]$ShowLogs
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed or not available in PATH."
    exit 1
}

docker compose up -d db
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose ps db
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($ShowLogs) {
    docker compose logs --tail 50 db
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
