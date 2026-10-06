# Homologação local — Windows 10/11 + Python 3.11

## 1. Ambiente

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python install.py
python analyze.py --doctor
```

`--doctor` deve confirmar FFmpeg/ffprobe, faster-whisper/CTranslate2 conforme instalado, GPU/CUDA quando usada, Pyannote/HF, modelos de visão, Ollama, disco/permissão e cache. O token HF nunca deve aparecer no output.

## 2. Regressão

```bat
python -m pytest src/tests -q --disable-warnings
```

Esperado para esta entrega: `129 passed` na suíte que independe de hardware/modelos externos. O número deve ser reexecutado localmente; não copie o resultado deste runner como evidência Windows.

## 3. Vídeo real

```bat
python analyze.py "C:\caminho\video real.mp4" --preview --camera-profile natural
```

Com diarização ativa, configure `HF_TOKEN` e aceite/aceda ao modelo configurado. Verifique ao final `run_manifest.json`, `analysis_quality.json`, `camera_plan.json`, `camera_director_timeline.json`, `preview_validation.json` e `second_curation_package.json`.

## 4. Critérios mínimos

- people tracking termina sem TypeError nullable;
- `NaN/Infinity` não aparecem em JSON;
- falha proposital após checkpoints reutiliza chunks íntegros;
- diarização indisponível não inventa speaker/person;
- Camera Director coverage só é >0 se realmente executado;
- canary preview renderiza e o verifier lê o arquivo renderizado;
- paths com espaços/acentos funcionam;
- BATs estão em CRLF real.
