@echo off
setlocal EnableExtensions
REM Compatibility wrapper. Canonical implementation: scripts/windows/install/INSTALAR_AVANCADO_WINDOWS.bat
call "%~dp0scripts\windows\install\INSTALAR_AVANCADO_WINDOWS.bat" %*
exit /b %errorlevel%
