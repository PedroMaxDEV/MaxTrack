@echo off
setlocal
cd /d "%~dp0.."
py -3.11 -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || exit /b 1
pip install -r requirements-build.txt || exit /b 1
pyinstaller --noconfirm --clean --windowed --onedir --name MaxTrack --collect-all mediapipe --collect-all cv2 src\maxtrack.py || exit /b 1
echo Executavel: dist\MaxTrack\MaxTrack.exe
