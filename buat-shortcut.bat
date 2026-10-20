@echo off
cd /d "%~dp0"
if exist "dist\SeretAje.exe" (
  "dist\SeretAje.exe" --buat-shortcut
) else (
  python seretaje.py --buat-shortcut
)
pause
