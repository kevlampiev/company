# PowerShell wrapper mirroring Makefile targets, for Windows users without `make`.
# Usage: pwsh ./tasks.ps1 <task>
param(
    [Parameter(Position = 0)]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

function Invoke-InBackend {
    param([scriptblock]$Block)
    Push-Location (Join-Path $RepoRoot "backend")
    try { & $Block } finally { Pop-Location }
}

function Invoke-Help {
    Write-Host "tasks.ps1 - dev wrapper for AI Bot Manager"
    Write-Host ""
    Write-Host "Usage: pwsh ./tasks.ps1 <task>"
    Write-Host ""
    Write-Host "Tasks:"
    Write-Host "  install       sync host venv (backend/.venv with runtime + dev deps)"
    Write-Host "  init-env      write a fresh .env at repo root with random secrets"
    Write-Host "  test          run pytest (requires Docker daemon for testcontainers)"
    Write-Host "  test-cov      run pytest with coverage report"
    Write-Host "  lint          ruff check"
    Write-Host "  fmt           ruff format + ruff --fix"
    Write-Host "  typecheck     mypy on app/"
    Write-Host "  check         lint + typecheck + test (the before-push target)"
    Write-Host "  up            docker compose up -d --build"
    Write-Host "  down          docker compose down (volumes preserved)"
    Write-Host "  logs          docker compose logs -f"
    Write-Host "  ps            docker compose ps"
}

switch ($Task) {
    "help"      { Invoke-Help }
    "install"   { Invoke-InBackend { uv sync } }
    "init-env"  { Invoke-InBackend { uv run python -m scripts.init_env } }
    "test"      { Invoke-InBackend { uv run pytest tests/ -v } }
    "test-cov"  { Invoke-InBackend { uv run pytest tests/ --cov=app --cov-report=term-missing } }
    "lint"      { Invoke-InBackend { uv run ruff check . } }
    "fmt"       { Invoke-InBackend { uv run ruff format .; uv run ruff check --fix . } }
    "typecheck" { Invoke-InBackend { uv run mypy app/ } }
    "check" {
        & $PSCommandPath lint
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PSCommandPath typecheck
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PSCommandPath test-cov
    }
    "up"   { docker compose up -d --build }
    "down" { docker compose down }
    "logs" { docker compose logs -f }
    "ps"   { docker compose ps }
    default {
        Write-Host "unknown task: $Task" -ForegroundColor Red
        Invoke-Help
        exit 1
    }
}
