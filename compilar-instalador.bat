@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Compilando o instalador do DroidNote...
echo Isso pode levar varios minutos (backend + app + Setup).
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\build-windows.ps1"
if errorlevel 1 (
  echo.
  echo Compilacao falhou. Veja a mensagem acima.
  pause
  exit /b 1
)
echo.
echo Instalador pronto:
echo   %~dp0DroidNote-Setup.exe
echo.
echo Clique duas vezes nesse arquivo para instalar neste PC.
echo Depois use o atalho DroidNote na Area de Trabalho.
pause
