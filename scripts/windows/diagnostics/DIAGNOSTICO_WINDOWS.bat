@echo off
setlocal EnableExtensions
cd /d "%~dp0..\..\.."
call "%~dp0..\CHECK_RUNTIME.bat"
if errorlevel 1 exit /b 1
echo L.D.PORTO - Diagnostico local offline
".venv\Scripts\python.exe" analyze.py --doctor --offline %*
exit /b %errorlevel%
