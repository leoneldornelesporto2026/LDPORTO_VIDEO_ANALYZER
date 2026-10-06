@echo off
setlocal EnableExtensions
REM Compatibility wrapper. Canonical implementation: scripts/windows/ollama/CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat
call "%~dp0scripts\windows\ollama\CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat" %*
exit /b %errorlevel%
