@echo off
setlocal EnableExtensions
REM Compatibility wrapper. Canonical implementation: scripts/windows/testing/TESTAR_WINDOWS.bat
call "%~dp0scripts\windows\testing\TESTAR_WINDOWS.bat" %*
exit /b %errorlevel%
