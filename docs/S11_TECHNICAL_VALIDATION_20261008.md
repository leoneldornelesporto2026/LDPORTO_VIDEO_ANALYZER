# R4.9 S9/S10/S11 — Relatório de validação técnica da entrega

**Data da execução:** 08/10/2026. **Base:** ZIP R4.9/S8. **Ambiente do teste:** Linux, Python 3.13, FFmpeg/ffprobe disponíveis, sem GPU NVIDIA e sem Ollama do usuário.

## Evidências executadas

- Regressão automatizada: **582 testes aprovados, 2 ignorados, 0 falhas**; relatório JUnit em `docs/S11_AUTOMATED_TESTS.xml`.
- Integração FFmpeg com vídeo **sintético** (padrão visual gerado por lavfi + tom senoidal): fonte em arquivo local com áudio real de teste, `SECOND_CURATION_READY` válido gerado pela arquitetura original, planejamento, transcrição e títulos importados.
- Canary MP4 1080 × 1920, H.264/AAC, áudio presente, timestamps de 2,0 segundos e SHA-256 no recibo.
- Testes de dois Stories sintéticos como MP4s independentes e aprovação de canário vinculada a hash; testes negativos rejeitam checklist incompleto, alterações em vídeo revisado, plano alterado, fonte diferente e pacote `PARTIAL`.
- Configuração de trilha instrumental testada num vídeo sintético com áudio de teste; teste de `SECOND_CURATION_DECISIONS` compila e importa duração, título e layout.
- A/B de Ollama e visão preparado para execução real. Não há medidas de ganho aqui. Auditor de recursos reporta ausência de NVIDIA e Ollama locais; nenhuma alteração de configuração de concorrência/cache foi aplicada.

## Limites da afirmação

**Não é homologação real do conteúdo Emerson/Clóvis**, e não foi feita avaliação subjetiva de punchlines, GC, escolha de rostos, fidelidade de legendas ou qualidade de música de fundo. Também não foi possível alterar/testar o aplicativo Curator independente porque seu código não acompanha a base; a nova ponte permite executar renderização local com FFmpeg e preservar o bridge legado.

A aprovação S11 continua bloqueada até executar os comandos de `docs/S9_S11_REAL_TEST.md` na máquina Windows/Python 3.11 com vídeos e artefatos reais, assistir aos MP4s, preencher os checklists humanos por hash e medir os benchmarks A/B.
