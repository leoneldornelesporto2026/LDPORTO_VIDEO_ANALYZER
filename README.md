> **V4.2:** [relatorio atual](docs/V4_2_IMPLEMENTATION_REPORT.md), [matriz](docs/V4_2_REQUIREMENT_MATRIX.md),
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
