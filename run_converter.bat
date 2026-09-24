@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python no encontrado. Ejecuta setup.bat primero.
  pause
  exit /b 1
)

echo Doc2md activo. Se cerrara automaticamente tras 30 segundos sin ficheros nuevos.
".venv\Scripts\doc2md.exe"
