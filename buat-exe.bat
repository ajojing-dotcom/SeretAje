@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
python -m PyInstaller --noconfirm --onefile --noconsole --name SeretAje seretaje.py || (pause & exit /b 1)
echo.
echo Selesai. File ada di folder dist\SeretAje.exe
pause
