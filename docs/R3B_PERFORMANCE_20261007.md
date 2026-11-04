# Rodada 3B — Performance segura (R4.6)

## Objetivo e baseline real

Preservar qualidade e identidade de cada frame/candidato, sem prometer ganhos não medidos.
Benchmark da análise Clóvis/Pânico de 8245 segundos: Semântica 5485,48s (55,54% do tempo medido),
Tracking 2441,16s (24,72%), Cenas 906,41s (9,18%) e ASR 830,34s (8,41%).
Em `07_people_tracking.json` o pipeline mediu:

| Fase visual | Tempo acumulado aproximado |
| --- | ---: |
| face_detection | 865,42s |
| body_detection (HOG) | 597,06s |
| landmark_inference | 255,13s |
| face_embedding | 165,74s |
| video_decode | 213,70s |
| motion_estimation | 175,95s |
| checkpoint_io | 112,20s |
| tracker_association | 6,54s |

`face_detection`/`face_embedding` e `face_body_embedding_detection` são grupos hierárquicos:
**não somar ambos**. Em execução CPU paralela, somas das fases também podem sobrepor.

## O que foi implementado

1. **Cache semântico:** chunks já validados ainda são verificados por checksum e re-grounding,
   mas não são regravados. `semantic_metrics.chunk_cache_hits` e
   `semantic_metrics.chunk_cache_rewrites_avoided` mostram o efeito.
2. **Prompt compacto opt-in:** `semantic_analysis.compact_prompt: true` suprime a segunda
   cópia textual do JSON Schema (o schema **permanece** no parâmetro `format` do Ollama).
   Inclui o prompt de reparo estrutural. Chaves de cache antigas são **idênticas** quando
   `compact_prompt: false`; o modo compacto recebe cache separado.
3. **Paralelismo CPU opt-in HOG/face:** `vision.parallel_hog_with_face: true`
   permite no máximo **1 thread adicional CPU** e apenas quando HOG seria chamado de
   qualquer forma por agenda, sobrepondo-o à detecção facial no mesmo frame. Mesmos boxes,
   sem alteração em `track/update`, amostragem, scores ou thresholds de reconhecimento.
   Se a detecção de rosto disparar HOG por baixa confiança em frame não agendado,
   o HOG continua síncrono (sem trabalho extra especulativo).
4. **Guarda fail-closed:** exige psutil, 4+ CPUs lógicos, ao menos 4 GiB de RAM
   disponível e CPU não acima de 80% no início. Sem evidência, fica serial.
   Nunca paraleliza GPU, Ollama, Whisper e diarização.
5. **Benchmark A/B sem tocar no cache:** scripts de visão e semântica com relatórios JSON,
   comparação de evidências e opção de testar Ollama com inferência local de forma explícita.

## Medições nesta sessão

- Prompt semântico (amostras 0, 8 e 30 de `04_transcription.json`): diminuição
  do texto de sistema de 67,6% a 73,9%. O schema `format` continua idêntico.
- Preview `CLIP_001_PREVIEW.mp4`, oito quadros (CPU Linux desta sessão, sem equivalência
  ao Windows/CUDA): detecções e contagem de chamadas idênticas. Serial 0,785s,
  HOG+face sobrepostos 1,426s: **mais lento**, portanto `parallel_hog_with_face`
  permanece desligado por padrão.
- **NÃO** foi realizado benchmark do Ollama ou do vídeo de 2h17 após estas mudanças.
  Não existe ganho percentual real de runtime comprovado até um A/B no Windows.

## Rodar A/B no Windows PowerShell, antes de ativar os modos

Da raiz do projeto, com `.venv`/modelos e arquivos locais:

```powershell
.\.venv\Scripts\python.exe scripts\dev\benchmark_semantic_r3b.py --transcription "C:\CAMINHO\04_transcription.json" --sample-indices 0 8 30 --output r3b_semantic_ab_offline.json
# Faz 2 inferências POR chunk selecionado, sem alterar o cache; só com Ollama iniciado:
.\.venv\Scripts\python.exe scripts\dev\benchmark_semantic_r3b.py --transcription "C:\CAMINHO\04_transcription.json" --sample-indices 0 8 30 --run-model --output r3b_semantic_ab_ollama.json
.\.venv\Scripts\python.exe scripts\dev\benchmark_vision_r3b.py --video "C:\CAMINHO\video.mp4" --frames 40 --output r3b_vision_ab.json
```

Ativar os knobs somente **um por vez**, em `config/config.yaml`, se validade e
latência forem melhores e GPU/CPU/RAM permanecerem saudáveis:

```yaml
vision:
  parallel_hog_with_face: true
semantic_analysis:
  compact_prompt: true
```

*Trechos acima são overrides ilustrativos dessas opções, não um config completo.*

Se `compact_prompt=true` aumentar falhas/repairs/fallback ou reduzir tema/QA,
restaurar `false` e preservar o cache semântico anterior.
Se `parallel_hog_with_face=true` aumentar latência ou mudar detecções, restaurar `false`.

## Cache e segurança

- As alterações em `semantic.py` e `vision.py` mudam os hashes de etapa:
  `15_semantic` e `07_people_tracking` poderão invalidar checkpoints de estágio.
- **Com prompt legado**, os chunks semânticos antigos mantêm a MESMA chave e podem
  ser reusados, evitando novos chamados ao Ollama (se o cache ainda existir).
- `--force` invalida deliberadamente todo esse ganho. Não excluir `.cache`, `.venv` ou `analysis`.
- Mudar o modo compacto exige inferência semântica nova intencionalmente.
- Mudar a agenda de HOG exige reprocessar visão, pois o perfil de execução mudou.
- Os dois modos são opt-in por padrão para evitar regressões não medidas.
- Validação definitiva requer Windows/Python 3.11/CUDA e benchmark completo.

## Próximas melhorias (não implementadas nesta build)

1. Medir first-pass valid, tokens/s, prompt eval e reparos com Ollama real; escolher modo
   compacto somente se A/B demonstrar maior qualidade/tempo.
2. Perfil por modelo YOLO/HOG/YuNet/SFace/MediaPipe no vídeo real. Avaliar se IO assíncrono
   ou batching alteram positivamente o tempo sem perda de observações.
3. Experimentar paralelismo entre ASR GPU e SceneDetect CPU somente com isolamento de
   estado, orçamento de memória/VRAM e testes de ordem/cancelamento; **não foi ativado**.
4. Medir `07` completo na máquina e deixar o HOG serial se não houver ganho.
5. Validar `16_understanding`/gates e o pacote social READY em replay após mudanças de código.
