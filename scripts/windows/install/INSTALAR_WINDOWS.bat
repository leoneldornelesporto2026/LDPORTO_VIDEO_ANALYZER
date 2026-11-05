@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0..\..\.."
py -3.11 -c "import sys" >nul 2>&1
if errorlevel 1 goto :fallback
py -3.11 install.py --windows-tools
set "RESULT=%ERRORLEVEL%"
goto :finish
:fallback
python install.py --windows-tools
set "RESULT=%ERRORLEVEL%"
:finish
echo.
echo Confira o resultado acima. Runtime oficial: Python 3.11.x. Leia README.md.
pause
exit /b %RESULT%
