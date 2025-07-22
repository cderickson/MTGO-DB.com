#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start all MTGO-DB development services
.DESCRIPTION
    This script starts Flask app, Celery worker, and Flower monitor for MTGO-DB development
#>

Write-Host "🚀 Starting MTGO-DB Development Environment..." -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Gray

# Set environment variable for local development
$env:FLASK_ENV = "local"

try {
    # Start services in new windows
    Write-Host "📦 Starting Celery Worker..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList "local-dev/start_celery.py" -WindowStyle Normal
    Start-Sleep -Seconds 2

    Write-Host "🌸 Starting Flower Monitor..." -ForegroundColor Magenta
    Start-Process -FilePath "python" -ArgumentList "local-dev/start_flower.py" -WindowStyle Normal
    Start-Sleep -Seconds 2

    Write-Host "🌐 Starting Flask App..." -ForegroundColor Cyan
    Start-Process -FilePath "python" -ArgumentList "app.py" -WindowStyle Normal
    Start-Sleep -Seconds 3

    Write-Host ""
    Write-Host "=" * 50 -ForegroundColor Gray
    Write-Host "✅ All services started!" -ForegroundColor Green
    Write-Host "=" * 50 -ForegroundColor Gray
    Write-Host "🌐 Flask App:    http://localhost:8000" -ForegroundColor Cyan
    Write-Host "🌸 Flower:       http://localhost:5555" -ForegroundColor Magenta
    Write-Host "📊 Task Monitor: http://localhost:8000/tasks" -ForegroundColor Yellow
    Write-Host "=" * 50 -ForegroundColor Gray
    Write-Host ""
    Write-Host "💡 Each service is running in its own window." -ForegroundColor Blue
    Write-Host "💡 Close the individual windows to stop services." -ForegroundColor Blue
}
catch {
    Write-Host "❌ Error starting services: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") 