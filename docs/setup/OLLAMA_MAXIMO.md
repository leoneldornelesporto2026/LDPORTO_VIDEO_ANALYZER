# Patch 1.1 — Ollama MAX

Este pacote foi ajustado para usar o Ollama como segunda camada semântica local.

## O que mudou

- Interface inicia com Ollama habilitado conforme `config/config.yaml`.
- Lista os modelos Ollama instalados e permite escolher `max`, `balanced` ou `fast`.
- `profile=max`: contexto 32768, saída estruturada, temperatura 0 e `keep_alive` de 30 minutos.
- Análise semântica continua aterrada em `segment_id`; saída fora do schema ou ID inventado é rejeitada.
- Segunda passada global gera `ollama_editorial_review.json` com top momentos, justificativas, hooks e títulos editoriais.
- `CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat` instala/configura Ollama e escolhe Qwen3 8B/14B/30B pela VRAM NVIDIA.
- Diagnóstico separa CUDA do CTranslate2/Whisper de GPU/VRAM usada pelo Ollama e mostra `ollama ps`.
- Ollama fica restrito ao loopback `127.0.0.1`.
- `charset-normalizer` foi incluído para eliminar o `RequestsDependencyWarning` observado no diagnóstico.
- Warning de symlinks do Hugging Face é suprimido; no Windows o cache continua funcional mesmo sem Developer Mode.

## Começar

1. `INSTALAR_WINDOWS.bat`
2. `INSTALAR_AVANCADO_WINDOWS.bat` (já chama a configuração do Ollama)
3. `DIAGNOSTICO_WINDOWS.bat`
4. `ABRIR_ANALYZER.bat`

Para configurar só o Ollama: `CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat`.
Para forçar um modelo: `CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat qwen3:14b`.
