@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.11 install.py --windows-tools
  goto finish
)
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.12 install.py --windows-tools
  goto finish
)
python install.py --windows-tools
:finish
echo.
echo Confira o resultado acima. Leia LEIA_PRIMEIRO.md.
pause
