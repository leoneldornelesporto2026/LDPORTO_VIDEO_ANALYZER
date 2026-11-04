@echo off
setlocal
cd /d "%~dp0\..\.."
if "%~1"=="" goto usage
if "%~2"=="" goto usage
if "%~3"=="" goto usage
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" scripts\dev\start_real_test_s11.py --package "%~1" --source "%~2" --output "%~3"
if errorlevel 1 (
  echo.
  echo TESTE BLOQUEADO. Verifique a causa exibida acima.
  exit /b 1
)
echo.
echo CANARIO GERADO. Assista ao MP4 e revise antes de aprovar e renderizar o lote.
exit /b 0
:usage
echo USO: TESTAR_FLUXO_REAL_WINDOWS.bat "SECOND_CURATION_READY.zip" "video_original.mp4" "C:\teste_s11"
echo Consulte docs\S9_S11_REAL_TEST.md
exit /b 2
