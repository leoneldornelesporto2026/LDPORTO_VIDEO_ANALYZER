@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR_WINDOWS.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pytest src\tests -q
set "TEST_RESULT=%ERRORLEVEL%"
pause
exit /b %TEST_RESULT%
