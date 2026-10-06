# V4.2: Windows e Python

Data: 2026-10-05. Alvo preservado: Windows 10/11, Python 3.11.x de 64 bits.

## Descoberta De Interpretadores

Foram executados `where.exe python`, `where.exe python3`, `Get-Command python.exe -All`
e `Get-Command python -All`. Foram consultados PATH de processo, usuario e maquina,
registro PythonCore (HKCU/HKLM/WOW6432Node), instalacoes em
`%LOCALAPPDATA%/Programs/Python`, processos Python acessiveis e ambientes virtuais
em Downloads, Documents e source/repos, incluindo o workspace.

- Instalacao local encontrada: Python 3.13.3.
- Tres ambientes virtuais executaveis encontrados: Python 3.13.3.
- Um ambiente antigo aponta para Python 3.10 removido; nao foi reutilizado.
- Nenhum Python 3.11 foi encontrado nos locais verificados. A ausencia de `py`
  nao foi usada como prova de ausencia de Python 3.11.
- Nao foi instalado outro interpretador global.

## Evidencia Executada

Ambiente auxiliar: `.venv`, Python 3.13.3, Windows 11 Enterprise 10.0.26200.
O baseline inicial usou um ambiente NAO HERMETICO: a preparacao anterior tinha
ativado `include-system-site-packages=true`. A auditoria de dependencias revelou
216 advisories em 24 pacotes do conjunto herdado; isso nao equivale a 216 CVEs
do Analyzer. A heranca foi desativada, sem atualizar nem remover pacotes globais.
As validacoes posteriores devem ser distinguidas desse baseline inicial.
Primeira tentativa: erro de coleta por `soundfile` ausente. Depois de instalar a
dependencia apenas na `.venv`, baseline original: 127 passed, 3 failed, 0 skipped,
34.274 segundos, 130 testes. Duas falhas eram FFmpeg ausente e uma era o teste do
exportador legado. O teste migrado inicialmente comprovou duplicatas no exportador
canonico; depois da correcao, 1 passed em 1.84 segundos.

Resultados em Python 3.13 sao validacao auxiliar, nao homologacao Python 3.11.
Sintaxe analisada com a gramatica 3.11 representa apenas compatibilidade estatica.
Nenhum requisito sera alterado exclusivamente para acomodar Python 3.13.

Suite consolidada auxiliar: 228 passed / 0 failed / 0 skipped em 46.08 s;
o fechamento final repete a suite apos os ultimos testes/documentacao, com resultado
definitivo em WORKER_FINAL_REPORT.md. py_compile de 65 arquivos first-party passou.
O full workflow usa video/audio sinteticos, transcricao importada e features
desativadas explicitamente. Preview/decoder FFmpeg/OpenCV foram executados de verdade.
Doctor real: exit 2; runtime_target_match=false, imports/modelos habilitados ausentes.
Teste de callbacks GUI nao equivale a homologacao de GUI nativa/acessibilidade.

## Pendencias

- Executar a suite e o doctor com Python 3.11.x real.
- Instalar dependencias/modelos em uma maquina Windows limpa com Python 3.11.
- Verificar GPU/CUDA, pyannote Community-1, MediaPipe e Ollama com modelos reais.
- Reexecutar o mesmo video e comparar os artefatos; fixtures nao comprovam acuracia.

A `.venv` auxiliar, qualquer interpretador temporario e `.worker_v42` devem ficar
fora do ZIP final. O teste de empacotamento verifica explicitamente a exclusao
da `.venv`; a inspecao final do ZIP repetira a verificacao.