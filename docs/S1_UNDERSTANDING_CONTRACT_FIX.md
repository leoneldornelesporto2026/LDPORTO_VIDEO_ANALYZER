# S1 — Understanding: contrato de histórias e exceções de duração

Base: R4.7 (2026-10-07); atualização: R4.8-S1-UNDERSTANDING.

## Incidente confirmado

`assess_duration()` registrava `duration_exception_evidence` como
`{"setup": [segment_ids], "development": [segment_ids], "payoff": [segment_ids]}`.
`rank_candidate()` reconstruía `story` a partir dessa evidência sem voltar
à representação `{"segment_ids": [...]}`. Em seguida `_complete_story()`
invocava `.get()` em uma lista e causava `AttributeError: 'list' object has no attribute 'get'`.

## Correção

- `_story_component_ids`: aceita somente IDs explícitos de segmentos, tanto
  de um componente de arco em objeto quanto do comprovante legado em lista.
  Rejeita evidências ausentes, malformadas ou repetidas.
- `_complete_story`: só aceita evidências presentes na sequência selecionada,
  em ordem estrita: setup, development, payoff. Não cria tempos/segmentos.
- `assess_duration` e `rank_candidate`: compartilham contrato de evidência;
  qualquer comprovante reprovado revoga a exceção de duração.
- `run_understanding`: valida componentes dos arcos antes do ranking,
  registra caminho/tipo/ação, invalida histórias sem prova e mantém
  `needs_review`. Os eventos de diagnóstico não contêm transcrição.
- `src/tests/test_understanding_session1.py`: 11 testes, incluindo IDs
  observados nos replays de Emerson e Clóvis; fixtures mínimas sem transcrição.

## Replays executados, offline e sem reinferência

Fonte: ZIPs `CHATGPT_REVIEW_video_b17d58aed164_20261007_211258_855955.zip`
(Emerson) e `CHATGPT_REVIEW_video_31329be78ca4_20261005_232323_219590.zip`
(Clóvis). O script reconstroi a entrada editorial a partir das coleções
exportadas; não executa ASR, tracking, Ollama, mídia ou publicação.

| Fonte | Segmentos | Momentos semânticos | Arcos | Entidades | Momentos finais | Shortlist |
|---|---:|---:|---:|---:|---:|---:|
| Emerson | 741 | 36 | 37 | 10 | 36 | 2 |
| Clóvis | 2710 | 188 | 99 | 24 | 176 | 9 |

O Clóvis também preservou uma exceção de duração fundamentada (122,2 s)
sem o crash antigo.

**Limitação:** Replay isolado da etapa não é homologação de todas as etapas
posteriores nem transforma pacote `PARTIAL` em `READY`.

## Executar o replay seguro (Windows / Python 3.11)

Na pasta raiz do Analyzer, sem sobrescrever a análise original:

```bat
.venv\Scripts\python.exe scripts\dev\replay_understanding_snapshot.py "C:\caminho\CHATGPT_REVIEW_video_b17d58aed164.zip" --output-dir "C:\temp\replay_s1_emerson"
```

O resultado tem `replay_summary.json` e
`understanding_contract_diagnostics.json`. Usar um ZIP de review que contenha
as coleções e `analysis.json` da mesma execução. Não inclua a pasta de
replay no cache oficial.

### Cache e retomar pipeline real

`16_understanding` deve ser reexecutado com o código novo. Como `15_semantic`
usa a assinatura de todo o arquivo `editorial.py`, esta alteração **também
pode invalidar o cache semântico** em um run normal; não garantir que a GUI
reutilize o trabalho do Ollama. Use o replay offline acima para testar apenas
o Understanding sem refazer etapas pesadas. Para um benchmark ponta a ponta,
faça backup e verifique os logs dos cache hits; não use `--force`.

## Limites desta sessão

Ainda falta a Sessão 2: reconciliar `manifest`/`summary`/gates/shortlist,
reanalisar comerciais e homologar um pacote completo `SECOND_CURATION_READY`.
Os títulos, os enquadramentos e a fidelidade das legendas exigem revisão
em vídeo real; nenhuma porcentagem de qualidade editorial é inferida daqui.
