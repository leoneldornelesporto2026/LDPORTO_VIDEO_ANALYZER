## R4.9/S6 — Camera Director e Smart Zoom (2026-10-07)

**Nova Sessão 6:** pré-planejamento de crop e split em proporção correta, funil diagnóstico de foco/zoom, Q&A/reveal como beats apenas com evidência real, detector temporal de barras no preview e auditor CLI offline. Base S5 e salvaguardas do Active Speaker mantidas. Leia [docs/S6_CAMERA_DIRECTOR_SMART_ZOOM_20261007.md](docs/S6_CAMERA_DIRECTOR_SMART_ZOOM_20261007.md). Benchmark dos 4,39% e zeros ainda exige execução original.

## R4.9/S4 — Tracking e recuperação facial (2026-10-07)

- YuNet multiescala orçada; quality gate facial; amostragem nos limites dos shots.
- Preferência por YOLO local para pessoa sentada (fallback HOG identificado); Re-ID facial conservador.
- Auditoria das razões da ausência de embeddings e CSV/contact sheet de revisão humana.
- Procedimento/limitações: [`docs/S4_TRACKING_FACIAL_RECOVERY_20261007.md`](docs/S4_TRACKING_FACIAL_RECOVERY_20261007.md).
- A execução real dos 742 micro-tracklets não acompanha o ZIP: **sem promessa de melhora numérica**.

## R4.9 / Sessão 2 — Integridade do pipeline

A nova auditoria read-only (`scripts/dev/audit_pipeline_integrity_s2.py`) detecta inconsistências de prontidão, comerciais e Stories sem reprocessar vídeo. Leia `docs/S2_PIPELINE_INTEGRITY_HARDENING.md`. `SECOND_CURATION_READY` continua significando pronto **para revisão humana**, não para publicação.

> **R4.7 — Rodada 4 Homologação e segurança editorial:** rechecagem comercial final para Stories/shortlist, consistência dos manifestos, bridge para Curator V2, diagnóstico de preview e prontidão explícita. Ver [docs/R4_FINAL_HOMOLOGACAO_20261007.md](docs/R4_FINAL_HOMOLOGACAO_20261007.md).

> **R4.6 — Rodada 3B Performance segura:** cache semântico sem regravação, opções A/B de prompt compacto e HOG/face CPU (desligadas por padrão), instrumentação e benchmarks. Consulte [docs/R3B_PERFORMANCE_20261007.md](docs/R3B_PERFORMANCE_20261007.md).

> **Build R4.5 — Rodada 3 Parte 1 (Câmera e Percepção).** Melhorias em aquisição de evidência nas cenas curtas, embeddings SFace quando disponível, filtros conservadores de associação speaker↔person para câmera e diagnóstico de oportunidade/ausência de Smart Zoom. Veja [docs/R3_CAMERA_PERCEPTION_PART1.md](docs/R3_CAMERA_PERCEPTION_PART1.md). Mantém versão de cache lógica 4.4.0; mudanças na etapa 07 invalidam seletivamente o cache visual, não a transcrição.

> **V4.2:** [relatorio atual](docs/V4_2_IMPLEMENTATION_REPORT.md), [matriz](docs/V4_2_REQUIREMENT_MATRIX.md),

> **Build de estabilização atual:** V4.4 R3 (cache identity 4.4.0). Veja `docs/V44_R3_STABILIZATION.md`.

> [auditoria independente](docs/WORKER_DISCOVERY_AUDIT.md), [benchmark](docs/V4_2_BENCHMARK_COMPARISON.md).
> Alvo: Windows 10/11 + Python 3.11.x. Testes auxiliares em 3.13 NAO homologam 3.11.
> **Camera Director v3:** leia [docs/CAMERA_DIRECTOR_V3.md](docs/CAMERA_DIRECTOR_V3.md).
> Novo `camera_director_timeline.json`, perfis na GUI e `--director-only` para ajustar câmera sem repetir percepção.
> Relatório atual: [docs/TEST_REPORT_V3.md](docs/TEST_REPORT_V3.md). Documentação v1/v2 abaixo preservada como referência.

# L.D.PORTO VIDEO ANALYZER

V4.4.0 mantém o runtime oficial **Windows/Python 3.11.x**. A entrega adiciona
diagnósticos e evidências speaker/person, fallback visual independente da voz,
Commercial Gate V3, repair semântico por item, recuperação de histórias,
ASR localizado e contrato de segunda curadoria com visuais sob demanda.
O Curator importa ZIP/JSON diretamente, refina cortes em 6 fps, preserva GC
em uma cópia e vincula aprovação ao preview e ao plano atual.

Estado verificável: [ledger V4.4](docs/V44_IMPLEMENTATION_LEDGER.md),
[baseline reconciliado](docs/V44_BASELINE_RECONCILIATION.md) e
[benchmark V4.4](docs/V44_BENCHMARK_REPORT.md). Replays e clips curtos são
identificados separadamente do benchmark completo; coverage não mede acurácia.

Visuais promovidos: `python exportar_ldporto.py --visuals-on-demand PACOTE.zip
--source-video VIDEO.mp4 --candidate MOMENT_ID`. O ZIP original é preservado.
Na GUI, **LIMPAR ARQUIVOS PESADOS** mostra estimativa antes de pedir confirmação;
JSONs, transcrições, pacotes, contact sheets e renders finais são protegidos.

Analisador Python local para a primeira fase de uma plataforma de cortes:
**entender o vídeo inteiro antes de editar**.

Comece por **[docs/setup/LEIA_PRIMEIRO.md](docs/setup/LEIA_PRIMEIRO.md)**.


## V4.3 — Hardening profissional

A V4.3 adiciona tracking/Re-ID mais estáveis, afinidade global speaker-person, filtros comerciais e editoriais mais fortes, cache/repair semântico, Smart Zoom com safety, Preview Verifier, progresso/ETA estruturado, replay downstream e geração automática do pacote compacto de segunda curadoria.

Documentos atuais: [arquitetura V4.3](docs/V43_ARCHITECTURE.md), [benchmark/status](docs/V43_REAL_BENCHMARK.md), [performance](docs/V43_PERFORMANCE.md), [ledger](docs/V43_IMPLEMENTATION_LEDGER.md) e [auditoria](docs/WORKER_DISCOVERY_AUDIT_V43.md).

Ao final de uma análise, o fluxo pode gerar em `pacotes_para_enviar/` um `SECOND_CURATION_READY_*.zip` ou `SECOND_CURATION_PARTIAL_*.zip`, além de mídia opcional separada. O pacote inclui `SECOND_CURATOR_BRIEF.json`, índice, catálogo completo de candidatos, transcrição, evidências e readiness por capacidade.

## V4.2: Readiness E Artefatos

A instalacao recomendada inclui base + diarizacao + visao; OCR/YOLO/audio-events
continuam opt-in. Community-1 online requer token HF em memoria e aceite do modelo.
O preflight verifica imports reais, assets/carregamento, CUDA quando solicitada,
Ollama/modelo e escrita ANTES de resolver/download da midia. Falha em recurso
habilitado nao vira downgrade silencioso; desative-o explicitamente quando apropriado.

O pipeline continua Analyzer -> Perception -> Semantic/Understanding -> Global
Planner -> Camera Director -> Preview/Verifier -> pacote de segunda curadoria.
Nao ha render social final nem segunda curadoria automatica nesta entrega.

`analysis.json` usa referencias com checksum por padrao. Colecoes originais
permanecem em arquivos separados. `--director-only` carrega e valida as referencias,
sem precisar do video original. Para consumidores legados, use
`export.legacy_full_analysis: true`. A GUI/CLI distinguem tracks, identidades
anonimas persistentes, participantes editoriais e locutores acusticos.

O review inclui `analysis_summary.json`, `people_summary.json`,
`camera_plan.compact.json`, `camera_timeline.compact.json`,
`master_timeline.compact.json`, `CHATGPT_ANALYSIS_HANDOFF.compact.json` e chunks
indexados em `review_evidence/`. Fonte original e projecao compacta nao sao sinonimos;
os indices registram esse limite. O exportador retorna READY, IN_PROGRESS,
PARTIAL_EXPORT, EMPTY ou ERROR; um ZIP valido nao garante analise completa.

Comandos adicionais: `.venv\Scripts\python.exe exportar_ldporto.py --self-test`,
`.venv\Scripts\python.exe exportar_ldporto.py --inspect-zip PACOTE.zip` e
`.venv\Scripts\python.exe compare_runs.py OLD NEW --output-dir comparison`.
Veja defaults novos e limitacoes em docs/V4_2_IMPLEMENTATION_REPORT.md.

## Terminal

No Windows, após instalar:

    .\.venv\Scripts\python.exe analyze.py "C:\Videos\entrevista.mp4"
    .\.venv\Scripts\python.exe analyze.py "https://www.youtube.com/watch?v=VIDEO_ID"
    .\.venv\Scripts\python.exe analyze.py "input/video.mp4" --output "analysis/minha_analise"
    .\.venv\Scripts\python.exe analyze.py "input/video.mp4" --semantic ollama
    .\.venv\Scripts\python.exe analyze.py "input/video.mp4" --device cpu --model medium
    .\.venv\Scripts\python.exe analyze.py "input/video.mp4" --offline
    .\.venv\Scripts\python.exe analyze.py --doctor

No Linux/macOS:

    python3.12 install.py
    .venv/bin/python analyze.py input/video.mp4
    .venv/bin/python analyze.py --doctor

Instale FFmpeg/FFprobe no sistema. Apple Silicon é detectado pelo diagnóstico; o
backend de transcrição desta versão usa CPU/int8, não Metal/MPS.

## Fluxo

1. Entrada local ou download unitário YouTube com yt-dlp.
2. Inspeção FFprobe e assinatura SHA-256 completa.
3. Áudio original PCM, trilha mono 16 kHz e speech_clean conservador, alinhados a t=0 do vídeo.
4. Comparação de pequenas amostras original/clean para escolher a fonte ASR.
5. faster-whisper em blocos sobrepostos, com ownership temporal único por palavra.
6. Revisão multipass de regiões de baixa confiança e alternativas sem reescrita.
7. Diarização community-1 no áudio original mono; sobreposições preservadas.
8. Cenas visuais, rostos/corpos, tracking e reidentificação anônima opcional.
9. Associação voz/rosto por evidência conservadora e revisão manual opcional.
10. OCR e classificação de sons opcionais.
11. Tópicos e candidatos editoriais via regras ou Ollama local.
12. Timeline integral, legendas e relatórios.

## Organização

| Pasta | Conteúdo |
|---|---|
| src/ldporto/ | Engines e pipeline |
| config/ | Configuração YAML |
| scripts/ | Ferramentas Windows, export, benchmark e utilitários |
| input/ | Vídeos locais e downloads |
| analysis/ | Resultados por vídeo |
| models/ | Modelos baixados ou fornecidos localmente |
| docs/ | Arquitetura, validação, contrato e áudio avançado |
| examples/ | Exemplos de formato explicitamente sintéticos |
| src/tests/ | Verificação de regras e pipeline |

O programa mantém áudio, cache e logs dentro da pasta de análise de cada vídeo.
Não sobrescreve o arquivo de entrada.

## Testes

    python -m pip install -r requirements.txt -r requirements/dev.txt
    python -m pytest src/tests -q

Os testes com mídia precisam de FFmpeg. Não precisam de conta nem de download de modelos.

## Extensões

- requirements/diarization.txt: community-1 via pyannote.audio 4.
- requirements/vision.txt: landmarks para correlação boca/áudio.
- requirements/yolo.txt: corpos com YOLO em vez de HOG; ativar no YAML.
- requirements/ocr.txt: wrapper Tesseract; executável externo e idiomas necessários.
- requirements/audio-events.txt: PANNs, com checkpoint local explícito.
- requirements/demucs.txt: separação **em outro ambiente Python**.

Não instale todos os extras sem necessidade. Demucs e pyannote 4 possuem
dependências diferentes de PyTorch; por isso o processo de separação fica separado.

Semântica e scores são inferências editoriais, não garantia de viralização.
As limitações constam em cada relatório.

## Fontes

Documentação primária consultada e links de implantação: docs/FONTES.md.


## Ollama local — potência máxima

No Windows, depois da instalação base/avançada, execute:

    CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat

O launcher detecta os modelos locais, inicia por padrão com Ollama habilitado e `profile=max`.
A análise semântica usa saída estruturada e produz uma revisão editorial global aterrada em IDs.
Veja `docs/setup/LEIA_PRIMEIRO.md` para perfis, diagnóstico e fallback.


## Saída social / Stories (build R4-SOCIAL)

A camada de saída social é **downstream**: mudar proporção, preset, fonte, cores ou quantidade de Stories não exige refazer Whisper, diarização, visão ou semântica. O Analyzer prepara o contrato; o `LDPORTO VIDEO CURATOR` continua responsável pelo render social final.

- `Stories` significa **vários momentos independentes** escolhidos ao longo do vídeo, não uma única compilação de 60 segundos.
- Duração padrão por Story: 15–60 s; seleção aplica diversidade temporal, de tópico e de categoria editorial.
- Proporções suportadas: `9:16`, `4:5`, `1:1`, `16:9`.
- Presets disponíveis incluem `Karaoke`, `Clean Bold`, `News`, `Show Highlight`, `Creator Style` e outros.
- A GUI permite escolher proporção, preset, modo de conteúdo, quantidade de Stories, fonte, escala e cores.
- O posicionamento de legenda é planejado para evitar rostos, boca e GC/lower-third; o Curator deve recalcular a safe-area depois do crop/câmera real.

Artefatos novos:

```text
stories_manifest.json
stories_candidates.json
caption_style_recommendations.json
title_suggestions.json
social_render_profiles.json
STORIES_PACKAGE/
```

O pacote de segunda curadoria também inclui `social/` com o mesmo contrato, para que candidatos promovidos pela segunda curadoria possam receber estilo/render sem nova inferência pesada.

### Integridade editorial + identidade visual — R4.2-INTEGRITY-VISION

Esta revisão mantém a versão lógica/cache `4.4.0` e endurece o caminho crítico sem invalidar ASR/visão/semântica por nome de build.

- `Semantic -> Understanding` valida campos aninhados conhecidos e grava `understanding_contract_diagnostics.json` com o caminho exato de qualquer normalização.
- Falha em `16_understanding` passa a bloquear publicação/Stories (`PROVISIONAL_UPSTREAM_INCOMPLETE`) em vez de deixar o downstream parecer editorialmente pronto.
- `eligibility=excluded` é invariável: nunca pode aparecer como shortlist/Story elegível.
- Commercial Gate usa contexto limitado para propagar um bloco publicitário apenas quando o próprio candidato já traz múltiplos sinais comerciais precursores; discussão neutra de marca continua permitida.
- Micro-tracklets com embedding facial podem reentrar em identidade já estabelecida somente com threshold/margem mais estritos e sem conflito temporal; posição de tela continua proibida como prova de identidade.
- Smart Zoom passa a medir oportunidades, pedidos, eventos aceitos, entregues, abortados e razões de bloqueio.

A melhoria de micro-ReID é conservadora e precisa ser medida no benchmark real antes de qualquer claim de ganho de cobertura.

### Observabilidade visual/transcrição — R4.1-SOCIAL-OBS

- `06_scenes` passa a aparecer como **Cenas visuais**; `Shot classification` continua sendo a etapa posterior de classificação de shot.
- O artefato registra `scene_metrics`, distinguindo explicitamente **quantidade de cenas** de **quantidade de cortes/limites visuais**. N cortes produzem N+1 cenas.
- Também registra densidade de cenas por janelas de 10 minutos e sinaliza regiões extremamente picotadas para contextualizar fragmentação do tracking.
- `partial` na GUI passa a ser exibido como **Parcial**, enquanto `degraded` continua **Degradado**.
- A transcrição parcial mostra resumo quantitativo (`needs_review`, baixa confiança, anomalias de timestamp e regiões suspeitas) em vez de um aviso genérico.
- A revisão não altera a versão lógica `4.4.0`; build `R4.1-SOCIAL-OBS` preserva a estratégia de cache seletivo.

### Checkpoint Rodada 2 — R4.3-VISUAL-ID-R2

Busca facial complementar conservadora para micro-tracklets que o indice de buckets nao recupera. Veja `docs/ROUND2_VISUAL_IDENTITY.md`. Sem full-run nesta revisao.


## Visual Identity R2 concluída / R3 diagnósticos (outubro 2026)

A etapa `08_person_reid` passa a conferir vizinhos faciais exatos nos
*micro-tracklets* e faz recuperação estrita dos *tracklets* estáveis não
associados pelo índice rápido. A margem considera identidades concorrentes;
conflito temporal bloqueia associação, e uma única amostra facial exige
cosine >= 0.86. Nunca há merge apenas por posição. Os parâmetros
`micro_reid_threshold` e `micro_reid_margin` são incluídos no contrato da
etapa (e no hash de cache). `09_person_motion`, `10_active_speaker`,
`11_shots` e `12_camera_timeline` bloqueiam na falha do Re-ID.

Replay offline (sem refazer vídeo ou GPU):

```powershell
python scripts/dev/replay_visual_identity_r2.py 'C:\caminho\files.zip' --output 'C:\caminho\reid_replay.json'
```

Medir gargalos e estimar limites conservadores de trabalhadores, **sem
ativar concorrência**:

```powershell
python scripts/dev/performance_diagnostics_r3.py --stage-runtime 'C:\caminho\performance_summary.json' --camera-summary 'C:\caminho\camera_summary.json' --output 'C:\caminho\r3_advisor.json'
```

As recomendações não equivalem a performance comprovada. Um replay de
Re-ID com o checkpoint real não valida identidade civil, acerto de câmera,
`active speaker` nem segurança de recorte. O ganho real exige benchmark
downstream e, posteriormente, um vídeo anotado de referência.

## R4.9/S5 — Speaker/Person e Active Speaker

A identidade global de uma pessoa e a confirmação de que ela fala **naquele instante** agora são explicitamente diferentes. O foco de câmera S5 prioriza `active_person` com sincronismo temporal, não apenas `person_id`. Veja [`docs/S5_SPEAKER_PERSON_ACTIVE_20261007.md`](docs/S5_SPEAKER_PERSON_ACTIVE_20261007.md). Para revisão offline, use `python scripts/dev/audit_speaker_s5.py ANALISE --output PASTA_S5`.

## R4.9/S7 — Transcrição, Targeted ASR e legendas (2026-10-07)

O Targeted ASR prioriza aberturas/desfechos de cortes selecionados e explicita orçamento/cobertura; novas hipóteses não substituem o áudio/transcript original. `17e_subtitle_review_s7` fornece pendências, SRT **rascunho** e CSV de revisão humana por corte. A seleção automática de karaokê passa a exigir texto **e alinhamento** verificados; caso contrário, o preset efetivo é legenda simples. Auditoria offline e importação de revisão humana em `scripts/dev/audit_subtitles_s7.py`. Consulte `docs/S7_TRANSCRICAO_REPARACAO_LEGENDAS_20261007.md`.

## Atualização R4.9 / Sessão 8 — Commercial Gate e Stories

Incremental sobre S7: blocos comerciais por evidência temporal, revisão para ofertas vistas apenas no OCR, Broadcast Graphics/Commercial Visual com estados de execução honestos, títulos apoiados na transcrição, Stories distribuídos no vídeo e zonas provisórias de GC/legendas/overlays. **Não infere persistência de texto observado em um frame.** O áudio de risadas por PANNs e o Tesseract são opcionais (desligados no padrão). Veja `docs/S8_COMMERCIAL_GRAPHICS_STORIES_20261008.md`.

Auditoria offline sem repetir mídia: `python scripts/dev/audit_commercial_stories_s8.py <PASTA_ANALISE_OU_ZIP> --output <PASTA_REVISAO>`.
