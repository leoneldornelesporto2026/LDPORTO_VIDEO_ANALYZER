# Entrega automática Analyzer → Curator (contrato 1.0)

Implementação apenas na branch develop do LDPORTO_VIDEO_ANALYZER.
Evento de integração: ReportEngine.run, após a validação do estágio 21_second_curation_handoff
e após finalize_report_receipt, sem reabrir/editar o ZIP oficial.

## Localização

- Default: repositório irmão LDPORTO_VIDEO_CURATOR, sem caminho absoluto fixo.
- Alternativa: export.curator_delivery_root em config.yaml ou variável de ambiente LDPORTO_VIDEO_CURATOR_ROOT.
- Desabilitar explicitamente: export.curator_delivery_auto: false.
- Entrega: <Curator>/input/analyzer/<video_id>/<run_id>/.
- Colisão de mesmo run_id e hashes distintos: pasta <run_id>--sha-<12 hex>.
- O Curator deve conter .gitignore e ldporto_studio/core.py. `input/analyzer/`, `input/curadorias/` e `input/videos/` ficam ignorados; `input/README.md` e `input/scripts/` podem aparecer no Git.

## Segurança

O exportador oficial build_core_package e validate_core_package continuam únicos.
O módulo local_curator_handoff valida novamente ZIP e SHA256 antes/depois da cópia.
Copiar para pasta temporária e renomear a pasta inteira quando completa.
Nenhuma entrega anterior é sobrescrita. Um ZIP já entregue e conferido é idempotente.
Falhas produzem curator_delivery.json em analysis/<run>, com DELIVERY_BLOCKED.
O ZIP original e os vídeos não são removidos ou modificados.

A entrega é de evidências, NÃO é formato R57 do Studio atual.
O Curator recebe ANALYZER_TO_CURATOR_HANDOFF.json e README_HANDOFF.md.
O importador continua CURATOR_IMPORT_PENDING. Nenhuma aprovação ou render foi criada.
Metadados só são transportados quando presentes no contrato canônico; faltas ficam nulas.

## Testes

Executar no Analyzer:

~~~powershell
git status --short
git pull --ff-only origin develop
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_local_curator_handoff.py
.\scripts\windows\testing\VALIDAR_P0_GUI.ps1
~~~

Executar no Curator após pull da develop:

~~~powershell
python -m unittest discover -s tests -p test_analyzer_inbox.py -v
python -m ldporto_studio.analyzer_inbox --path ".\input\analyzer\<video_id>\<run_id>"
~~~

Para retentar uma entrega bloqueada sem rodar inferência, executar:

~~~powershell
.\.venv\Scripts\python.exe scripts/dev/retry_curator_delivery.py --analysis-dir "analysis\video_<id>"
~~~

Não é possível homologar entrega física em um computador Windows externo sem executar uma análise ou
reusar um ZIP original validado. Testes sintéticos de transporte não homologam conteúdo real.

## Gate integrado Windows

Na raiz do Analyzer, com ambos repositorios atualizados em develop:

~~~powershell
.\scripts\windows\testing\VALIDAR_ENTREGA_CURATOR.ps1
~~~

Para reutilizar um ZIP oficial ja exportado, sem inferencia de video:

~~~powershell
.\scripts\windows\testing\VALIDAR_ENTREGA_CURATOR.ps1 -AnalysisDir ".\analysis\video_<id>"
~~~

Opcional: -CuratorRoot aponta para o repo existente fora da pasta irma.
O script recusa outras branches, verifica que os ZIPs do Analyzer e os vídeos em `input/` são ignorados pelo Git, tolera `input/README.md` e os roteiros em `input/scripts/`, e bloqueia arquivos brutos indevidamente rastreados.
Sinteticos nao sao entrega fisica; somente -AnalysisDir faz copia real e verifica SHA no Curator.

## Confirmação na GUI e no CLI

O Analyzer exibe a confirmação de pacote entregue somente quando a cópia recebeu
DELIVERED ou ALREADY_DELIVERED. Inclui vídeo, ZIP, SHA256, destino, contagens
e CURATOR_IMPORT_PENDING. Erros geram DELIVERY_BLOCKED com o motivo,
sem eliminar o ZIP original do Analyzer.

## Evidência recebida — execução Windows em 2026-11-05

**Baseline histórica executada:** Analyzer `36bdfbb` (`develop`), Curator `69e5e43` (`develop`). A configuração do Git e do diretório `input/` mudou depois; requer nova execução do gate atualizado.
**Ambiente:** Windows, Python 3.11.9, pytest 9.1.1.

| Etapa | Resultado |
| --- | --- |
| Integração Analyzer (`test_local_curator_handoff.py`) | 18 passed, 1 skipped (criação de symlink no Windows) |
| P0-01 GUI | 15 passed |
| P0-02 shell | 6 passed |
| P0-03 mídia | 8 passed |
| P0-04 perfis | 11 passed |
| Fixture LF | 6 passed |
| Regressão GUI | 39 passed + 14 subtests passed |
| Inspetor Curator (`test_analyzer_inbox.py`) | 3 passed |

**Total não duplicado no gate:** 106 testes passaram, 14 subtestes passaram, 1 teste
ignorado, 0 falhas. `VALIDAR_ENTREGA_CURATOR.ps1` terminou com mensagem
'Gates concluidos. Nenhum render ou aprovacao humana foi acionado.'

**Atenção:** a validação executada foi exclusivamente automática e sintética;
o operador não forneceu `-AnalysisDir`. Portanto **não há evidência ainda** de que um
ZIP oficial de análise real tenha sido copiado para `input/analyzer/<video_id>/<run_id>/`.
Não registrar DELIVERY_SUCCESS nem CURATOR_IMPORT_SUCCESS para uma entrega física
antes do recibo e inspeção no Windows.

**Próximo gate físico:** localizar `second_curation_export.json` de uma análise
existente (no diretório `analysis/`), conferir a existência do ZIP oficial e executar:

~~~powershell
.\scripts\windows\testing\VALIDAR_ENTREGA_CURATOR.ps1 -AnalysisDir "<pasta-real-da-analise>"
~~~

Depois verificar `curator_delivery.json`, conferir SHA256 e o resultado do inspetor
`ldporto_studio.analyzer_inbox` no Curator. Mesmo com `DELIVERED`, o estado editorial
permanece `CURATOR_IMPORT_PENDING` até adaptador R57 validado.

A alteração local em `src/tests/fixtures/stage55_commercial_synthetic.json`
foi preservada no Windows; não executar `git reset --hard` ou descarte automático.

## Insumos completos por vídeo — escopo da etapa P0

O ZIP oficial entregue ao Curator contém os **artefatos canônicos exportáveis** disponíveis: metadados da fonte (ID/título/URL, duração, SHA256), transcrição original e segmentos/palavras, catálogo e shortlist de candidatos, propostas de Stories, observações de pessoas, câmera/zoom, áudio, evidências visuais/OCR, prévias e verificações **quando de fato produzidos**. O `SECOND_CURATION_MANIFEST.json` dentro do ZIP lista os membros e hashes; o `HANDOFF_MASTER.json` vincula IDs e referências. O validador bloqueia ZIP com membros inseguros/inconsistentes. Arquivos brutos temporários de inferência, modelos e o MP4 original **não estão incluídos** por padrão.

Diretório por execução:

```
LDPORTO_VIDEO_CURATOR/input/analyzer/<video_id>/<run_id>/
    SECOND_CURATION_*.zip
    ANALYZER_TO_CURATOR_HANDOFF.json
    README_HANDOFF.md
```

O caminho `input/videos/` é reservado aos vídeos baixados/associados pelo Curator e está inteiramente ignorado no Git. Nenhum material audiovisual é commitado.

**Critério de fechamento P0:** uma análise REAL já exportada deve passar por `VALIDAR_ENTREGA_CURATOR.ps1 -AnalysisDir <pasta-da-analise>`, conferir ZIP/manifesto SHA256 original e cópia, ler o ZIP pelo Curator e confirmar `DELIVERED`/`ALREADY_DELIVERED` e `CURATOR_IMPORT_PENDING`. Não afirmar homologação física apenas com testes sintéticos.

### Inventário integral e fronteira de mídia

O novo arquivo `VIDEO_EVIDENCE_INDEX.json` acompanha cada entrega nova. Ele enumera **todos os membros do ZIP oficial validado**, com nome, categoria, tamanho, SHA256, identificação do vídeo e da execução, e `missing_review_references` para evidências opcionais não disponíveis. É um catálogo auditável, **não uma cópia descompactada**; o material continua em um ZIP íntegro e imutável. O recibo registra o SHA256 do índice. O Curator confere esse vínculo, mantendo suporte a entregas legadas sem índice.

**Limite de escopo:** o Analyzer exporta evidências canônicas suficientes para a segunda curadoria; os arquivos de modelos, mídia original e artefatos temporários/brutos fora do pacote canônico não são copiados. A mídia original continua separada do handoff e pode ser obtida/associada pelo Curator em `input/videos/`. Um pacote complementar opcional de prévias, quando gerado pelo Analyzer (`media_path`), também **não faz parte da entrega automática atual**; essa extensão exige contrato e homologação específicos. Não anunciar que esses arquivos extras chegaram quando não chegaram.

A entrega completa de **evidências incluídas no ZIP** é atestada apenas após o ZIP e o índice passarem no inspetor do Curator. Isso não atesta processamento editorial, aprovação ou renderização.

## Piloto E2E real Windows — sem dados no GitHub

O script `scripts/windows/testing/PILOTO_E2E_REAL.ps1` valida as **etapas já implementadas**, sem falsear um render R57: execução REAL do Analyzer a partir de um vídeo YouTube autorizado, ZIP canônico, entrega física validada no Curator, smoke R6 com 1–5 IDs gerados apenas para teste, relatório de mídia por SHA256, evidência final no diretório de análise. Pode reutilizar análise existente sem reprocessamento.

**Condições:** Windows PowerShell 5.1, Python Analyzer 3.11 em `.venv`, Curator irmão em `develop`, vídeo com direitos de processamento, dependências FFmpeg/modelos conforme `--doctor`, espaço em disco e conexão apenas quando explicitamente autorizada. O script não instala dependências, não executa Git pull/commit/push, não altera branches. Ele bloqueia download implícito. Quando o vídeo é fornecido por URL e você deseja autorização explícita de baixar, informe `-AllowDownload`; para mídia local já disponível, use `-MediaPath`. O SHA256 local será vinculado à URL pelo Analyzer.

### Novo vídeo (pode baixar apenas com consentimento explícito)

```powershell
cd "C:\Users\leone\Documentos\Meus Projetos\LDPORTO_VIDEO_ANALYZER"
& .\scripts\windows\testing\PILOTO_E2E_REAL.ps1 -SourceUrl "https://www.youtube.com/watch?v=ID_DO_VIDEO_AUTORIZADO" -AllowDownload
```

### Vídeo do YouTube já salvo no Windows (recomendado: evita download duplicado)

```powershell
& .\scripts\windows\testing\PILOTO_E2E_REAL.ps1 -SourceUrl "https://www.youtube.com/watch?v=ID_DO_VIDEO_AUTORIZADO" -MediaPath "C:\CAMINHO\VIDEO_ORIGINAL.mp4"
```

### Repetir entrega e consumo sem nova inferência

```powershell
& .\scripts\windows\testing\PILOTO_E2E_REAL.ps1 -AnalysisDir ".\analysis\PILOT_OUTPUT_REAL"
```

**Gates e evidências:**

1. Regressão focal Analyzer/Curator antes de processar mídia; falha interrompe a execução.
2. Análise real com checkpoints e saída nova em `analysis/pilot_e2e_<timestamp>/`; ZIP oficial validado. A análise pode ser `partial`, sem falso "sucesso editorial".
3. Gate integrado Windows físico `VALIDAR_ENTREGA_CURATOR.ps1 -AnalysisDir`: destino `Curator/input/analyzer/<video_id>/<run_id>/`, recibo de entrega e hashes. `ALREADY_DELIVERED` é idempotência, não corte renderizado.
4. `r6-smoke` automático: 2 IDs distintos por padrão, JSON de teste em `Curator/output/r6_smoke/`, `render_ready=false`, `human_approved=false`.
5. `r6-media-audit`: procura mídia em locais locais gerenciados. Com `-MediaPath` também verifica esse arquivo explicitamente. Sempre exige SHA256 igual para considerar a fonte exata. O relatório local fica em `Analyzer/analysis/pilot_e2e_*/PILOT_E2E_REPORT.json`.

**Critério P0/P1:** recibo `DELIVERED` ou `ALREADY_DELIVERED`, inspetor `VALID`, smoke de candidatos reais `SMOKE_PASSED_WITH_PENDING_HUMAN_REVIEWS`, relatório com os SHAs e `render_ready=false`. Se não houver dois candidatos sem sobreposição, o teste falha honestamente; `-SmokeCount 1` testa um só. Não inventar Stories nem ignorar `publication_eligible_false`.

**P2 pendente:** associação de vídeo ao motor de prévias, adaptador verdadeiro R6 -> contratos/ativos do renderizador R57, vídeo curto de teste, inspeção de áudio/câmera/legendas, render final condicionado a aprovação. Um piloto P0/P1 PASSOU não é homologação E2E até o MP4 final. Se a auditoria encontrar mídia alternativa com SHA diferente, não liberar os timestamps automaticamente.

**Análises textuais no Git (nova opção revisável):** o Git continua protegendo o ZIP R6, MP4 original, diretórios `analysis/`, capturas, prévias e renders. Contudo, após revisão de conteúdo/confidencialidade e comando explícito, `scripts/dev/export_r6_git_review.py` prepara em `docs/analyzer_runs/<video_id>/<run_id>_<sha>/` **todos os membros textuais do ZIP canônico** (inclusive transcrições SRT e JSONL, evidências editoriais/câmera e hashes). Binários aparecem apenas no manifesto. Os arquivos textuais podem ser commitados manualmente; o exportador não faz `git add`, `commit` ou `push`. Consulte `.docs/integrations/ANALYZER_R6_GIT_EVIDENCE.md`. Nunca executar `git add -f` sobre os diretórios brutos.

## Piloto de duas suítes COMPLETAS + vídeo curto real sem mudar defaults

Novo controlador para PowerShell 5.1: `scripts/windows/testing/PILOTO_FULL_DEFAULTS.ps1`.

**Vídeo padrão:** NASA Johnson, "Space to Ground: Flight Test: June 14, 2024" (~2m38s), `https://www.youtube.com/watch?v=Eo2bUJcxASI`. Publicado pelo centro Johnson da NASA, com apresentação falada, mudanças de imagem e áudio. Uso exclusivamente para homologação local; não significa autorização para publicar derivados, usar marcas da NASA ou material de terceiros. Consulte `https://www.nasa.gov/nasa-brand-center/images-and-media/`. Para escolher outra fonte autorizada, informe `-SourceUrl`.

**Uma execução de homologação:**

```powershell
cd "C:\Users\leone\Documentos\Meus Projetos\LDPORTO_VIDEO_ANALYZER"
& .\scripts\windows\testing\PILOTO_FULL_DEFAULTS.ps1 -AllowDownload
```

Caso já tenha o arquivo **original**, evitando novo download:

```powershell
& .\scripts\windows\testing\PILOTO_FULL_DEFAULTS.ps1 -MediaPath "C:\CAMINHO\ORIGINAL.mp4"
```

O controlador faz: (1) Analyzer: gate oficial `VALIDAR_P0_GUI.ps1 -FullSuite` com fixtures históricas e `pytest -q src/tests` integral (não só smoke); (2) Curator: `unittest discover -s tests -p test_*.py -v` integral, com os testes FFmpeg (o comando bloqueia se FFmpeg/FFprobe faltarem); (3) execução **real** do vídeo curto com os valores de `config/config.yaml` atuais, sem flags que desabilitem visão/diarização, sem mocks, sem `--force`; download opt-in; (4) ZIP validado e cópia atômica na caixa de entrada `Curator/input/analyzer/<video_id>/<run_id>`, via o gate físico já conhecido; (5) Curator: seleção técnica real R6, conferência do SHA256 do vídeo (arquivo original do **Analyzer** reaproveitado por caminho local, sem recodificar ou copiar), e prévia de até seis segundos com áudio e imagem, salva em `Curator/output/r6_preview_smoke/`.

O hash de `config/config.yaml` é comparado antes/depois. O relatório local final é `Analyzer/analysis/pilot_e2e_*/PILOT_FULL_DEFAULTS_REPORT.json`. Suítes falhas **interrompem** a cadeia antes de mídia. Se a análise real vier sem candidatos ou falhar por dependência/modelo, o piloto falha sem inventar resultados. Se a mídia não tiver o SHA256 exato da fonte analisada, a prévia é bloqueada.

**Limite:** trata-se de E2E da infraestrutura até uma **prévia técnica de teste**, e NÃO de entrega do primeiro Reel R57 definitivo, legenda revisada ou publicação. O Curator ainda requer adaptador R6 para o contrato editorial R57, render completo por corte, revisão de música/voz/câmera/legenda, confirmação humana e direitos. O teste de prévia não atribui elegibilidade nem altera projetos R57. Não enviar análise bruta, MP4, ZIPs ou renders a Git; esses arquivos ficam sob diretórios `analysis/`, `input/` e `output/` ignorados. Apenas código/testes/docs sob `develop`; não há merge/push pelo script.


### Recuperação das fixtures históricas no Windows — bloqueio do piloto completo

A suíte completa preserva a integridade histórica dos ZIPs `CHATGPT_REVIEW.zip` (26.956.533 bytes, SHA256 `5a9da201f984d63de2c68dbd9aee4c03365b9e0815b1fb041130d4da02b5f073`) e `SECOND_CURATION_READY.zip` (1.864.261 bytes, SHA256 `8339e90f41cce13f93bc61cc6417cecc1058ad37df272d194d7f62060d860349`).

Quando faltam, o operador `PILOTO_FULL_DEFAULTS.ps1` chama o restaurador **já existente** `RESTAURAR_FIXTURES_HISTORICAS.ps1`, procurando automaticamente cópias originais dentro da pasta irmã dos repositórios, sem extrair/reconstruir ZIPs. Só copia um arquivo se o **tamanho e o SHA256** forem exatamente os registrados em `src/tests/fixtures/historical_evidence/ORIGEM.json`. Antes de executar a suíte completa, confere novamente as duas provas. Um ZIP divergente **nunca** é considerado fixture aceita.

Uso padrão:

```powershell
& .\scripts\windows\testing\PILOTO_FULL_DEFAULTS.ps1 -AllowDownload
```

Se os originais estiverem em outra pasta de backups, informar a raiz onde a busca deve ocorrer:

```powershell
& .\scripts\windows\testing\PILOTO_FULL_DEFAULTS.ps1 -AllowDownload -FixtureSearchRoot "C:\CAMINHO\BACKUPS"
```

O vídeo real **não inicia** enquanto qualquer fixture estiver ausente/divergente ou enquanto uma das duas suítes completas falhar. O script não instala dependências nem cria artefatos falsos, e preserva todos os outputs do piloto anterior. Se não houver os ZIPs originais em nenhuma pasta, o bloqueio deve ser documentado como `FIXTURE_HISTORICA_INDISPONIVEL`; procurar os backups legítimos em vez de desabilitar testes ou modificar os hashes.


### Piloto com baseline atual, quando os dois ZIPs históricos não estão disponíveis

**Uso excepcional e explicitamente nomeado — não é homologação da suíte histórica completa.** O operador `PILOTO_FULL_DEFAULTS.ps1` aceita a opção `-CurrentBaselineWithoutHistoricalFixtures`. A opção nunca fabrica, altera ou re-hash ZIPs históricos. Com o switch, caso as fixtures históricas estejam ausentes, a validação de existência/hashes segue reportada como pendente, e somente **sete testes identificados individualmente** (o teste de proveniência e os seis testes que dependem dos ZIPs históricos) são desmarcados no modo de baseline atual; nenhum arquivo de testes inteiro é excluído.

```powershell
& .\scripts\windows\testing\PILOTO_FULL_DEFAULTS.ps1 -AllowDownload -CurrentBaselineWithoutHistoricalFixtures
```

Sequência de execução: (1) checar fixtures presentes e bloquear bytes divergentes; (2) executar `VALIDAR_P0_GUI.ps1` focal e `pytest -q src/tests` com **sete argumentos `--deselect=<nodeid>` exatos, registrados em log e no relatório**, ou a suíte histórica **sem exceção** se ambos os ZIPs estiverem presentes; (3) executar a **suíte integral** do Curator; (4) analisar vídeo curto real com `config/config.yaml` intacto; (5) transferir ZIP R6, verificar o SHA original e gerar prévia técnica de 6 segundos, sem publicação.

O relatório `PILOT_FULL_DEFAULTS_REPORT.json` distingue `historical_full_suite_passed` de `suite_analyzer`, lista `deselected_tests`, e usa `CURRENT_BASELINE_AND_REAL_TECHNICAL_PREVIEW_PASS_HISTORICAL_PENDING` somente quando todas as etapas efetivamente rodarem sem erros, mas as fixtures históricas permanecerem ausentes. A referência anterior `FULL_SUITES_AND_REAL_TECHNICAL_PREVIEW_PASS` permanece restrita ao caminho completo com provas originais.

**Importante:** se outros testes falharem por dependência, execução, fixtures adicionais ou defeitos reais, a regressão atual também falha e o vídeo não inicia. Se qualquer ZIP presente apresentar SHA/tamanho errado, o processo bloqueia; nunca aceita um arquivo divergente. Nenhuma branch de produção, mídia ou dado de cliente é enviado ao Git. Esse caminho é útil para testar a integração atual sem confundir progresso técnico com aceite histórico.


**Evidência Windows em 06/11/2026:** com apenas um dos sete testes desmarcado, o Analyzer apresentou **2.692 testes aprovados, seis falhas exclusivamente por ausência dos dois ZIPs, seis skipped, um deselected**. A baseline atual desmarca agora os sete casos comprovadamente dependentes desses arquivos: o de proveniência, um de diagnósticos S4, três de replay S17, um de auditoria S18 e um de palavras incertas S19. O total de testes restantes não é declarado PASS antes de nova execução no Windows. Nenhum estado de publicação ou render é liberado por esse tratamento.

### Retomar o video real apos suites aprovadas no Windows (PowerShell 5.1)

Em 06/11/2026 as suites passaram em **Analyzer `751ac18`** (2.693 passed, 6 skipped, 7 históricos deselected, 39 subtests) e **Curator `70c3c71`** (94/94). A execucao parou antes de iniciar o YouTube por um defeito de *parameter binding* ao usar array splatting `& $pilot @pilotArgs`: no PowerShell 5.1, os elementos `"-SourceUrl"` e `"-SmokeCount"` foram tratados como argumentos posicionais. O controlador agora chama `PILOTO_E2E_REAL.ps1` usando os nomes reais dos parametros.

Nao precisa repetir todos os testes para diagnosticar o download e o processamento. A retomada **opt-in** segue os mesmos gates de fixtures e de SHA, mas verifica o commit exato do Curator, restringe mudancas do Analyzer desde `751ac18` a script controlador, teste de contrato e docs, bloqueia modificacoes locais de codigo/config e reexecuta os testes de contrato dos operadores. O suboperador continua executando testes **focais reais** antes de iniciar a inferencia.

```powershell
& .\scripts\windows\testing\PILOTO_FULL_DEFAULTS.ps1 -AllowDownload -CurrentBaselineWithoutHistoricalFixtures -ResumeAfterValidatedSuites
```

A opcao imprime que as suites foram **reutilizadas do log de execucao anterior**: nunca relata como se os 2.693 ou 94 testes tivessem rodado de novo. Um relatorio final de retomada, se a etapa do video e a previa passarem, usa o status `RESUMED_REAL_TECHNICAL_PREVIEW_WITH_PRIOR_SUITES_HISTORICAL_PENDING`, `suites_executed_nesta_invocacao=false` e `suites_retoma_com_evidencia_anterior=true`.

Para repetir a regressao integral da baseline atual, **omita** `-ResumeAfterValidatedSuites`. Se os commits ou arquivos criticos mudarem, a retomada aborta e exige novamente as suites. O teste historico integral permanece pendente ate recuperar as duas fixtures SHA256 originais; os downloads, registros e resultados de video permanecem locais (nao criar commit com MP4/ZIP).


### Incidente R6 real NASA — WinError 5 ao promover pasta temporária do Curator (06/11/2026)

Execução real em Windows 11, PowerShell 5.1, Analyzer `d913bb1`, Curator `70c3c71`: baseline atual Analyzer **2.693 passed, 6 skipped e 7 testes históricos pendentes**, Curator **94/94 PASS**, testes focais da retomada **19/19** e handoff focais **20 passed, 1 skipped**. Vídeo oficial NASA `Eo2bUJcxASI`, 158,654 s, mídia original identificada por SHA256 `2131f80ae982b4dc6e00c4b4a4dc86e38ee7a6bc5a676785715dde3f0d7ef634`. Etapas reais de transcrição, diarização, visão YOLO e Ollama foram executadas; resultado geral da análise `PARTIAL`, com avisos editoriais, não `READY`.

O Analyzer preservou o ZIP R6 `pacotes_para_enviar/SECOND_CURATION_PARTIAL_Eo2bUJcxASI_20261106_170203_379229_e70235.zip`, **3.863.207 bytes**, mas **NÃO entregou** ao Curator: houve `[WinError 5] Acesso negado` no `os.rename` da pasta temporária `.analyzer-pending-*` para `Curator/input/analyzer/Eo2bUJcxASI/2131f80ae982b4dc`. Duas tentativas independentes falharam da mesma forma. Não interpretar isso como falha do download, da inferência ou do ZIP. O log sozinho não distingue um bloqueio temporário de um ACL/antivírus/política de segurança persistente.

**Correção:** o handoff tenta renomeação atômica até **seis vezes** para os códigos Win32 5/32/33, com atraso limitado, verificando que ninguém criou o destino nesse intervalo; qualquer outro erro falha imediatamente. Nunca substitui um destino existente, modifica ACLs, desliga proteção, usa fallback não-atômico ou toca no ZIP original. Bloqueio persistente retorna `curator_atomic_directory_rename_denied:winerror=...`, sem fingir sucesso. Novos testes sintéticos cobrem retries, bloqueio permanente e disputa pelo mesmo nome.

**Diagnóstico isolado** no Windows: `scripts/windows/testing/DIAGNOSTICAR_RENAME_CURATOR.ps1`, que cria, renomeia e remove **somente suas próprias pastas temporárias com GUID** sob `input/analyzer/Eo2bUJcxASI`. Em caso de erro, verificar permissões do Windows e bloqueios de processos/proteção com o operador, sem executar comandos para contornar controles corporativos.

**Retomada segura, sem nova inferência nem download:**

```powershell
cd "C:\Users\leone\Documentos\Meus Projetos\LDPORTO_VIDEO_ANALYZER"
& .\scripts\windows\testing\RETOMAR_R6_NASA_SEM_REANALISE.ps1 -AnalysisDir ".\analysis\pilot_e2e_20261106_135438_190"
```

O operador executa o diagnóstico de rename, chama `PILOTO_E2E_REAL.ps1 -AnalysisDir` (somente regressão focal + reentrega validada, sem reprocessar vídeo), checa `PILOT_E2E_REPORT.json`, verifica a mídia original local do Analyzer com **SHA256 exato**, audita no Curator e cria **apenas uma prévia técnica de 6 segundos** em `output/r6_preview_smoke/`. Se o original não estiver no cache `input/youtube/<id>/download.json`, indique `-MediaPath "<original.mp4>"`; nunca usar um recode diferente como se fosse o original. O relatório local fica em `analysis/pilot_e2e_.../PILOT_RECOVERED_PREVIEW_REPORT.json`, com `publication_ready=false`. Se o diagnóstico persistir em `WinError 5`, não repetir a análise pesada nem aplicar ACLs/antivírus de forma automática.

**Status do incidente:** correção de código publicada, reentrega física e prévia ainda dependem de execução real no Windows. O motor editorial R6 → R57 e as revisões de câmera, legendas, áudio e direitos continuam pendentes.


### Contrato de retomada reforçado (06/11/2026)

O operador `RETOMAR_R6_NASA_SEM_REANALISE.ps1` agora normaliza `-MediaPath` relativo **antes** de mudar o diretório corrente para o Curator; quando informado, repassa o caminho absoluto ao gate P0/P1. O ZIP original é medido em bytes e SHA256 antes da tentativa e revalidado após o handoff e a prévia. O recibo P0/P1 também deve coincidir com o SHA256 inicial.

O relatório de sucesso exige que o MP4 exista fisicamente sob `Curator/output/r6_preview_smoke/`, não seja um reparse point, tenha extensão MP4, bytes e SHA256 idênticos aos do recibo do Curator. Metadados retornados pelo Curator devem declarar áudio, 360×640 e duração compatível com a amostra solicitada. A prévia pode ter **menos de seis segundos** se o intervalo do candidato for mais curto. O contrato não atesta verificação editorial, publicação ou Reels finais.

Esses controles são **adicionais** à validação da mídia original e ao FFprobe já executados pelo Curator. A verificação física do Windows 11 permanece necessária; testes sintéticos e revisão de código não autorizam declarar o incidente recuperado.


No piloto NASA, `media_resolution.origin=legacy_input` não implica a existência de `download.json`. Quando esse manifesto não existe, o operador consulta **somente** `Analyzer/input/youtube/<videoId>/<videoId>.{mp4,mkv,webm,mov}`, conforme o fallback legado do motor, e aceita apenas o arquivo que coincidir com o SHA256 do pacote R6. Não há busca recursiva, redownload ou aceitação por nome/duração isoladamente. `-MediaPath` explícito continua disponível para fontes em outros locais.


### Diagnostico Python de WinError 5 persistente (06/11/2026)

Se o probe simples `DIAGNOSTICAR_RENAME_CURATOR.ps1` permitir rename, mas a entrega do ZIP real continuar com `curator_atomic_directory_rename_denied:winerror=5;attempts=6`, executar **sem reanalise e sem retentar entregar**:

```powershell
& .\.venv\Scripts\python.exe scripts\dev\diagnose_curator_rename.py --analysis-dir ".\analysis\pilot_e2e_20261106_135438_190"
```

O diagnostico testa duas operacoes **Python `os.rename`** no mesmo diretorio do Curator: uma pasta com texto pequeno e outra com copia temporaria do ZIP original validado e SHA256 verificado. Ambas usam nomes novos aleatorios sob a inbox do video, sem tocar no destino definitivo. Nao ha mudanca de ACL, exclusao de entregas anteriores, desligamento de protecoes ou chamada ao Analyzer. O relatorio local `CURATOR_RENAME_DIAGNOSTIC_<id>.json` distingue: `RENAME_DENIED_FOR_BASIC_DIRECTORY`, `RENAME_DENIED_WITH_ZIP_PAYLOAD` e `TEMPORARY_PROBES_PASSED_REAL_HANDOFF_NOT_PROVEN`. O resultado classifica **apenas o que os testes fisicos demonstraram**, sem atribuir automaticamente a causa a Defender, antivirus, ACL ou processos concorrentes. Em falha de limpeza, os caminhos exatos dos artefatos pertencentes ao proprio diagnostico permanecem registrados para avaliacao humana. A suite sintetica nao substitui a execucao Win11.


### Probe P0 adicional: staging completo (06/11/2026)

O resultado real em Windows 11 demonstrou **17 testes focais PASS**, probes `text` e `zip` PASS, mas a entrega física posterior continuou `DELIVERY_BLOCKED` com `WinError 5` em seis tentativas. Portanto, nome de pasta, ACL, Defender e lock de processo ainda são hipóteses, não causas comprovadas.

O mesmo comando de diagnóstico agora inclui um terceiro probe, `full`. Ele usa o mesmo prefixo `.analyzer-pending-` e a mesma rotina de cópia, `fsync`, validação oficial do ZIP e geração de `VIDEO_EVIDENCE_INDEX.json`, `ANALYZER_TO_CURATOR_HANDOFF.json` e `README_HANDOFF.md` do handoff real. O recibo temporário é expressamente `DIAGNOSTIC_ONLY_NOT_AN_ACTUAL_HANDOFF`. A promoção é feita por **uma** chamada a `os.rename` para destino isolado com prefixo de diagnóstico; nunca para o nome canônico da entrega. O diretório de prova é removido ao encerrar e o ZIP original é revalidado.

Interpretações adicionais: `RENAME_DENIED_WITH_FULL_HANDOFF_STAGE` (bloqueio após montar os artefatos), `FULL_HANDOFF_STAGE_PREPARATION_FAILED` (falha antes de chamar o rename), ou `ALL_DIAGNOSTIC_PROBES_PASSED_REAL_HANDOFF_NOT_PROVEN` (todos os testes temporários passaram, mas a entrega definitiva ainda precisa ser investigada). Não alterar regras de segurança nem adicionar copy-fallback não atômico. Execute testes e depois o diagnóstico isolado; **não execute o piloto completo novamente antes de avaliar o JSON**.


### Matriz de isolamento P0 para WinError 5 (06/11/2026)

O probe `full` reproduziu o `WinError 5` real apesar de `text` e `zip` passarem. A versão 1.2 do diagnóstico acrescenta automaticamente uma matriz de **sete** experimentos **somente se o probe `full` falhar**. Todos usam o prefixo de staging da produção `.analyzer-pending-`, mas apenas destinos temporários de diagnóstico com identificadores aleatórios: `pending_empty`, `pending_text`, `pending_zip_copy`, `pending_zip_validate`, `pending_zip_index`, `pending_zip_receipt` e `pending_zip_readme`. Cada fase acrescenta uma operação e preserva a análise e o ZIP originais.

O resultado `matrix_first_failure` indica a primeira etapa *observada* com falha e **não comprova causalidade**. Se toda a matriz passar apesar de `full` falhar, investigar concorrência e intermitência. Nunca promover um resultado de diagnóstico como entrega, nunca alterar ACL/Defender e nunca substituir a renomeação atômica por cópia. Não executar o piloto completo antes de analisar a matriz.


### Correção proposta após isolamento: validação do ZIP fora da inbox (06/11/2026)

Matriz real Windows: `pending_zip_copy=PASS`, `pending_zip_validate=FAILED (WinError 5)` e falha nas etapas posteriores. O validador oficial usa `ZipFile.close()` em `finally`; isso não demonstra um handle Python vazado nem prova que o Windows Defender seja responsável. A coincidência entre a validação dentro do staging e a falha de rename justifica um teste de arquitetura com **validação isolada fora da pasta que será renomeada**.

O Analyzer mantém os controles originais: valida o pacote de origem, copia-o com `fsync` para o staging, exige hash SHA256 original == staging, cria um snapshot do **staging** fora da pasta Curator, exige SHA256 snapshot == original, executa o **mesmo** `validate_core_package` sobre o snapshot, remove-o e verifica novamente staging e original por SHA256. A geração do índice de evidências passa a ler o original (bytes comprovadamente idênticos) em vez de abrir o ZIP dentro do staging. Antes de publicar, os hashes do staging e original são repetidos. Renomeação continua **atômica**, sem fallback de cópia para a inbox, sem sobrescrever destinos e sem mudanças nas ACLs/Defender.

O probe `full` passa a testar esse novo comportamento. Os estágios históricos `pending_zip_validate` e seguintes continuam usando leitura direta no staging para distinguir o padrão anterior; falha nesses estágios não invalida automaticamente sucesso do novo probe full. Apenas os resultados físicos Win11 confirmarão se a mudança resolveu o bloqueio. O Curator só receberá R6 técnico; revisão editorial, R57 e publicação permanecem pendentes.


### Diagnóstico diferencial v1.3 — isolamento de leituras e pasta-pai

Em Windows 11, 52 testes focais passaram (1 SKIP), mas o terceiro probe `full` continuou com `WinError 5`, mesmo ao validar um snapshot fora da inbox. A matriz anterior `pending_zip_validate` **continua lendo o ZIP no staging**, logo seu resultado não permite atribuir a falha do `full` atualizado à mesma operação.

O diagnóstico v1.3 mantém os probes originais e, apenas se `full` falhar, executa quatro testes de leitura isolados usando ZIP e destino descartáveis: `rehash` (SHA repetido), `snapshot_copy` (cópia externa sem validação), `snapshot_validated` (validador oficial no snapshot externo) e `source_validated` (validador oficial no original). Acrescenta também `cross_parent_full_probe`: o mesmo staging completo, mas criado **na pasta-pai `input/analyzer` no mesmo volume**, com renomeação atômica para um destino temporário no diretório do vídeo. Se esse último passar e `full` falhar, o local do staging será candidato a mudança de arquitetura — não uma homologação automática. Não cria slot de entrega real nem modifica segurança, Git ou mídia original.

Resultados da matriz são observacionais: a primeira falha não prova a causa ou a identidade de um processo de segurança. A execução física da entrega definitiva continua pendente.


### Windows v1.4 — inspecao nao destrutiva do acesso DELETE

Quando um probe `full` ou de leitura falha na renomeacao, antes de limpar a pasta de prova consulta `CreateFileW` com acesso DELETE e compartilhamento de leitura/escrita/exclusao sobre a propria pasta e sobre o ZIP, fechando imediatamente o handle. **Solicitar acesso DELETE nao executa uma exclusao.** O codigo nao chama `DeleteFile` nem altera ACL. Os campos `stage_delete_access_on_failure` e `zip_delete_access_on_failure` registram `DELETE_ACCESS_AVAILABLE` ou `DELETE_ACCESS_UNAVAILABLE` com o codigo Windows. Esses codigos nao provam identidade do processo, exclusao por antivirus ou causa especifica de ACL.


### Diagnóstico temporal v1.5: renomeacao repetida com staging completo

A versão 1.4 reproduziu `WinError 5` depois da validação oficial do ZIP de origem ou de snapshot, apesar do sucesso de copiar o ZIP e consultar handles com acesso DELETE. A próxima hipótese a testar é uma janela de indisponibilidade **transitória** após a validação. A versão 1.5 acrescenta `timed_settle_full_probe`: monta **uma** pasta de diagnóstico completa e tenta **apenas** `os.rename` para um destino descartável, com esperas graduais de 2, 5 e 10 segundos (no máximo 17 segundos de espera) para os códigos 5, 32 e 33; interrompe imediatamente para qualquer outro erro ou colisão. Registra `rename_attempts`, `rename_failures`, `wait_seconds_total` e consultas de acesso nativo à pasta/ZIP. Nunca altera as permissões, nunca publica um slot real, nunca faz cópia fallback e nunca altera o ZIP original. O teste físico Win11 determinará se um retry mais longo é justificável na produção. Não mude o handoff real com base só em testes sintéticos.


### P0 — Recuperação física validou 7s de espera (06/11/2026)

A execução **real** do diagnóstico temporal v1.5 na máquina Windows 11 do operador, no commit `fc4dab5`, retornou `timed_settle_full_probe.status=PASS`, `rename_attempts=3`, `rename_failures=[WinError 5, WinError 5]`, `wait_seconds_total=7` e `source_zip_preserved=True`, sobre o ZIP original NASA `Eo2bUJcxASI`. **Isto comprova o comportamento da pasta temporária, não a entrega final ao Curator.**

A política real de renomeação atômica do handoff passa a usar **quatro tentativas** (primeira imediata, depois intervalos de 2, 5 e 10 segundos, com no máximo 17 segundos de espera). Mantém o mesmo staging, exige o destino ainda inexistente antes de **cada** tentativa, faz uma única operação `os.rename(staging, folder)` por tentativa, e só repete para códigos Windows 5, 32 e 33. Erros diferentes, destino concorrente ou esgotamento da janela bloqueiam a entrega preservando o ZIP original. A validação oficial de snapshot externo, checksums SHA256 e revisão humana continuam obrigatórios. Sem copy-fallback, sem renomeação forçada, sem reprocessamento de vídeo, sem alteração de permissões e sem publicação de mídia.

Depois de atualizar `develop`, execute testes focais e somente então `RETOMAR_R6_NASA_SEM_REANALISE.ps1`. Sucesso técnico somente com os relatórios reais `PILOT_E2E_REPORT.json` e `PILOT_RECOVERED_PREVIEW_REPORT.json`, correspondentes à inbox e MP4 realmente verificados. `release`/`main` seguem não promovidas até aceite.


## Histórico do Analyzer → input do Curator (P0, sem reanálise)

A entrega automática para **novas** análises já ocorre após o exportador oficial R6 e o relatório. Para **análises anteriores**, `scripts/dev/sync_historical_curator_delivery.py` inventaria as subpastas **imediatas** de `analysis/` e aceita selecionar pastas históricas explícitas, sem percorrer recursivamente mídia ou backups.

**Modo padrão = somente leitura**, valida `second_curation_export.json`, SHA256 do ZIP original, `validate_core_package` oficial e metadados de origem. Classifica:

- `READY_FOR_DELIVERY`: existe ZIP R6 válido, pronto para sincronizar
- `NO_R6_EXPORT`: existe análise, mas **não existe ZIP oficial já exportado**; não inventar nem reconstruir sem solicitação separada
- `MISSING_SOURCE_ZIP`, `BLOCKED_*`: pacote/recibo ausente, incompatível ou corrompido; não publicar
- `DELIVERED`, `ALREADY_DELIVERED`: após `--apply`, entrega atômica ao `input/analyzer/<video_id>/<run_id>/` com integridade SHA256 e idempotência

**Prévia de todo o histórico (sem alterações)**:

```powershell
.\.venv\Scripts\python.exe scripts/dev/sync_historical_curator_delivery.py --scan-root ".\analysis"
```

**Entregar apenas uma análise anterior, primeiro como dry run**:

```powershell
.\scripts\windows\testing\SINCRONIZAR_ANALISES_CURATOR.ps1 -AnalysisDir @(".\analysis\pilot_e2e_20261106_135438_190")
```

**Aplicar explicitamente apenas ZIPs R6 válidos de todas as análises imediatas**:

```powershell
.\scripts\windows\testing\SINCRONIZAR_ANALISES_CURATOR.ps1 -ScanRoot ".\analysis" -Aplicar
```

**Aplicar somente pastas escolhidas**, sem varrer todo `analysis/`:

```powershell
.\scripts\windows\testing\SINCRONIZAR_ANALISES_CURATOR.ps1 -AnalysisDir @(".\analysis\run_A", ".\analysis\run_B") -Aplicar
```

O operador limita o inventário a 250 runs, recusa diretórios apontando para links/junctions, exige as duas branches `develop` para aplicar via PowerShell, não sobrescreve destinos e não altera `release`/`main`. O próprio `deliver_package` aplica a política física validada de retry de renomeação (2/5/10 segundos). Nenhum download, inferência, render, Stories inventados ou aprovação é executado. O relatório JSON é impresso no console e pode ser guardado fora do Git. A transferência de um R6 `PARTIAL` não significa análise completa nem R57 pronto.
