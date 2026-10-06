@echo off
setlocal EnableExtensions
REM Compatibility wrapper. Canonical implementation: scripts/windows/diagnostics/DIAGNOSTICO_GPU_WINDOWS.bat
call "%~dp0scripts\windows\diagnostics\DIAGNOSTICO_GPU_WINDOWS.bat" %*
exit /b %errorlevel%
