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
