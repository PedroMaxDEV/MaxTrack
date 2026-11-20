@echo off
cd /d "%~dp0"
py -3.11 maxtrack.py
if errorlevel 1 echo ERRO: envie a mensagem acima e o arquivo maxtrack_diagnostico.log
pause
