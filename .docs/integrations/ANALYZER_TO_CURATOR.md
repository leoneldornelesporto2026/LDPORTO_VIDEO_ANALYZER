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

**Sem commits de análise:** o GitHub recebe somente código, testes, contratos e documentos. ZIP R6, MP4 original, diretórios `analysis/`, capturas, prévias e renders ficam localmente ignorados pelo Git; para compartilhar evidências enviar um pacote de diagnóstico **separado**, com relatório/manifesto/hashes, ou artefatos apropriados com retenção. Nunca executar `git add -f` nesses caminhos.

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
