# Sessão 3 — Inteligência editorial (R4.9 / S3)

## Entregue no código

- `src/ldporto/editorial_intelligence.py`: análise de **integridade narrativa** com IDs literais de setup, desenvolvimento, climax/punchline e ending, indícios de humor (transcrição com marcador de riso, réplica, interrupção e reação após a janela) e shortlist sem cotas obrigatórias (piso de qualidade e diversidade). Não confunde risada em ASR com comprovação acústica de humor.
- `src/ldporto/understanding.py` e `src/ldporto/story_recovery.py`: arcos com estrutura introdução/desenvolvimento/clímax/resolução/desfecho; expansão de momentos para preservar o desfecho quando o arco completo está devidamente fundamentado; correção da prioridade do primeiro desfecho após o conflito; arcos incompletos não são tratados como histórias completas.
- `src/ldporto/semantic.py`: recuperação multi-turno de Q&A incluindo pergunta fragmentada, réplica interrompida, resposta longa e evidência de locutor; distinção entre *candidato vinculado* e resposta semanticamente comprovada. Continua `needs_review=true` sem confiança fictícia.
- `src/ldporto/editorial.py`: expansão de limites ancorados em segmento até abranger pergunta e resposta associadas, pontuação que penaliza final incompleto, exclusão da shortlist ao perder pergunta essencial, setup ou desfecho.
- `src/ldporto/second_curation.py` e `src/ldporto/second_curation_export.py`: transferem diagnóstico editorial, segmentos observados, categorias, clímax, ending e arquivo `editorial/selection_report_s3.json` sem mudar os contratos de aprovação S2.
- `scripts/dev/review_editorial_s3.py`: reavalia `analysis.json` ou pacote SECOND_CURATION em **modo offline**, sem processar vídeo. Preserva estado PROVISIONAL se a integridade upstream estiver incompleta.

## Como avaliar os 36 candidatos do vídeo real

O ZIP **do projeto-fonte** recebido nesta sessão não inclui os 36 registros, `analysis.json`, o transcript desse vídeo nem o ZIP de segunda curadoria correspondente. Portanto nenhum resultado real dos 36 é afirmado no relatório de entrega.

No Windows, depois de produzir ou localizar o `SECOND_CURATION_*.zip` **da mesma execução**:

```bat
py -3.11 scripts\dev\review_editorial_s3.py --package "C:\CAMINHO\SECOND_CURATION_....zip" --out "C:\CAMINHO\auditoria_editorial_s3.json"
```

Ou com o `analysis.json` completo:

```bat
py -3.11 scripts\dev\review_editorial_s3.py --analysis "C:\CAMINHO\analysis.json" --out "C:\CAMINHO\auditoria_editorial_s3.json"
```

O relatório inclui a lista de IDs selecionados, razão de exclusão por candidato, shortlist com piso de qualidade e diversidade, e o *status real* do upstream. Quando o upstream estiver incompleto, `shortlist_ids=[]` e os eventuais IDs sugeridos aparecem **somente como diagnósticos hipotéticos**. Uma curadoria editorial reexecutada pelo pipeline principal gera a shortlist com as novas regras, pontuações e limites.

## Critérios de aceite e limites reais

- Não selecionar um candidato de história observada se faltam setup, desenvolvimento, payoff ou ending; nem trecho de pergunta sem resposta completa quando a pergunta aparece dentro do recorte.
- Não selecionar o humor explicitamente marcado quando a reação observada ou indício de payoff ocorre **depois** do recorte. Sem indícios lexicais ou riso anotado, humor continua **não resolvido**; o programa não escuta risadas independentemente da transcrição neste patch.
- A presença de pontuação e marcadores não prova desfecho editorial satisfatório; **revisão humana/segunda curadoria continua obrigatória**.
- Q&A ampliado aumenta associações *candidatas*, não garante que 45 perguntas reais produzirão um certo número de pares — exige medição no vídeo/análise fornecida.
- Piso `.50` e teto de `2` momentos por tópico são padrões iniciais conservadores, **não** thresholds calibrados empiricamente no vídeo real. O limite `max_moments` é teto, nunca cota.
- A exportação conserva candidatos alternativos, exclusões comerciais, dados da câmera, e o gate S2; nunca declara `preview_approved` nem `publication_ready` como verdadeiros.

## Testes

Com `PYTHONPATH=src:. pytest -q`, a suíte completa exercita o pipeline, QA, arcos, S2, exportador e curadoria, incluindo novos testes `test_s3_editorial_intelligence.py` e `test_s3_editorial_reviewer.py`. A aceitação com vídeo real, inspeção humana de setup/desfecho, precisão/recall de Q&A e homologação no Windows 3.11 são etapas ainda não executadas neste ambiente.
