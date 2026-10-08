# R4.9 / Sessões 9–11 — Teste real e critérios de homologação

**Base:** R4.9/S8, incremental. **Separação obrigatória:** testes automáticos e MP4 sintético ≠ aprovação editorial do vídeo Emerson/Clóvis. Esta distribuição contém Analyzer + ponte local renderizadora em FFmpeg. O projeto independente `LDPORTO_VIDEO_CURATOR` NÃO estava anexado: não houve alteração ou teste do código daquele aplicativo. A ponte legada `bridge_curator_r4.py` continua disponível.

## S9 — entregas operacionais

- Validação rigorosa de `SECOND_CURATION_READY` pelo manifest, referência dos candidatos, visual obrigatório da shortlist, SHA-256 e `workflow.review_ready`. `PARTIAL` não entra.
- Verificação do **arquivo original do vídeo** contra SHA-256 informado no pacote. Arquivo fonte diferente, incompleto ou não autenticado bloqueia planejamento.
- Importa Stories, shortlist ou `SECOND_CURATION_DECISIONS.json` (contrato V4.4); IDs, títulos sugeridos, tempos, transcrição segmentada, palavras anotadas e recomendações do Director ficam no `CURATOR_S9_PLAN.json`. Classificação comercial `excluded/review` bloqueia candidato, inclusive override tentado por fornecedor externo.
- Quando não há crop visual comprovadamente seguro, a política de render é `source_preserve_blurred_fill`: toda a imagem original fica visível sobre fundo desfocado, **sem Smart Zoom ou split inventado**. Director/reação são importados como recomendações para revisão humana, não comandos cegos.
- Render FFmpeg independente para cada `STORY_NNN.mp4`/`SHORT_NNN.mp4`, H.264/AAC, resolução **1080×1920**, 30fps; overlay ASS básico para título e legendas opcionais *provisórias*. Espaçamento e estilos dos títulos não são considerados verificados contra faces/GC; é obrigatório assistir.
- `--music` ativa mix instrumental discreto (volume 10% sobre áudio original, sem separação de voz). Performances classificadas como tais preservam integralmente o áudio original, sem mix. **Não afirmar que música de fundo original foi separada**: isso ainda exige um separador de fontes e aprovação por escuta.
- Per-file MP4 SHA-256 e verificação de vídeo, áudio, duração e desvio temporal áudio-vídeo quando disponível; erro crítico não libera o arquivo como tecnicamente válido.
- **Gate por hash**: primeiro canário; depois checklist humano explícito; depois renderização do lote; por último revisão humana individual dos MP4s, vinculada a seus SHA-256. Arquivos finais continuam locais, sem publicação automática.
- `--draft-captions` serve **apenas para conferir visualmente** hipóteses ASR em cortes. Não implica fidelidade auditiva. Nada de karaokê sem word-alignment e áudio revisados. O `.ass` acompanha cada MP4.
- Transições: cortes diretos limpos preservados por padrão. Não introduzir transição decorativa no começo da fala, clímax ou payoff. Crop, split, Smart Zoom e animações finais continuam pendentes de prova de acompanhamento facial/frames.

## Começar o teste real (Windows 10/11 + Python 3.11)

A partir da **raiz do projeto**, após instalar as dependências e confirmar FFmpeg com `ffmpeg -version` / `ffprobe -version`:

```powershell
.venv\Scripts\python.exe scripts\dev\start_real_test_s11.py `
  --package "C:\analises\SECOND_CURATION_READY_video.zip" `
  --source "C:\videos\emerson_clovis_original.mp4" `
  --output "C:\analises\TESTE_S11"
```

Ou utilize o launcher com três argumentos:

```bat
scripts\windows\TESTAR_FLUXO_REAL_WINDOWS.bat "C:\analises\SECOND_CURATION_READY_video.zip" "C:\videos\emerson_clovis_original.mp4" "C:\analises\TESTE_S11"
```

**Por segurança, nenhuma etapa baixa vídeos automaticamente nem aceita pacote `PARTIAL`**. A fonte deve ser exatamente o arquivo cujo SHA está registrado no pacote. Se o vídeo for redownload/transcodificado, gerar pacote atualizado a partir da fonte correta — **não reescrever hashes apenas para passar**.

O comando produz `CURATOR_S9_PLAN.json`, `STORY_001.mp4` (ou `SHORT_001.mp4`), `STORY_001.ass`, `STORY_001.render.json`, `S9_CANARY_REPORT.json`, `S10_RESOURCES.json`, `S11_HOMOLOGATION_PENDING.json` e `.md`.

Assista ao canário em 1080×1920. **Não marque como aprovado** antes de ouvir a fala, comparar o contexto e o desfecho, verificar rostos, GC, título, quadro, legendas e áudio.

## Fluxo manual de autorização de lote

Após a revisão do canário, crie `C:\analises\TESTE_S11\canary_checklist.json`:

```json
{
  "editorial": true,
  "commercial": true,
  "subtitles": true,
  "camera": true,
  "audio": true,
  "safe_area": true,
  "payoff": true
}
```

**Coloque `true` apenas depois de conferir cada item.** As marcas não são preenchidas automaticamente. Caso ainda não tenha ouvido/conferido, use `false`: o gate bloqueará a etapa.

```powershell
.venv\Scripts\python.exe scripts\dev\curator_s9.py approve `
  --plan "C:\analises\TESTE_S11\CURATOR_S9_PLAN.json" `
  --canary-report "C:\analises\TESTE_S11\S9_CANARY_REPORT.json" `
  --checklist "C:\analises\TESTE_S11\canary_checklist.json" `
  --reviewer "Revisor local" `
  --output "C:\analises\TESTE_S11\CANARY_APPROVAL.json"
```

Depois:

```powershell
.venv\Scripts\python.exe scripts\dev\curator_s9.py batch `
  --plan "C:\analises\TESTE_S11\CURATOR_S9_PLAN.json" `
  --canary-report "C:\analises\TESTE_S11\S9_CANARY_REPORT.json" `
  --approval "C:\analises\TESTE_S11\CANARY_APPROVAL.json" `
  --output "C:\analises\TESTE_S11\STORIES_BATCH"
```

Cada arquivo independente vem acompanhado de `.render.json` com SHA-256. O manifesto `STORIES_BATCH\BATCH_REVIEW_MANIFEST.json` fica em estado `REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE`.

### Gate final por Story

Após assistir **cada MP4**, crie `reviews.json` contendo uma entrada por Story, com `id`, `sha256` extraído de seu `.render.json`, `reviewer` e todas as chaves de `canary_checklist.json` (true somente após validação). Então:

```powershell
.venv\Scripts\python.exe scripts\dev\curator_s9.py finalize `
  --plan "C:\analises\TESTE_S11\CURATOR_S9_PLAN.json" `
  --batch-manifest "C:\analises\TESTE_S11\STORIES_BATCH\BATCH_REVIEW_MANIFEST.json" `
  --reviews "C:\analises\TESTE_S11\reviews.json" `
  --output "C:\analises\TESTE_S11\FINAL_REVIEW_RECEIPT.json"
```

O recibo `REVIEWED_FINAL_FILES` **não posta** em YouTube/TikTok/Instagram, nem garante direitos musicais. Qualquer edição posterior do MP4 invalida seu hash e exige revisão nova.

## S10 — A/B sem promessas de velocidade

```powershell
.venv\Scripts\python.exe scripts\dev\benchmark_semantic_r3b.py `
  --transcription "C:\analises\EMERSON_CLOVIS\04_transcription.json" `
  --sample-indices 0 2 4 --run-model --output "C:\analises\s10_semantic_ab.json"

.venv\Scripts\python.exe scripts\dev\benchmark_vision_r3b.py `
  --video "C:\videos\emerson_clovis_original.mp4" --frames 18 --output "C:\analises\s10_vision_ab.json"

.venv\Scripts\python.exe scripts\dev\performance_s10.py `
  --semantic-report "C:\analises\s10_semantic_ab.json" `
  --vision-report "C:\analises\s10_vision_ab.json" `
  --output "C:\analises\S10_PERFORMANCE.json"
```

O benchmark A/B já existente compara face/HOG serial e paralelo **com o mesmo detector e os mesmos frames**. O relatório S10 bloqueia a recomendação de paralelismo se caixas, número de chamadas ou speedup não passarem o gate. O Ollama usa o mesmo schema e grounding; throughput tokens/s e tempo são medidos quando o modelo local responde; avaliações sem modelo são apenas tamanho do prompt. **Qualidade semântica real depende de uma amostra rotulada manualmente.**

Não alterar `config.yaml`, número de threads, CPU/GPU concorrente ou apagar cache com base em uma única execução. Os checkpoints existentes e ETA com histórico permanecem preservados. O botão **Recursos S10** da GUI exibe CPU/GPU/FFmpeg disponíveis; não mexe nos recursos.

## S11 — Comparação e aceitação

Rode testes da versão instalada:

```powershell
$env:PYTHONPATH = ".;src"
.venv\Scripts\python.exe -m pytest -q --junitxml "C:\analises\S11_AUTOMATED_TESTS.xml"
```

E a homologação, depois do lote:

```powershell
.venv\Scripts\python.exe scripts\dev\homologation_s11.py `
  --package "C:\analises\SECOND_CURATION_READY_video.zip" `
  --source "C:\videos\emerson_clovis_original.mp4" `
  --preview "C:\analises\TESTE_S11\STORY_001.mp4" `
  --batch-manifest "C:\analises\TESTE_S11\STORIES_BATCH\BATCH_REVIEW_MANIFEST.json" `
  --analysis "C:\analises\EMERSON_CLOVIS" `
  --baseline "C:\analises\BASELINE_ANTERIOR" `
  --junit "C:\analises\S11_AUTOMATED_TESTS.xml" `
  --output "C:\analises\TESTE_S11\S11_HOMOLOGACAO_FINAL.json"
```

Relatório também em Markdown. Para registrar aprovação editorial no S11, passe `--human-reviews` com `reviewer`, `checks` (`editorial`, `payoff`, `commercial`, `subtitles`, `face_tracking`, `audio_sync`, `safe_area`, `broadcast_graphics`, `camera_motion`) e os SHA-256 atuais de `package_sha256`, `source_sha256`, `preview_sha256`. Sem isso, continua pendente. Não use dados sintéticos como se fossem a medição do Emerson e Clóvis.

## Critérios de aprovação final

1. Pacote comprovadamente `READY` sem divergências entre manifestos, índices, Shorts e Stories.
2. Canário 1080×1920 tecnicamente válido, SHA original intacto, áudio e duração conferidos.
3. Revisão humana explícita de comercial/contexto/punchline, legibilidade de legendas, rostos, GC, zonas seguras e áudio.
4. Stories em MP4 independentes; todos com hash e revisão própria.
5. Testes automatizados sem erro, ambiente Windows Python 3.11/FFmpeg/NVIDIA/Ollama devidamente diagnosticado, métricas do benchmark anterior comparáveis.
6. Desempenho reportado como ganho **somente quando medido**, qualidade editorial humana validada separadamente.

### Estado desta entrega

Automatização, regressão e renderização técnica foram exercitadas com **vídeo sintético**, não com Emerson/Clóvis. Não houve acesso à GPU Windows, Ollama do usuário nem ao código independente do Curator. Portanto, a fase S11 **não está homologada para publicação real**. Não chamar esses testes de validação editorial definitiva.
