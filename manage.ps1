# Risk-Aware AI Platform - Docker Management Script
# PowerShell script for managing the platform

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('build', 'up', 'down', 'restart', 'logs', 'ps', 'clean', 'help')]
    [string]$Command = 'help'
)

$ProjectRoot = $PSScriptRoot
$DockerDir = Join-Path $ProjectRoot "docker"

function Show-Help {
    Write-Host "Risk-Aware AI Platform - Docker Management" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\manage.ps1 [command]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Green
    Write-Host "  build      Build all Docker images"
    Write-Host "  up         Start all services"
    Write-Host "  down       Stop all services"
    Write-Host "  restart    Restart all services"
    Write-Host "  logs       Show logs (follow mode)"
    Write-Host "  ps         Show running containers"
    Write-Host "  clean      Stop and remove all containers, volumes, and images"
    Write-Host "  help       Show this help message"
    Write-Host ""
}

function Build-Images {
    Write-Host "Building Docker images..." -ForegroundColor Cyan
    Set-Location $DockerDir
    docker-compose build --parallel
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Build completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "Build failed!" -ForegroundColor Red
        exit 1
    }
    Set-Location $ProjectRoot
}

function Start-Services {
    Write-Host "Starting services..." -ForegroundColor Cyan
    Set-Location $DockerDir
    docker-compose up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Services started successfully!" -ForegroundColor Green
        Write-Host ""
        docker-compose ps
    } else {
        Write-Host "Failed to start services!" -ForegroundColor Red
        exit 1
    }
    Set-Location $ProjectRoot
}

function Stop-Services {
    Write-Host "Stopping services..." -ForegroundColor Cyan
    Set-Location $DockerDir
    docker-compose down
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Services stopped successfully!" -ForegroundColor Green
    } else {
        Write-Host "Failed to stop services!" -ForegroundColor Red
        exit 1
    }
    Set-Location $ProjectRoot
}

function Restart-Services {
    Write-Host "Restarting services..." -ForegroundColor Cyan
    Stop-Services
    Start-Services
}

function Show-Logs {
    Write-Host "Showing logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    Set-Location $DockerDir
    docker-compose logs -f
    Set-Location $ProjectRoot
}

function Show-Status {
    Write-Host "Container Status:" -ForegroundColor Cyan
    Set-Location $DockerDir
    docker-compose ps
    Set-Location $ProjectRoot
}

function Clean-All {
    Write-Host "WARNING: This will remove all containers, volumes, and images!" -ForegroundColor Red
    $confirmation = Read-Host "Are you sure? (yes/no)"

    if ($confirmation -eq 'yes') {
        Write-Host "Cleaning up..." -ForegroundColor Cyan
        Set-Location $DockerDir
        docker-compose down -v --rmi all
        Write-Host "Cleanup completed!" -ForegroundColor Green
    } else {
        Write-Host "Cleanup cancelled." -ForegroundColor Yellow
    }
    Set-Location $ProjectRoot
}

# Main execution
switch ($Command) {
    'build'   { Build-Images }
    'up'      { Start-Services }
    'down'    { Stop-Services }
    'restart' { Restart-Services }
    'logs'    { Show-Logs }
    'ps'      { Show-Status }
    'clean'   { Clean-All }
    'help'    { Show-Help }
    default   { Show-Help }
}

