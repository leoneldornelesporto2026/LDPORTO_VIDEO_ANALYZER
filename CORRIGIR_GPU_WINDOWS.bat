@echo off
setlocal EnableExtensions
REM Compatibility wrapper. Canonical implementation: scripts/windows/gpu/CORRIGIR_GPU_WINDOWS.bat
call "%~dp0scripts\windows\gpu\CORRIGIR_GPU_WINDOWS.bat" %*
exit /b %errorlevel%
