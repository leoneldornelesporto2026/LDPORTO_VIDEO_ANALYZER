# P0-02 — Shell visual nativo

Implementacao somente em develop, partindo do commit cba9feb6.

Entregas: novo titulo e subtitulo, navegacao horizontal pelas 6 secoes,
cards de secao, CTA de ANALISAR destacado e estilos ttk isolados.

Nao houve alteracao de engine, argumentos, download, GPU, modelos,
cancelamento, integridade, gates de revisao ou exportacao.

## Gate Windows

1. python -m unittest discover -s src/tests -p test_p0_visual_shell.py -v
2. Executar scripts/windows/testing/VALIDAR_P0_GUI.ps1
3. Abrir ABRIR_ANALYZER.bat e verificar layout e navegacao por teclado/mouse.
4. Conferir tela com DPI 100% e 125%, janela menor e cada secao.

Esta etapa depende de aceite visual. Teste estatico nao homologa a interface.
Suite geral continua bloqueada pelos dois ZIPs historicos originais ausentes.

Proxima: P0-03 - fluxo de entrada de video; depois P0-04 - perfis de analise.

## Evidencia Windows recebida (2026-11-05)

Abertura da GUI Windows comprovada com Python 3.11.9. A captura do
usuario mostra cabeçalho, seis itens da navegacao, titulos das secoes
e rodape fixo com ANALISAR. Testes estaticos da P0-02: 6/6 PASS;
baseline P0-01: 15/15 PASS; regressao focal: 39 PASS e 14 subtestes
PASS. Teste de integridade de fixture: 6/6 PASS.

Apenas a renderizacao inicial foi comprovada pela captura.
Ainda nao ha evidencia de clique em cada item de navegacao, DPI 125%
e janela reduzida. O aceite completo de P0-02 fica pendente desses
casos; P0-03 avanca isoladamente sem promover release/main.
