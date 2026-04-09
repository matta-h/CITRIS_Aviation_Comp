@echo off
setlocal EnableExtensions EnableDelayedExpansion

title CITRIS Aviation Sim Setup
color 0A

REM ------------------------------------------------------------
REM CITRIS Aviation Sim - Windows setup / launch helper
REM Assumptions:
REM   - Repo root contains backend\ and frontend\
REM   - Backend runs with: python -m uvicorn backend.app:app --reload
REM   - Frontend uses npm start
REM ------------------------------------------------------------

cd /d "%~dp0"

echo.
echo ============================================================
echo   CITRIS Aviation Sim - Setup and Launch Script
echo ============================================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY_CMD=py"
    goto :python_ok
)

where python >nul 2>nul
if %errorlevel%==0 (
    set "PY_CMD=python"
    goto :python_ok
)

echo [ERROR] Python was not found on this system.
echo Install Python 3.11+ and check "Add Python to PATH" during install.
echo.
pause
exit /b 1

:python_ok
for /f "tokens=2 delims= " %%v in ('%PY_CMD% --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] Python detected: %PY_VER%

where npm >nul 2>nul
if not %errorlevel%==0 (
    echo [ERROR] npm was not found on this system.
    echo Install Node.js LTS from nodejs.org, then rerun this script.
    echo.
    pause
    exit /b 1
)
for /f "tokens=1,* delims=:" %%a in ('npm -v 2^>nul') do set "NPM_VER=%%a"
echo [OK] npm detected: %NPM_VER%

echo.
echo [1/7] Checking project folders...
if not exist "backend" (
    echo [ERROR] Could not find backend\ folder in:
    echo %cd%
    pause
    exit /b 1
)
if not exist "frontend" (
    echo [ERROR] Could not find frontend\ folder in:
    echo %cd%
    pause
    exit /b 1
)

echo [OK] Found backend\ and frontend\

echo.
echo [2/7] Creating backend virtual environment...
if not exist ".venv" (
    %PY_CMD% -m venv .venv
    if not %errorlevel%==0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [OK] Existing .venv found.
)

echo.
echo [3/7] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if not %errorlevel%==0 (
    echo [ERROR] Failed to activate .venv
    pause
    exit /b 1
)

echo.
echo [4/7] Upgrading pip / wheel / setuptools...
python -m pip install --upgrade pip setuptools wheel
if not %errorlevel%==0 (
    echo [WARN] pip upgrade had an issue, continuing anyway...
)

echo.
echo [5/7] Installing backend dependencies...
if exist "requirements.txt" (
    echo [INFO] Using root requirements.txt
    pip install -r requirements.txt
) else if exist "backend\requirements.txt" (
    echo [INFO] Using backend\requirements.txt
    pip install -r backend\requirements.txt
) else (
    echo [INFO] No requirements file found. Installing common backend packages.
    pip install fastapi uvicorn[standard] requests python-multipart pydantic numpy
)
if not %errorlevel%==0 (
    echo [ERROR] Backend dependency installation failed.
    pause
    exit /b 1
)

echo.
echo [6/7] Installing frontend dependencies...
pushd frontend
if exist "package-lock.json" (
    call npm install
) else (
    call npm install
)
if not %errorlevel%==0 (
    popd
    echo [ERROR] Frontend dependency installation failed.
    pause
    exit /b 1
)
popd

echo.
echo [7/7] Writing startup helper files...
>"run_backend_temp.bat" echo @echo off
>>"run_backend_temp.bat" echo cd /d "%cd%"
>>"run_backend_temp.bat" echo call ".venv\Scripts\activate.bat"
>>"run_backend_temp.bat" echo python -m uvicorn backend.app:app --reload

>"run_frontend_temp.bat" echo @echo off
>>"run_frontend_temp.bat" echo cd /d "%cd%\frontend"
>>"run_frontend_temp.bat" echo npm start

echo.
echo ============================================================
echo Setup complete.
echo.
echo Choose an option:
echo   [1] Start backend and frontend now
Echo   [2] Exit only
echo ============================================================
set /p CHOICE=Enter 1 or 2: 

if /I "%CHOICE%"=="1" goto :launch_all
if /I "%CHOICE%"=="2" goto :done

echo Invalid option. Exiting.
goto :done

:launch_all
echo.
echo Launching backend in a new window...
start "CITRIS Backend" cmd /k call "%cd%\run_backend_temp.bat"
timeout /t 3 >nul

echo Launching frontend in a new window...
start "CITRIS Frontend" cmd /k call "%cd%\run_frontend_temp.bat"

echo.
echo Backend should be at:  http://127.0.0.1:8000
echo Frontend should be at: http://localhost:3000
echo.
echo If the browser does not open automatically, open the frontend URL manually.
goto :done

:done
echo.
echo Finished.
pause
endlocal
