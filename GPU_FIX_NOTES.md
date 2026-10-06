# GPU Fix - v1.1.2

## Objetivo
Impedir fallback silencioso do faster-whisper para CPU e carregar o runtime NVIDIA CUDA 12 a partir da propria `.venv` no Windows.

## Componentes
- `CORRIGIR_GPU_WINDOWS.bat`: instala CUDA runtime, cuBLAS e cuDNN 9 via wheels NVIDIA para Windows.
- `DIAGNOSTICO_GPU_WINDOWS.bat`: mostra GPU e runtime detectado.
- `scripts/test_gpu.py`: smoke test real de inferencia do faster-whisper em CUDA.
- `src/ldporto/gpu_runtime.py`: registra DLLs NVIDIA usando `os.add_dll_directory` antes do CTranslate2.
- CPU fallback desativado por padrao (`transcription.allow_cpu_fallback: false`).
- GUI inicia em `cuda` quando `nvidia-smi` existe.
- `ABRIR_ANALYZER.bat` descarrega modelos Ollama antes do ASR para liberar VRAM.

## Uso recomendado para RTX 5070
1. Execute `CORRIGIR_GPU_WINDOWS.bat` uma vez.
2. O final deve mostrar `GPU TEST OK`.
3. Execute `ABRIR_ANALYZER.bat`.
4. Deixe `Dispositivo = cuda`.
5. Analise o video. O log deve permanecer em `large-v3 / cuda / int8_float16` e nunca trocar para CPU.
