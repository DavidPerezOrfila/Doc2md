@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python no esta instalado o no esta en PATH.
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)"
if errorlevel 1 (
  echo Se requiere Python 3.12 a 3.14.
  pause
  exit /b 1
)

python -m venv .venv
if errorlevel 1 (
  echo No se pudo crear el entorno virtual.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
  echo Fallo la instalacion del proyecto.
  pause
  exit /b 1
)

echo.
echo Instalacion completada. Ejecuta run_converter.bat.
pause
