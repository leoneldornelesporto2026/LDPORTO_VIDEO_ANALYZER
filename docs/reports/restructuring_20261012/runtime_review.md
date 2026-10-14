# Runtime, fidelidade do handoff e diagnóstico editorial — 12/10/2026

## Escopo e evidência

Mudanças em `ollama_local.py`, `semantic.py`, `runtime_metrics.py`, `progress.py`, `app.py`, `second_curation_export.py`; novo `editorial_outcome.py` e 41 casos em `test_runtime_fidelity_contracts.py`. Integrações em pipeline, relatórios e reconstrução editorial ficaram a cargo dos agentes responsáveis por esses arquivos.

Não houve chamada de inferência Ollama/Whisper, carregamento de modelo, análise audiovisual completa, download ou instalação. Testes utilizaram respostas simuladas, relógios controlados, arquivos JSON e, nas regressões existentes de handoff, mídia sintética temporária. Nenhuma mídia local do usuário foi consumida. Nenhum resultado de pytest representa homologação acústica/visual real.

## Causas confirmadas e mudanças

Uma reprodução com `python -B`, relógio fictício e pesos atuais mostrou 99,02% global e 100% da etapa enquanto a revisão editorial global ainda estava em execução; depois de todas as etapas, antes do evento `run_completed`, o indicador mostrava 99,9%. O indicador global agora reserva 5% até a confirmação da conclusão. Quando todos os estágios terminaram, a GUI identifica a finalização de artefatos/verificações. A extração semântica reserva explicitamente sua fase de revisão, e mudanças de subetapa descartam amostras de throughput de unidades incompatíveis.

O histórico de ETA anteriormente distinguia somente modelo/perfil semântico, permitindo combinar opções e trabalho diferentes. O fingerprint agora inclui duração em faixas de cinco segundos, opções de geração e as configurações que determinam custo de ASR, diarização, áudio, cenas, visão, OCR, semântica, câmera e exportação. Custos negativos/não finitos, booleanos, estágios em cache e falhas explícitas não alimentam estimativas. ETA continua `calculando...` quando não existem amostras comparáveis suficientes.

O cliente Ollama já guardava contadores e durações em nanossegundos. Foram acrescentados custos separados de carregamento, processamento de prompt e geração, TPS de entrada/saída e tamanho real do request/schema. Valores ausentes, inválidos ou que transbordem aritmeticamente ficam `null`. A agregação usa somente pares realmente medidos de tokens/tempo. Contadores zero observados continuam zero. Erros de transporte preservam seu tipo e metadados de custo; chamadas inicial e de reparo falho continuam separadas. Uma falha de validação local, anterior ao HTTP da revisão global, contabiliza zero chamadas nessa fase. Custos de inferência originais guardados em cache não entram como nova inferência.

O perfil `max` permanece com contexto 32768, saída máxima 6144, temperatura 0 e seed 42. O modo de prompt compacto já existente permanece opt-in; não foi ativado automaticamente. A fotografia já disponível dos modelos em execução no início é projetada para tamanho/contexto/VRAM informados pelo serviço, sem inventar uso de GPU.

A semântica recebe a fala original em qualquer idioma e os sinais de idioma/uncertainty fornecidos pelo ASR. Traduções nunca entram nesse slot. O cache incorpora esses campos e o prompt atualizado. Tópicos, momentos, perguntas/respostas e tópicos/seções mesclados preservam quais segmentos originais exigem revisão; o tema principal mantém a mesma sinalização. O texto literal continua derivado exclusivamente dos segmentos fornecidos.

O pacote de segunda curadoria anteriormente projetava segmentos apenas para ID, início/fim, falante e texto, descartando contexto ASR. Agora preserva idioma, escopo/hints de detecção, marcações de incerteza e IDs de hipóteses; palavras mantêm tokens raw, proveniência e marcadores de tarefa. As traduções, segmentos originais de importação, proveniência, hipóteses de idioma, alternativas e orçamento de revisão ficam em artefatos separados e cobertos pelo manifesto/SHA-256. Traduções referenciam os IDs originais da importação, sem remapeamento fictício para segmentos divididos pela diarização. Referências a hipóteses brutas externas permanecem explicitamente atribuídas à análise produtora, sem afirmar inclusão no ZIP.

O contrato novo do pacote valida paridade entre manifesto/index/brief, IDs de tradução, rejeição de marcadores de tradução/reescrita no slot original e correspondência do TXT/SRT com os segmentos originais. Rehashes não escondem inconsistências semânticas. A primeira rodada revelou uma falha real de portabilidade: `write_text` no Windows produzia CRLF, enquanto a validação esperava LF. A produção agora grava LF explicitamente e a comparação normaliza somente CRLF/LF; o conteúdo literal continua estrito.

Uma revisão de compatibilidade identificou que emitir `raw: null` em palavras legadas sem token raw impediria o fallback já existente em `word_text`. Campos opcionais ausentes agora continuam ausentes no JSONL, e uma regressão percorre exportação do pacote e leitura pelo consumidor real. A GUI usa o rótulo neutro `Revisao editorial global`, pois a fase também pode consultar cache sem executar inferência nova.

O diagnóstico editorial distingue `no_eligible_cuts`, `insufficient_evidence`, `video_too_short`, `technical_error`, `low_quality_candidates` e o caso positivo `selected`. Preserva razões/candidatos registrados, duração alvo e piso de qualidade. Uma falha conhecida em etapa editorial obrigatória prevalece sobre uma shortlist obsoleta. Evidência original incerta é consultada diretamente pelos IDs, inclusive para candidatos legados sem os novos flags. O diagnóstico não modifica seleção, pontuações, elegibilidade ou gates. Pacote, resumo, index, brief e manifesto exigem paridade dos diagnósticos quando o contrato está presente; a GUI apresenta seu motivo.

## Comandos e resultados reais

1. Auditoria: `rg --files`, `rg -n` e `Get-Content` nos módulos/testes relevantes. Uma reprodução CPU via `.venv\Scripts\python.exe -B -` importou somente `WeightedProgress`, emitiu eventos sintéticos e registrou 99,02%/100%/99,9% descritos acima.
2. Primeira validação: `.venv\Scripts\python.exe -m pytest -q src/tests/test_runtime_fidelity_contracts.py src/tests/test_v43_runtime.py src/tests/test_v44_ops.py src/tests/test_v43_semantic.py src/tests/test_v47_r3b_performance.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py src/tests/test_v42_editorial.py` — **124 passed, 10 failed, 10,65 s**; falhas de exportação por CRLF/LF, corrigidas no código.
3. Após a correção, mesma seleção acrescida de `--tb=short src/tests/test_stage65_execution_receipts.py` — **175 passed, 18,55 s**.
4. Nova validação dessa seleção depois dos guardas adicionais — **178 passed, 1 failed, 18,98 s**, em `runtime_focus.log`. A única falha era o teste negativo alterar o estado para o valor que já existia; corrigido para produzir uma divergência efetiva. Não foi necessário afrouxar validação.
5. `.venv\Scripts\python.exe -m pytest -q --tb=short src/tests/test_runtime_fidelity_contracts.py` — **38 passed, 4,73 s**, em `runtime_new_contracts.log`.
6. Após os dois casos de overflow: `.venv\Scripts\python.exe -m pytest -q --tb=short src/tests/test_runtime_fidelity_contracts.py src/tests/test_v43_semantic.py src/tests/test_v47_r3b_performance.py src/tests/test_v44_ops.py` — **62 passed, 4,99 s**, em `runtime_final_focus.log`; destes, 40 são casos novos.
7. Após o ajuste de compatibilidade final: `.venv\Scripts\python.exe -m pytest -q --tb=short src/tests/test_runtime_fidelity_contracts.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py` — **53 passed, 9,28 s**, em `runtime_compatibility_focus.log`; 41 casos novos estão incluídos. Arquivos de produção/testes congelados após esta rodada para a regressão final do responsável principal.

O responsável principal registra a regressão completa final e a baseline; este relatório não atribui esses resultados aos testes acima.

## Benchmark CPU e limites

`runtime_cpu_overhead.json` foi produzido por `.venv\Scripts\python.exe -B -` em script inline: `semantic.ollama_chat` substituído por função que apenas captura payloads; um segmento sintético de 19 s; cinco rodadas; 100 construções de payload por rodada e 20 agregações ampliadas de 1000 registros sintéticos por rodada. Nenhuma resposta foi gerada por modelo.

Mensagem legada: **3903 caracteres**; opt-in compacto: **1956**, com mesmo schema e mesmas opções `max`. Construção de payload: mediana **0,0664 ms** e **0,0519 ms**, respectivamente. Agregação antiga de TPS de geração: **0,0438 ms** por 1000 registros; agregação ampliada de todos os custos finitos: **1,4211 ms**. Estes números mostram tamanho e custo CPU da instrumentação; não são desempenho Qwen nem melhora da análise de 289,4 s relatada pelo usuário.

## Estado de validação

- Resolvido em fixtures/regressões: separação e preservação de custos, falhas/reparos, progresso antes da confirmação final, fingerprint de ETA, propagação de incerteza e contratos de transcrição/tradução/diagnóstico do ZIP.
- Não validado por esta atividade: velocidade/qualidade Qwen real antes/depois, detecção de idioma acústica, acurácia de ASR, VRAM durante inferência e ETA em vídeos reais nesta máquina.
- Pendente de homologação: rodada audiovisual explícita no Windows, A/B equivalente de prompt compacto com mesma fonte/cache/configuração/modelo e medição de tokens/tempos informados pelo Ollama real. O modo compacto continua opt-in até essa validação.

Os estados de revisão, preview e publicação, regras comerciais, áudio autoral e identidade visual permaneceram preservados.
