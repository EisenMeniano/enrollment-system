param(
    [switch]$SkipMigrate
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not available in PATH."
    exit 1
}

if (-not (Test-Path ".env")) {
    if (-not (Test-Path ".env.example")) {
        Write-Error "Missing both .env and .env.example in project root."
        exit 1
    }

    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Update DB_HOST if you are using shared Postgres."
}

$envValues = @{}
Get-Content ".env" | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
        return
    }

    $parts = $line -split "=", 2
    if ($parts.Count -eq 2) {
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        $envValues[$key] = $value
    }
}

$dbEngine = "sqlite"
if ($envValues.ContainsKey("DB_ENGINE")) {
    $dbEngine = $envValues["DB_ENGINE"].ToLower()
}
if ($dbEngine -eq "postgresql") {
    $dbEngine = "postgres"
}

if ($dbEngine -eq "postgres") {
    $dbHost = ""
    if ($envValues.ContainsKey("DB_HOST")) {
        $dbHost = $envValues["DB_HOST"]
    }

    if ([string]::IsNullOrWhiteSpace($dbHost) -or $dbHost -like "<*>") {
        Write-Error "DB_ENGINE=postgres but DB_HOST is not set to a real host in .env."
        exit 1
    }
}

if (-not $SkipMigrate) {
    python manage.py migrate
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

python manage.py runserver
exit $LASTEXITCODE
