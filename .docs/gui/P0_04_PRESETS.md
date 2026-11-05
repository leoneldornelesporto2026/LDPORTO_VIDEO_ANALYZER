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

- [ ] 10/10 contratos P0-04 passam no Windows.
- [ ] P0-01/02/03 e regressao focal continuam verdes.
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
