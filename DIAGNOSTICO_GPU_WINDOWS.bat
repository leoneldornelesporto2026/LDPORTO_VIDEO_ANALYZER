@echo off
setlocal EnableExtensions
call "%~dp0scripts\windows\diagnostics\DIAGNOSTICO_GPU_WINDOWS.bat" %*
exit /b %errorlevel%
