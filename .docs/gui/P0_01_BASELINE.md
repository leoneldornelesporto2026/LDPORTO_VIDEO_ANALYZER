# P0 — Modernizacao da GUI, sessao 01

**Projeto:** LDPORTO_VIDEO_ANALYZER
**Branch:** develop
**Baseline pre-sessao:** 0f102ca420fe6255b665628b48e37688ca52baed
**Escopo:** acrescentar testes, validador Windows e documentacao, SEM alterar o motor ou app.py.

## Inventario e protecao

A GUI publica usa Tkinter/ttk em app.py, chama analyze.py via subprocesso
e apresenta configuracao, execucao e conclusao. Ela ja possui verificacao de
origem e SHA256, consentimento explicito de download, progresso com evidencias,
cancelamento seguro via CANCEL_REQUESTED e gates separados para aprovacao de
preview e publicacao. Esses contratos devem permanecer ao modernizar a interface.

Implementados:
- Classe P0GuiBaselineContractTests: 15 verificacoes estaticas sem abrir GUI,
  instalar pacotes, iniciar subprocessos, usar GPU, rede ou videos.
- Validador scripts/windows/testing/VALIDAR_P0_GUI.ps1: exige Python 3.11 na
  .venv atual, confere branch develop, executa a nova classe e quatro
  arquivos de regressao ja existentes.
- Opcao -FullSuite para rodar toda a suite Python, sem baixar modelos.

## Comandos de teste (PowerShell, raiz do repositorio)

1. git switch develop
2. git pull --ff-only origin develop
3. & .\scripts\windows\testing\VALIDAR_P0_GUI.ps1
4. & .\scripts\windows\testing\VALIDAR_P0_GUI.ps1 -FullSuite

Se a politica bloquear scripts, execute:
Set-ExecutionPolicy -Scope Process RemoteSigned

Este validador nao instala dependencias. Se pytest estiver faltando, verificar
requirements/dev.txt antes de executar uma instalacao explicita no ambiente.

## Gate de aceite P0-01

- [x] Baseline e limites registrados.
- [x] Classe e validador publicados na develop.
- [x] 15/15 verificacoes P0 aprovadas no Windows (commit 6c8dec9).
- [x] Regressao focal GUI no Windows: 39 passed, 12 subtests passed.
- [ ] Suite completa aprovada: 2622 passed, 10 failed, 5 skipped e 28 subtests passed (466.82s) em 2026-11-05.
  Triagem: 7 faltas de ZIPs historicos, 1 conversao CRLF e 2 launchers.
  **Revalidacao focal no Windows (commit de79399): 65 passed, 1 skipped, 14 subtests passed, 1 warning, em 6.31s.**
  O SHA256 da fixture foi recuperado exatamente (81298196...).
  **Pendencia atual:** recuperar dois ZIPs originais, executar suite geral e validar a GUI visualmente.
  O aviso de string de caminho foi corrigido em commit posterior; requer confirmar ausencia de warning no Windows.
- [ ] GUI atual abre e funciona no Windows antes da refatoracao.

**Status: AGUARDANDO VALIDACAO WINDOWS.**
Testes estaticos nao comprovam funcionamento visual nem processamento real.
Nenhuma promocao para release/main antes do aceite.

## Proximas sessoes P0 — sequenciais

- 02: novo shell visual, navegacao, hierarquia, foco, espacamento e responsividade.
- 03: entrada guiada de video/YouTube, SHA256 e consentimento.
- 04: perfis Qualidade/Balanceado/Rapido/Personalizado, com configuracao
  efetiva documentada e preflight antes de executar.

Ciclo de trabalho: alterar somente develop, registrar SHA, executar teste
focado e suite completa no Windows, conferir visual e avancar apos aceite.
