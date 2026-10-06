@echo off
setlocal EnableExtensions
REM Compatibility wrapper. Canonical implementation: scripts/windows/install/INSTALAR_WINDOWS.bat
call "%~dp0scripts\windows\install\INSTALAR_WINDOWS.bat" %*
exit /b %errorlevel%
