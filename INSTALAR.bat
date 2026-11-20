@echo off
cd /d "%~dp0"
echo Instalando dependencias compativeis...
py -3.11 -m pip install -r requirements.txt
if errorlevel 1 (echo FALHA NA INSTALACAO & pause & exit /b 1)
py -3.11 -c "import mediapipe as mp; assert hasattr(mp, 'solutions'), 'MediaPipe sem solutions'; print('MediaPipe OK:',mp.__version__)"
if errorlevel 1 (echo ERRO MEDIAPIPE & pause & exit /b 1)
echo Instalacao concluida
pause
