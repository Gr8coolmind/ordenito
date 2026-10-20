@echo off
rem Quita Ordenito de Windows. Con /todo borra tambien tus reglas e historial.
if /i "%1"=="/todo" (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar.ps1" -todo) else (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar.ps1")
if not "%ORDENITO_SIN_PAUSA%"=="1" pause
