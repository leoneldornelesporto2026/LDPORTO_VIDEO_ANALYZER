# Diagnóstico do pacote anexado

Este diagnóstico fundamenta os prompts. Ele confirma o conteúdo dos exports e registra hipóteses para investigação. Não representa inspeção do código, escuta do áudio ou validação do render final.

## Conteúdo verificado

- Fonte tpcF5ri6GS4, FAMOSOS QUE VIRARAM CRENTES feat. João Gordo, duração declarada 1820,034 s, 1920 × 1080, aproximadamente 23,976 FPS.
- 113 arquivos: 96 JSON, 2 JSONL, 12 JPEG, 1 Markdown, 1 SRT e 1 TXT.
- Os 112 arquivos relacionados no manifesto existem e correspondem aos hashes/tamanhos informados. A contagem total inclui o próprio manifesto.
- Não há código Python, vídeo fonte, áudio ou preview MP4.
- Os JSONL relevantes têm 959 segmentos e 5958 palavras, sem IDs duplicados. Os vínculos de segmento/palavra dos candidatos e de evidência dos qa_pairs presentes resolvem nesses exports. A contagem global reportada é 6840 palavras e tem escopo diferente.
- Há 12 contact sheets para 55 candidatos. Quatro foram abertas na auditoria inicial para confrontar exemplos com os relatórios; isso não é revisão de todos os frames. Os 43 demais candidatos têm visual_refs vazio. Não foram encontrados refs JPEG que apontassem para arquivo ausente.
- Todas as 55 preview_reference são null. Os relatórios informam canary técnico feito anteriormente; nenhum MP4 de canary/final foi incluído para conferência.

## Achados e investigação necessária

1. Integridade do handoff de Q&A

Há 123 ocorrências de vínculos para 111 IDs de pergunta que não aparecem como registros no qa_pairs exportado. O único selecionado referencia Q_0114 e Q_0115, ambos ausentes. Isso confirma uma lacuna de resolução local; a causa pode ser exportação limitada a perguntas respondidas, escopo distinto ou erro de contrato. O código precisa explicar e corrigir a representação.

2. Seleção muito restrita

O funil reportado é 55 candidatos → 52 após dedup → 1 selecionado. O catálogo original contém 54 não elegíveis; o relatório após dedup informa 51 excluídos. Isso é compatível com três alternativas removidas, e não comprova falha de contagem.

O rank 1 MOMENT_PRESERVED_00005_0000 tem score 0,854, dura 35,44 s e está ineligible para shortlist/review; hook=null aparece em missing_required_components. É evidência para investigar a relação entre score, completude de campos, confiança e gate. Não prova que o candidato deva ser aprovado.

Um fragmento de 1,46 s aparece no rank 5 com score 0,737 e clean_ending=true. Precisamos separar fragmentos úteis como hook de cortes autônomos.

3. Percepção e câmera limitadas

Active speaker confirmado reportado: 0 s e cobertura zero. Associação provável, mapeamento global e fala contemporânea são métricas diferentes. Existem 653 identidades persistentes; isso sinaliza necessidade de investigar fragmentação, mas não é contagem real de pessoas.

YOLO ficou indisponível, segundo o relatório, com fallback HOG. Há 1814 tracks, 916 microtracks, duração mediana de aproximadamente 1 s e sucesso de embedding de aproximadamente 34,90%.

Foco de câmera resolvido: aproximadamente 1,95%; preservação/fallback: aproximadamente 98,05%. Há 183 oportunidades de zoom, zero requests e zero eventos entregues. O motivo reportado é falta de alvo seguro/confirmado. Corrigir a percepção pode permitir mais câmera; forçar zoom não resolve a causa.

4. Revisão de legendas e apresentação

O relatório S7 registra 0 candidatos selecionados avaliados, enquanto o pacote final contém 1 story. O story está NOT_EVALUATED para legenda; safe area final=false. A ordem ou snapshot da revisão é uma hipótese que exige código.

O título atual é uma frase literal interrompida. A variante individual diz requires_review=false e o status geral pede revisão editorial; a semântica dos flags precisa ser esclarecida.

5. Compreensão e contexto

Há 70 tópicos e 69 seções; zero story arcs completos reportados. A qualidade desses recortes exige leitura global e, depois, áudio. O bloco semântico 6 usou fallback sinalizado. Não se deve descartar a evidência preservada nem completar histórias ficticiamente.

possible_name=Tipo em um participante e type=event para Rodox são casos concretos para revisar vocativos e entidades usando contexto.

6. Readiness e qualidade

Os recursos do brief/manifesto estão true, mas analysis_status=partial e gate=P1_DEGRADED. O quality_summary registra active_speaker_known_person como capacidade ausente. Isso exige escopos claros, não trocar tudo para false indiscriminadamente.

OCR comercial foi skipped por ocr_disabled; zero comerciais excluídos não prova ausência de comercial. A região detectada como lower_third no selecionado pode corresponder a objetos/cenário, hipótese a confrontar com frames e detector.

7. Desempenho

A soma de tempos das etapas listadas é 3135,78 s, aproximadamente 52 min 16 s; não é certificação do tempo total de parede. Semântica e tracking dominam os tempos reportados. Um run com todos os cache_hit=false não prova erro de cache.

## Limites desta auditoria

Não foi possível confirmar fidelity/WER, DER, identidade real, sincronismo audiovisual, correção de active speaker, fluidez do Director ou render final sem mídia e referência. Nenhuma alteração do programa foi feita.

Os identificadores de versão/build e schemas diferentes precisam de matriz de compatibilidade; não são automaticamente inconsistentes. Hash de mídia declarado e hash do ZIP medido são identificadores diferentes.

Os nomes dos relatórios/checkpoints e contratos de diagnóstico deste kit são propostas de workflow, não arquivos já existentes no analisador. O schema de decisões existente é preservado como fonte autoritativa.
