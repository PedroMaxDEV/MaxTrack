@echo off
cd /d "%~dp0"
if not exist .build-venv\Scripts\python.exe py -3.11 -m venv .build-venv
if errorlevel 1 (echo Falha ao criar ambiente de compilacao.& pause & exit /b 1)
.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 (echo Falha ao preparar compilador.& pause & exit /b 1)
.build-venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 (echo Falha nos testes.& pause & exit /b 1)
.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name MaxTrackPro --collect-all mediapipe maxtrack.py
if errorlevel 1 (echo Falha na compilacao.& pause & exit /b 1)
.build-venv\Scripts\python.exe installer\collect_notices.py
if errorlevel 1 (echo Falha ao coletar avisos de licenca.& pause & exit /b 1)
echo EXE criado em dist\MaxTrackPro\MaxTrackPro.exe
echo A pasta inteira dist\MaxTrackPro deve acompanhar o executavel.
pause
