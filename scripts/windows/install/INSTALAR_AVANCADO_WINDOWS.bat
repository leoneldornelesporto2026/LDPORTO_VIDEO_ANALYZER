@echo off
cd /d "%~dp0..\..\.."
call "%~dp0..\CHECK_RUNTIME.bat"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR_WINDOWS.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" install.py --extras diarization,vision,ocr --download-vision-models --windows-tools --ollama
if errorlevel 1 (
  pause
  exit /b 1
)
where nvidia-smi >nul 2>&1
if not errorlevel 1 call CORRIGIR_GPU_WINDOWS.bat
call CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat