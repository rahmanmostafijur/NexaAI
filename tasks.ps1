<#
.SYNOPSIS
  NexaAI Agent developer commands for Windows (equivalent to the Makefile).
.EXAMPLE
  ./tasks.ps1 up
  ./tasks.ps1 test
#>
param([Parameter(Position = 0)][string]$Task = "help")

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Invoke-In([string]$Dir, [scriptblock]$Block) {
    Push-Location (Join-Path $Root $Dir)
    try { & $Block; if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
    finally { Pop-Location }
}

$tasks = [ordered]@{
    "up"            = { docker compose up --build -d }
    "down"          = { docker compose down }
    "logs"          = { docker compose logs -f backend }
    "install"       = { Invoke-In backend { uv sync }; Invoke-In frontend { npm ci } }
    "migrate"       = { Invoke-In backend { uv run alembic upgrade head } }
    "dev-backend"   = { Invoke-In backend { uv run uvicorn app.main:app --reload --port 8000 } }
    "dev-frontend"  = { Invoke-In frontend { npm run dev } }
    "dev"           = {
        docker compose up -d postgres
        & $tasks["migrate"]
        Start-Process powershell -ArgumentList "-NoExit", "-File", "$Root\tasks.ps1", "dev-backend"
        & $tasks["dev-frontend"]
    }
    "seed"          = { Invoke-In backend { uv run python -m scripts.seed } }
    "reseed"        = { Invoke-In backend { uv run python -m scripts.seed --reset } }
    "test-backend"  = { Invoke-In backend { uv run pytest } }
    "test-frontend" = { Invoke-In frontend { npm test } }
    "test"          = { & $tasks["test-backend"]; & $tasks["test-frontend"] }
    "coverage"      = { Invoke-In backend { uv run pytest --cov=app --cov-report=term-missing } }
    "lint"          = {
        Invoke-In backend { uv run ruff check .; uv run ruff format --check . }
        Invoke-In frontend { npm run lint; npm run typecheck }
    }
    "format"        = {
        Invoke-In backend { uv run ruff check --fix .; uv run ruff format . }
        Invoke-In frontend { npm run format }
    }
    "evaluate"      = {
        Invoke-In backend {
            uv run python evaluate_agent.py --mode offline
            uv run python evaluate_agent.py --mode offline --dataset holdout
        }
    }
    "evaluate-full" = { Invoke-In backend { uv run python evaluate_agent.py --mode full } }
}

if ($Task -eq "help" -or -not $tasks.Contains($Task)) {
    Write-Output "Usage: ./tasks.ps1 <task>"
    Write-Output ("Tasks: " + ($tasks.Keys -join ", "))
    exit 0
}
& $tasks[$Task]
