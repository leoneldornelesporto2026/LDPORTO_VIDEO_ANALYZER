# L.D.PORTO VIDEO ANALYZER / Perception Engine

Aplicação local para analisar vídeo, preservar a fala original e produzir evidências
para revisão editorial e segunda curadoria. Integra ASR, diarização, visão, OCR,
semântica, planejamento de câmera, previews e exportação com referências verificáveis.
Identidades visuais são anônimas; resultados incertos permanecem explícitos.

## Ambiente

O alvo é Windows 10/11 e Python 3.11.x, com Tcl/Tk para a GUI. Utilize a `.venv`
existente. A base está em `requirements.txt`; grupos opcionais estão em
[requirements/README.md](requirements/README.md). FFmpeg e FFprobe precisam estar
disponíveis. A configuração compartilhada fica em `config/config.yaml`.

Em uma instalação nova, execute `INSTALAR_WINDOWS.bat` e, quando necessário,
`INSTALAR_AVANCADO_WINDOWS.bat`. Esses comandos alteram o ambiente quando acionados
pelo usuário; não fazem parte da regressão. Pesos e credenciais não são versionados.
Diarização Community-1 requer acesso ao modelo; o token da GUI permanece em memória.
Para uso offline, prepare previamente os modelos necessários.

## Iniciar e diagnosticar

Abra `ABRIR_ANALYZER.bat` ou execute no PowerShell:

```powershell
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe analyze.py --help
.\.venv\Scripts\python.exe analyze.py --doctor --offline
```

O diagnóstico verifica recursos configurados; não comprova inferência audiovisual.
YOLO usa checkpoint **local `.pt`**, tarefa `detect`, classe 0 `person`.
Configure `vision.body_backend`, `vision.yolo_model` e `vision.yolo_device` conforme
[YOLO local](docs/YOLO_LOCAL_57.md). Sem modelo válido, o fallback HOG e a qualidade
degradada são declarados. Diagnóstico e `--help` não devem baixar pesos.

Ollama é local, em loopback. O perfil `max` conserva seu orçamento original;
consulte [configuração Ollama](docs/setup/OLLAMA_MAXIMO.md). A falta de um recurso
habilitado aparece no preflight. Desabilite-o explicitamente quando adequado.

## Analisar

Na GUI, selecione a entrada e os recursos, acompanhe as etapas e abra os resultados.
Para iniciar uma análise explicitamente pela CLI:

```powershell
.\.venv\Scripts\python.exe analyze.py 'C:\Videos\entrevista.mp4' --offline --output analysis/minha_analise
.\.venv\Scripts\python.exe analyze.py 'C:\Videos\entrevista.mp4' --semantic ollama --ollama-model qwen3:14b --ollama-profile max
```

A detecção de idioma é automática por padrão; `language: pt` ou `en` é uma escolha
explícita para fontes conhecidas. ASR usa `transcribe`. Traduções ficam separadas da
fala original; alternativas, proveniência e incertezas acompanham os artefatos.
Idioma detectado para um bloco não comprova o idioma de cada palavra desse bloco.
Revisões acústicas seletivas têm limites de chamadas e segundos de áudio.

A interrupção da GUI solicita parada na próxima unidade segura e preserva checkpoints.
Replays seletivos reutilizam artefatos validados:

```powershell
.\.venv\Scripts\python.exe analyze.py --director-only analysis/minha_analise
.\.venv\Scripts\python.exe analyze.py --replay-analysis analysis/minha_analise --from-stage understanding
```

## Resultados e exportação

`analysis/` contém relatórios HTML/Markdown, transcrição, palavras, alternativas,
traduções separadas, decisões de câmera e manifestos. `analysis.json` usa referências
com SHA-256; o leitor valida caminhos e checksums. Pacotes destinados à segunda
curadoria ficam em `pacotes_para_enviar/`. Preserve os artefatos de cada referência.

```powershell
.\.venv\Scripts\python.exe exportar_ldporto.py --help
.\.venv\Scripts\python.exe exportar_ldporto.py --inspect-zip 'PACOTE.zip'
.\.venv\Scripts\python.exe compare_runs.py OLD NEW --output-dir comparison
```

`PARTIAL`, `READY_FOR_REVIEW`, `PREVIEW_APPROVED` e `PUBLISH_READY` são estados
separados. Pacote íntegro não comprova qualidade nem aprovação humana. O Analyzer
não publica automaticamente. Instrumental autoral, marcas d'água, áudio musical
original e exportação vertical permanecem no fluxo editorial/renderização, conforme
[segunda curadoria](docs/V4_SECOND_CURATION.md) e [áudio](docs/AUDIO_AVANCADO.md).

## Desenvolver e testar

Trabalhe diretamente com Git, alterações incrementais e testes. Preserve mudanças
preexistentes, dados locais, modelos e segredos. Não há commits automáticos.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_transcription_fidelity.py
```

A regressão é offline e usa mocks, fixtures históricas e canários sintéticos.
Ela não homologa Whisper, YOLO, diarização ou Qwen em conteúdo real.
O baseline `2f4634f` e **1627 passed / 4 skipped** são referências históricas
fornecidas; resultados atuais ficam no
[relatório da reestruturação](docs/reports/restructuring_20261012/RELATORIO_TECNICO.md).

## Estrutura e documentação

| Caminho | Responsabilidade |
| --- | --- |
| `app.py`, `analyze.py` | GUI e CLI públicas |
| `src/ldporto/` | Engines, pipeline, contratos e exportação |
| `src/tests/`, `src/tests/fixtures/` | Regressão e evidências com proveniência |
| `scripts/windows/`, `scripts/dev/`, `scripts/export/` | Ferramentas por finalidade |
| `requirements/`, `config/`, `schemas/` | Dependências, configuração e contratos |
| `docs/` | Guias ativos e índice por finalidade |
| `docs/reports/`, `docs/archive/`, `docs/briefings/` | Auditorias, histórico e requisitos |
| `models/`, `input/`, `analysis/`, `pacotes_para_enviar/` | Dados locais protegidos, fora do Git |

Consulte o [índice de documentação](docs/README.md), a
[arquitetura](docs/ARQUITETURA.md) e a [estrutura existente](docs/REPOSITORY_STRUCTURE.md).
Caminhos públicos e módulos foram preservados para evitar migrações cosméticas.

Limitações: HOG perde pessoas sentadas/ocultas; qualidade facial e sincronismo limitam
Active Speaker; identidade pode permanecer `null`; câmera preserva a fonte sem ganho
e evidência suficientes. Vídeos curtos podem não produzir shortlist. ASR, LLM e
scores editoriais não são fatos garantidos. Ganhos reais de qualidade e latência
exigem homologação comparável documentada.
