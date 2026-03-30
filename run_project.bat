@echo off
echo Starting CITRIS Flight Simulation...

REM --- Start Backend ---
echo Starting backend...
start cmd /k "cd /d C:\Main\Repository\CITRIS_Aviation_Comp && python -m uvicorn backend.app:app --reload"

REM --- Wait a bit so backend starts first ---
timeout /t 3 > nul

REM --- Start Frontend ---
echo Starting frontend...
start cmd /k "cd /d C:\Main\Repository\CITRIS_Aviation_Comp\frontend && npm start"

echo All services started.