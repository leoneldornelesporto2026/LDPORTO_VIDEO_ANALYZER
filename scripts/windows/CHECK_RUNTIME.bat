@echo off
setlocal EnableExtensions
set "PROJECT_ROOT=%~dp0..\.."
set "PY=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Ambiente ausente. Execute scripts\windows\install\INSTALAR_WINDOWS.bat.
  exit /b 1
)
"%PY%" -c "import sys; print('Selected executable:',sys.executable); print('Selected version:',sys.version.split()[0]); print('Venv:',sys.prefix); raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)"
if errorlevel 1 (
  echo Runtime oficial: Python 3.11.x. Nenhuma dependencia sera instalada no runtime incorreto.
  exit /b 1
)
exit /b 0