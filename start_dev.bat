@echo off
echo Starting MTGO-DB Development Environment...

echo.
echo Starting Celery Worker...
start "Celery Worker" cmd /k "python local-dev/start_celery.py"

echo Starting Flower Monitor...
start "Flower Monitor" cmd /k "python local-dev/start_flower.py"

echo Starting Flask App...
start "Flask App" cmd /k "python app.py"

echo.
echo ========================================
echo Development servers are starting!
echo ========================================
echo Flask App:    http://localhost:8000
echo Flower:       http://localhost:5555
echo Task Monitor: http://localhost:8000/tasks
echo ========================================
echo.
echo Press any key to close this window...
pause > nul 