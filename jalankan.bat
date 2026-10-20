@echo off
cd /d "%~dp0"
where python >nul 2>nul || (
  echo Python belum terpasang. Unduh dari https://www.python.org/downloads/ lalu centang "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist ".siap" (
  echo Memasang kebutuhan, cukup sekali...
  python -m pip install -r requirements.txt || (pause & exit /b 1)
  python -m pip install pillow-heif >nul 2>nul
  echo ok> .siap
  python seretaje.py --buat-shortcut
)
start "" pythonw seretaje.py
