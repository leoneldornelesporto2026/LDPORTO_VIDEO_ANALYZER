# P0-04 — Perfis de analise opcionais

Branch: develop. Baseline inicial: c9c76a61405edef73a9f18f54fd27f9c56f97050.

## Principio

Perfis sao apenas escolhas explicitas de UI; nao representam qualidade ou
performance benchmarkada e nao iniciam nenhuma chamada de IA ou rede.
Inicializa em Personalizado para preservar os parametros carregados.

## Mapeamento

| Selecao | ASR | Perfil Ollama |
| --- | --- | --- |
| Qualidade (large-v3) | large-v3 | max |
| Equilibrado (medium) | medium | balanced |
| Rapido (turbo) | turbo | fast |
| Personalizado | nao altera | nao altera |

CPU/CUDA, habilitacao do Ollama, modelo Ollama, diarizacao, vision, OCR,
camera, downloads, hash e seguranca permanecem inalterados pelos perfis.
Quando o operador altera manualmente modelo ou parametros relevantes,
o seletor volta para Personalizado sem perda das escolhas atuais.
Resumo mostra valores efetivos, sem reivindicar benchmark.

## Aceite da sessao

- [x] 11/11 testes P0-04 aprovados no Windows no commit 750f4eb (2026-11-05).
- [x] P0-01 15/15, P0-02 6/6, P0-03 8/8, fixture 6/6 e regressao GUI 39 passed + 14 subtests passed, sem falhas.
- [ ] GUI abre: inicio Personalizado; selecionar Qualidade, Equilibrado, Rapido;
- [ ] Modelo ASR e perfil Ollama mudam conforme selecao; CPU/CUDA nao muda.
- [ ] Ativar/desativar Ollama, trocar modelo/dispositivo -> Personalizado.
- [ ] Verificar que botao ANALISAR, verificacao de fonte e SHA256 permanecem.
- [ ] Revisao de tela em 100%/125% e janela reduzida.

Comandos:

~~~powershell
git status --short
git pull --ff-only origin develop
.\.venv\Scripts\python.exe -m unittest discover -s src/tests -p test_p0_analysis_presets.py -v
.\scripts\windows\testing\VALIDAR_P0_GUI.ps1
.\ABRIR_ANALYZER.bat
~~~

Bloqueio paralelo: suite historica continua dependente dos dois ZIPs originais
R4.9-S4. Nao gerar fixtures falsas nem promover release/main.

**Estado:** implementado, aguardando testes e homologacao GUI Windows.


## Regressao Windows em 2026-11-05 — correção do teste 06

Commit testado: `59168b2886558a23840f919e3e913469a877333c`.
Os 10 testes de perfis apresentaram 9 PASS e 1 FAIL, somente no
`test_06_manual_changes_turn_named_profile_into_custom`: a verificacao
literal procurava `self._applying_analysis_profile`, enquanto a
implementacao segura usa `getattr(self, "_applying_analysis_profile", False)`.
Nao foi observada excecao do app nesse teste; a falha ocorreu na assercao
de texto.

O contrato foi atualizado para verificar a forma efetiva do guard, e
complementado por execucao isolada do metodo: edicao manual troca o
perfil para Personalizado, mas alteracoes durante aplicacao de preset
nao alteram seu nome. Adicionado teste de execucao isolada de preset
protegendo dispositivo, habilitacao de Ollama, consentimento e SHA256.
**Agora 11 testes de perfil precisam ser reexecutados no Windows.**

As evidencias anteriores continuam: P0-01 15 PASS, P0-02 6 PASS,
P0-03 8 PASS, regressao de integridade 6 PASS. A bateria focal
completa foi interrompida pelo teste 06 e ainda precisa ser repetida.
A GUI foi iniciada pelo BAT; falta homologacao visual e comportamental
dos perfis. A suite historica continua bloqueada pelos ZIPs ausentes.

## Evidencia Windows confirmada — commit 750f4eb (2026-11-05)

O operador atualizou `develop` e executou o comando dedicado e
`scripts/windows/testing/VALIDAR_P0_GUI.ps1`, usando Python 3.11.9 e pytest 9.1.1.

| Gate | Resultado observado |
| --- | --- |
| Testes de perfis P0-04 | 11 passed, 0 failed |
| Baseline P0-01 | 15 passed, 0 failed |
| Shell P0-02 | 6 passed, 0 failed |
| Midia P0-03 | 8 passed, 0 failed |
| Integridade de fixture | 6 passed, 0 failed |
| Regressao focal GUI | 39 passed, 14 subtests passed, 0 failed |

No total do validador, sao **85 testes distintos aprovados e 14 subtestes
aprovados**, sem duplicar a execucao separada da mesma classe P0-04.
O aviso de escape e a falha da assercao de texto anterior nao reapareceram
nessa evidencia.

**Aceite de testes P0: APROVADO. Aceite visual P0: PENDENTE.**

### Checklist manual que ainda falta (sem processar videos)

1. Abrir `ABRIR_ANALYZER.bat` e conferir a nova secao de perfis na interface.
2. Valor inicial deve ser Personalizado, sem alterar selecoes do operador.
3. Selecionar Qualidade, Equilibrado e Rapido; conferir modelo ASR e
   perfil do Ollama conforme mapeamento acima.
4. Conferir que dispositivo CPU/CUDA nao muda, Ollama nao liga/desliga
   e modelo Ollama permanece o escolhido.
5. Alterar manualmente ASR ou dispositivo; seletor precisa voltar
   para Personalizado sem descartar as opcoes.
6. Abrir os detalhes de SHA256 e voltar; verificar que o consentimento
   de download continua desmarcado, sem processamento automatico.
7. Navegar pelas seis secoes; verificar rodape ANALISAR, scroll e foco
   em 100% e 125% de escala Windows (quando possivel).

A suite historica com evidencias externas **nao foi executada por completo**:
`CHATGPT_REVIEW.zip` e `SECOND_CURATION_READY.zip` originais continuam
ausentes. Nunca sintetizar arquivos, editar hashes ou desabilitar testes
para conceder homologacao. `main` e `release` nao foram modificadas.
