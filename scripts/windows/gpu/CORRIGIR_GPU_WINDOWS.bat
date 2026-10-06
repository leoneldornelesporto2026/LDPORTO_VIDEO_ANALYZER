@echo off
setlocal EnableExtensions
cd /d "%~dp0..\..\.."
call "%~dp0..\CHECK_RUNTIME.bat"
if errorlevel 1 exit /b 1
title L.D.PORTO - REPARO GPU CUDA

echo ================================================================
echo L.D.PORTO VIDEO ANALYZER - REPARO GPU NVIDIA / FASTER-WHISPER
echo ================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo ERRO: .venv nao encontrada.
  echo Rode INSTALAR_AVANCADO_WINDOWS.bat primeiro.
  pause
  exit /b 1
)

set "PY=%CD%\.venv\Scripts\python.exe"

where nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo ERRO: nvidia-smi nao encontrado. Verifique o driver NVIDIA.
  pause
  exit /b 2
)

echo [1/4] Sessoes Ollama externas preservadas; nenhuma sera encerrada automaticamente.

echo [2/4] Atualizando pip...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo [3/4] Instalando runtime CUDA 12 + cuBLAS + cuDNN 9 dentro da .venv...
"%PY%" -m pip install --upgrade --only-binary=:all: -r "requirements\gpu-windows.txt"
if errorlevel 1 goto :fail

echo.
echo [4/4] Smoke test REAL do faster-whisper na GPU...
"%PY%" scripts\test_gpu.py --model large-v3 --compute int8_float16
if errorlevel 1 goto :gpu_fail

echo.
echo ================================================================
echo Smoke test sintetico de inferencia CUDA aprovado; qualidade ASR real ainda requer benchmark.
echo Abra ABRIR_ANALYZER.bat e deixe Dispositivo = cuda.
echo ================================================================
pause
exit /b 0

:gpu_fail
echo.
echo O runtime foi instalado, mas o teste CUDA ainda falhou.
echo Copie toda a saida desta janela para o ChatGPT.
pause
exit /b 3

:fail
echo.
echo Falha durante a instalacao do runtime NVIDIA.
pause
exit /b 1