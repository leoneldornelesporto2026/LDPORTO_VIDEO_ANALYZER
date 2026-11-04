@echo off
setlocal EnableExtensions
cd /d "%~dp0..\..\.."
if errorlevel 1 exit /b 1
call "%~dp0..\CHECK_RUNTIME.bat"
if errorlevel 1 exit /b %errorlevel%

echo ================================================================
echo L.D.PORTO VIDEO ANALYZER - DIAGNOSTICO WINDOWS (SOMENTE LEITURA)
echo ================================================================
".venv\Scripts\python.exe" analyze.py --doctor --offline %*
set "DIAGNOSTIC_RESULT=%ERRORLEVEL%"
exit /b %DIAGNOSTIC_RESULT%
