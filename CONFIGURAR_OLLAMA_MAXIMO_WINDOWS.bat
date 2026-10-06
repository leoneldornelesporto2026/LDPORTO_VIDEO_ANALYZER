@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ================================================================
echo L.D.PORTO VIDEO ANALYZER - OLLAMA LOCAL / POTENCIA MAXIMA
echo ================================================================
echo.

echo [1/4] Verificando Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
  ) else (
    where winget >nul 2>&1
    if errorlevel 1 (
      echo ERRO: Winget nao encontrado.
      echo Instale o Ollama manualmente e execute este arquivo novamente.
      echo https://ollama.com/download
      pause
      exit /b 1
    )
    echo Instalando Ollama via winget...
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
      echo ERRO: Falha ao instalar Ollama.
      pause
      exit /b 1
    )
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
  )
)

where ollama >nul 2>&1
if errorlevel 1 (
  if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo ERRO: Ollama nao foi encontrado apos a instalacao.
    echo Feche este CMD, abra outro e rode novamente.
    pause
    exit /b 1
  )
  set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
)

if not exist ".venv\Scripts\python.exe" (
  echo ERRO: Ambiente Python nao encontrado.
  echo Execute INSTALAR_WINDOWS.bat primeiro.
  pause
  exit /b 1
)

echo [2/4] Ajustando Ollama para analise local pesada...
set "OLLAMA_NO_CLOUD=1"
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_NUM_PARALLEL=1"
set "OLLAMA_MAX_LOADED_MODELS=1"
setx OLLAMA_NO_CLOUD 1 >nul
setx OLLAMA_FLASH_ATTENTION 1 >nul
setx OLLAMA_NUM_PARALLEL 1 >nul
setx OLLAMA_MAX_LOADED_MODELS 1 >nul

echo [3/4] Detectando GPU e baixando o melhor Qwen3 compativel...
if "%~1"=="" (
  ".venv\Scripts\python.exe" "scripts\configure_ollama.py"
) else (
  ".venv\Scripts\python.exe" "scripts\configure_ollama.py" --model "%~1"
)
if errorlevel 1 (
  echo.
  echo ERRO: A configuracao do Ollama falhou.
  echo Rode DIAGNOSTICO_WINDOWS.bat e copie o resultado.
  pause
  exit /b 1
)

echo [4/4] Diagnostico final...
".venv\Scripts\python.exe" "analyze.py" --doctor

echo.
echo PRONTO. Agora execute ABRIR_ANALYZER.bat
echo Para forcar outro modelo: CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat qwen3:14b
pause
exit /b 0
