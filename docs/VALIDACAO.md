> Relatório histórico da entrega anterior. Resultados desta entrega v3: [TEST_REPORT_V3.md](TEST_REPORT_V3.md). A suíte recebida tinha 10 testes v2; a contagem antiga abaixo não foi reconstituída.

# Validação desta entrega

Data: 2 de outubro de 2026.

## Executado

- 27 casos de teste automatizado, cobrindo:
  - URLs de vídeo e rejeição de entradas inválidas;
  - configuração YAML e erros de digitação;
  - timestamps e transporte de milissegundos;
  - manutenção de falas sobrepostas e locutor ambíguo sem atribuição artificial;
  - preservação de repetição de palavras;
  - importação sem inventar alinhamento de texto;
  - blocos de legenda, pontuação e troca de locutor;
  - caixas normalizadas e geometria de crop futuro;
  - identidade temporal limitada à mesma câmera;
  - reidentificação por embedding sem duas caixas com um mesmo ID;
  - timeline sem buracos cobrindo a duração inteira;
  - duas pessoas visíveis sem participação comprovada não geram split screen;
  - semântica sem omitir segmentos e rejeição de IDs/tópicos inválidos do LLM;
  - heurísticas sem scores editoriais fictícios;
  - invalidação de cache por parâmetros e artifact ausente;
  - lock de execução;
  - ownership de chunks ASR sem duplicar contexto ou apagar repetições.
- Pipeline com FFmpeg/FFprobe/PySceneDetect/OpenCV reais sobre fixture de duas cenas,
  áudio sintético e anotações explicitamente importadas.
- Extração/tratamento com duração preservada.
- Caso real de arquivo com trilha de áudio deslocada +0,5s.
- Reexecução que usa cache e recria relatório removido.
- Compilação dos arquivos Python.
- Resolução das dependências base/visão para Windows amd64 / Python 3.11 por
  pip dry-run, sem executar a instalação Windows.
- Resolução de dependências base + diarização + visão + OCR para Python 3.12 / Linux
  por pip dry-run, sem carregar esses modelos opcionais.

## Não executado em ponta a ponta

- Reconhecimento real large-v3 de entrevista PT-BR.
- Diarização real community-1 com token/modelo autorizado.
- MediaPipe/YuNet/SFace aplicados a uma entrevista real.
- LLM Ollama real, qualidade semântica e retenção/viralização.
- OCR Tesseract real ou classificador PANNs real.
- Separação Demucs real.
- Download YouTube de vídeo real.
- Interface nativa em um desktop Windows e execução CUDA.

O teste de ASR em chunks substitui o backend por hipóteses controladas. A
importação da fixture testa o restante do pipeline, sem se passar por transcrição
de fala humana.

Um download de modelo tiny foi tentado no ambiente de teste, mas não ficou
disponível por incompatibilidade de transporte HTTP/proxy da sessão. Portanto não
há alegação de validação acústica real.

## Ambiente dos testes

Python 3.12.14, Linux, CPU, NumPy 2.2.6, OpenCV 4.11.0.86,
PySceneDetect 0.7.1, SoundFile 0.13.1, FFmpeg/FFprobe disponíveis.

## Executar no seu ambiente

    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    .\.venv\Scripts\python.exe -m pytest tests -q
    .\.venv\Scripts\python.exe analyze.py --doctor

Para a primeira entrevista real, ouça trechos do início/meio/fim, confirme as
palavras marcadas e compare as miniaturas com os locutores antes de planejar crops.
