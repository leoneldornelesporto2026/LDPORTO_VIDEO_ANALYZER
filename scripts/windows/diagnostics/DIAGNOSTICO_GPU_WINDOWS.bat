@echo off
setlocal EnableExtensions
cd /d "%~dp0..\..\.."
if errorlevel 1 exit /b 1
call "%~dp0..\CHECK_RUNTIME.bat"
if errorlevel 1 exit /b %errorlevel%

echo ================================================================
echo L.D.PORTO VIDEO ANALYZER - DIAGNOSTICO GPU (SEM INFERENCIA)
echo ================================================================
".venv\Scripts\python.exe" scripts\test_gpu.py --check-only %*
set "DIAGNOSTIC_RESULT=%ERRORLEVEL%"
exit /b %DIAGNOSTIC_RESULT%
