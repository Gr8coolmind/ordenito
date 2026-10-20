@echo off
rem Instala Ordenito en Windows (doble clic o desde una terminal)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
if not "%ORDENITO_SIN_PAUSA%"=="1" pause
