@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title L.D.PORTO - DIAGNOSTICO GPU
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: .venv nao encontrada.
  pause
  exit /b 1
)
echo ================================================================
echo GPU NVIDIA
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free --format=csv,noheader
echo ================================================================
"%CD%\.venv\Scripts\python.exe" scripts\test_gpu.py --check-only
echo.
echo Para testar inferencia REAL do large-v3:
echo   .venv\Scripts\python.exe scripts\test_gpu.py --model large-v3
pause
