@echo off
setlocal EnableExtensions
call "%~dp0scripts\windows\diagnostics\DIAGNOSTICO_WINDOWS.bat" %*
exit /b %errorlevel%
