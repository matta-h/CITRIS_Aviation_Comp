@echo off
cd /d "C:\Main\Repository\CITRIS_Aviation_Comp"
call ".venv\Scripts\activate.bat"
python -m uvicorn backend.app:app --reload
