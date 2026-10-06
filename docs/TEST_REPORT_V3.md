# Relatório final — Camera Director v3

Entrega de 04/10/2026, construída sobre o workspace em andamento, sem reextrair nem substituir as alterações anteriores. Comparação de arquivos abaixo feita por conteúdo contra o ZIP original recebido.

## Resultado da validação

**117 testes passaram; 0 falharam; 0 ignorados.** São 10 testes legados e 107 casos novos, incluindo parametrizações da validação de configuração. Comando executado: `python -m pytest project/src/tests -q --junitxml=project/docs/TEST_RESULTS_V3.xml` a partir da pasta pai. Tempo da última suíte: 1,96 s. O XML JUnit acompanha esta entrega.

Ambiente: Linux, Python 3.12.14, pytest 9.1.1, NumPy 2.2.6, OpenCV 4.11.0.86 e FFmpeg disponível. Todos os arquivos Python foram analisados com gramática Python 3.11; todos os BATs foram verificados com CRLF real. Importação de `app.py` e ajuda da CLI também passaram. Isso não equivale a executar a GUI nativa nem a suíte no runtime 3.11.

Cobertura executada:

- Configuração: tipos, valores finitos, limites, campos desconhecidos, presets e relações entre limites.
- Política: interrupção curta, diálogo rápido/two-shot, overlap, split conservador e lados estáveis, ausência visual, baixo consenso, empate, mapping manual, hysteresis, hold, cooldown e supressão.
- Geometria/movimento: deadzone, jitter, velocidade/aceleração/jerk, overshoot de zoom, estabilidade de monólogo, breathing, resolução/nitidez e segurança de crop.
- Tempo: limites fracionários de shots, impossibilidade de atravessar cortes da fonte, reset entre tracks/cenas, look-ahead limitado ao shot e reaction shots por movimento sem emoção inferida.
- Contratos: JSON Schema, serialização sem NaN, intervalos contíguos, foco contemporâneo e split com ambos presentes.
- Integração real do pipeline com mídia sintética temporária: FFmpeg/OpenCV, transcrição importada e semântica heurística; etapas caras bloqueadas no segundo processamento para comprovar cache; perfil alterado sem executá-las.
- Director-only após remoção do vídeo: exports legados preservados por hash, novo handoff, invalidação por config/evidência, remoção de debug/métricas obsoletos ao desativar.
- Compatibilidade com a amostra real enxuta recebida, sem inventar locutores/observações; gerador sintético visual com 96 frames decodificados.

Benchmark separado: 600 s sintéticos/2.400 amostras em 3,45 s com tracemalloc, pico de alocação do Director 5,89 MiB. Não mede ASR, GPU nem consumo total do processo. Detalhes em `DIRECTOR_BENCHMARK.json`.

## Funcionalidades entregues

Director como etapa 19 depois das análises pesadas, cache independente por entradas/código/configuração; active speaker reforçado com consenso e visibilidade contemporânea; percepção v2 mantida como camada separada. Controle com memória temporal, perfis, two-shot, split conservador, reação por movimento, look-ahead, breathing e suavização física de pan/zoom. Correções de transições entre pessoas/cenas e de janelas atravessando cortes. Amostragem visual adaptativa na passagem existente.

Pipeline, CLI, GUI, exports e handoff integrados. A GUI oferece habilitação, perfil, overrides de hold/zoom, resumo de métricas e reprocessamento isolado. Outputs v1/v2 e arquivos legados preservados; extensão v3 identificada separadamente. Não há nova dependência pesada de produção.

## Outputs e schemas

- `camera_director_timeline.json`: array de decisões com `schema_version: "3.0"`, IDs, limites de shot, modo, foco, layout, framing, crop, split, razões, eventos de áudio e keyframes de câmera.
- `camera_director_debug.json`: opcional; schema 3.0 com eventos, candidatos, scores, estado, supressões e contagens.
- Schemas em `schemas/camera_director_timeline.schema.json` e `schemas/camera_director_debug.schema.json`.
- `master_timeline.json`: referências temporais aos intervalos do Director.
- `analysis_quality.json` e `video_understanding.json`: cobertura, incerteza, plano médio, trocas/minuto, split/two-shot, supressões e resumo.
- `CHATGPT_ANALYSIS_HANDOFF.json/.md`: timeline compactada, configuração efetiva, métricas, referência ao debug, foco visual versus áudio, origem/shot, motivos, framing/crops, trajetórias, contexto editorial e instruções de consumo. O debug completo não é duplicado.

Consumidores devem seguir keyframes e cortes explícitos; `full_frame` significa fit com padding. Não interpolar entre shots. Consulte `CAMERA_DIRECTOR_V3.md` para o contrato detalhado.

## Reprocessar somente o Director

Na raiz do projeto, Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe analyze.py --director-only "analysis\video_ID" --camera-profile podcast
```

Exige `analysis.json` completo com evidências salvas. Não exige vídeo disponível e não executa ASR, diarização, tracking ou extração. `--force` nessa modalidade força somente o Director. Também existe botão **Reprocessar só câmera** na GUI. A amostra enxuta recebida não tem `analysis.json`, portanto não serve como entrada completa para esse comando.

## Testar no Windows

1. Preserve a `.venv`, os modelos, vídeos e análises da instalação existente; compare seu YAML personalizado antes de substituir.
2. Para instalação nova com Python 3.11, execute `INSTALAR_WINDOWS.bat` e disponibilize FFmpeg conforme o README.
3. Execute `TESTAR_WINDOWS.bat` ou os comandos abaixo.
4. Abra `ABRIR_ANALYZER.bat`, teste vídeo local e cada perfil; em seguida reexecute somente câmera e confirme status/cache e exports.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest src\tests -q
.\.venv\Scripts\python.exe analyze.py --doctor
```

## Limitações restantes — não testadas como produção

- Não foi executado runtime nativo Windows/Python 3.11, interface Tk interativa, CUDA/RTX 5070, modelos Whisper/pyannote/MediaPipe, Ollama nem download YouTube.
- Não havia vídeo real nem `people_observations.json` na amostra. Testes comportamentais usam fixtures explícitas e mídia sintética; não comprovam acurácia audiovisual real. O teste do pipeline importa a transcrição e desativa diarização e detecção de cenas; os cortes são cobertos separadamente por fixtures.
- Active speaker permanece heurístico, sem probabilidades calibradas ou backend ASD treinado novo. Não foi validada qualidade de sincronização labial em vídeo humano real.
- B-roll/logos são respeitados quando já rotulados; não foi criado detector semântico geral desses conteúdos. Reações usam movimento, não inferência emocional.
- Segurança de crop/split é validada nas observações amostradas. O renderizador final deve conferir frames reais. Nitidez desconhecida limita zoom; fallback preserva a fonte quando falta evidência.
- A documentação de validação antiga é histórica; os números desta entrega são os do XML incluído.

## Conteúdo do pacote

Código completo, BATs CRLF, configuração, documentação, schemas, testes e amostra JSON legada preservada. Sem `.venv`, vídeos, pesos de modelos, caches ou bytecode. `models/README.md` e manifesto de modelos são apenas documentação. Metadados de cache Whisper existentes no ZIP de entrada foram excluídos desta entrega, conforme solicitado.

`WORK_PACKAGE_*` permanece como proveniência histórica da entrada, não como inventário atual. `DELIVERY_MANIFEST.json` contém hashes da entrega (exclui a si próprio).

## Arquivos alterados e novos

Lista completa em `FILES_CHANGED_V3.md`: 18 arquivos alterados e 22 arquivos novos.
