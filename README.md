# L.D.PORTO VIDEO ANALYZER

**Analyzer / Perception Engine** — aplicacao local para Windows 10/11 e Python
3.11, com analise de videos, transcricao, diarizacao, visao, OCR, curadoria
editorial e geracao de pacotes para revisao humana. Nao publica conteudo
automaticamente.

## Inicio rapido

1. Instale Python 3.11 de 64 bits e prepare FFmpeg/FFprobe.
2. Na pasta do projeto, execute `INSTALAR_WINDOWS.bat` (instala dependencias).
3. Execute `DIAGNOSTICO_WINDOWS.bat` para verificar o ambiente.
4. Execute `ABRIR_ANALYZER.bat` para abrir a interface.

Para consultar comandos sem instalar dependencias:

```powershell
.\.venv\Scripts\python.exe analyze.py --help
```

Os scripts `INSTALAR_AVANCADO_WINDOWS.bat`, `CORRIGIR_GPU_WINDOWS.bat` e
`CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat` sao opcionais e podem modificar o
ambiente. Os modelos de IA, os videos e as credenciais ficam fora do Git.

## Documentacao

A documentacao detalhada fica centralizada pelo indice:

**[Abrir documentacao completa (.docs/README.md)](.docs/README.md)**

La estao o guia de instalacao, execucao, diagnosticos, arquitetura,
dependencias, testes, exportacao, changelogs e registros historicos.

## Desenvolvimento

A branch de trabalho e `develop`. `release` e `main` so devem receber
promocoes apos validacao. Os resultados de testes automatizados offline nao
substituem homologacao em Windows com videos e modelos reais.

Os arquivos `AGENTS.md` (instrucoes de agentes), `src/`, `scripts/`,
`config/` e `schemas/` continuam nos caminhos tecnicos originais por
compatibilidade com o codigo e as ferramentas.

## Piloto real Analyzer -> Curator

No Windows/PowerShell 5.1, execute o operador `scripts/windows/testing/PILOTO_E2E_REAL.ps1`, com um vídeo do YouTube que você tem direito de processar. Exige `-SourceUrl <URL>` e **`-AllowDownload` explícito** se for baixar, ou `-MediaPath <original local>` quando já houver mídia. Pode repetir um resultado existente com `-AnalysisDir <pasta>`, sem inferência.

O operador gera `analysis/pilot_e2e_*/PILOT_E2E_REPORT.json` com os gates P0/P1 de ZIP real, recibo, SHA256, smoke técnico R6 e auditoria do MP4. Não renderiza vídeos finais, não efetua commits/push de mídia e não aprova publicação. Leia detalhes em `.docs/integrations/ANALYZER_TO_CURATOR.md`.

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
