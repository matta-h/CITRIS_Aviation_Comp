@echo off
setlocal EnableDelayedExpansion

echo Starting CITRIS Flight Simulation...

REM --- Resolve project root from this BAT file's location ---
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

cd /d "%ROOT%"

REM --- Choose Python executable (prefer local venv) ---
set "PYTHON=python"
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
)

echo.
echo [1/4] Checking backend Python dependencies...
if exist "%ROOT%\requirements.txt" (
    "%PYTHON%" -m pip install -r "%ROOT%\requirements.txt"
    if errorlevel 1 (
        echo Failed to install backend dependencies from requirements.txt
        pause
        exit /b 1
    )
) else (
    echo No requirements.txt found in repo root.
)

echo.
echo [2/4] Checking frontend npm dependencies...
if not exist "%ROOT%\frontend\package.json" (
    echo frontend\package.json not found.
    pause
    exit /b 1
)

cd /d "%ROOT%\frontend"

if not exist "%ROOT%\frontend\node_modules" (
    echo node_modules not found. Running npm install...
    call npm install
    if errorlevel 1 (
        echo npm install failed.
        pause
        exit /b 1
    )
)

REM --- Ensure Turf is installed on the frontend ---
call npm list @turf/turf >nul 2>&1
if errorlevel 1 (
    echo @turf/turf is missing. Installing it now...
    call npm install @turf/turf
    if errorlevel 1 (
        echo Failed to install @turf/turf.
        pause
        exit /b 1
    )
) else (
    echo @turf/turf is already installed.
)

cd /d "%ROOT%"

echo.
echo [3/4] Starting backend...
start cmd /k "cd /d "%ROOT%" && "%PYTHON%" -m uvicorn backend.app:app --reload"

REM --- Wait a bit so backend starts first ---
timeout /t 3 > nul

echo.
echo [4/4] Starting frontend...
start cmd /k "cd /d "%ROOT%\frontend" && npm start"

echo.
echo All services started.
endlocal
