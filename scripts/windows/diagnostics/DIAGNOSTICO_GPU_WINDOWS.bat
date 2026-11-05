@echo off
setlocal EnableExtensions
cd /d "%~dp0..\..\.."
call "%~dp0..\CHECK_RUNTIME.bat"
if errorlevel 1 exit /b 1
echo L.D.PORTO - Diagnostico CUDA sem carregar pesos
".venv\Scripts\python.exe" scripts\test_gpu.py --check-only %*
exit /b %errorlevel%
