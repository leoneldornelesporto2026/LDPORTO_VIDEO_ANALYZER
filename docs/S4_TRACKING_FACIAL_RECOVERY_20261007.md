# Sessão 4 — Recuperação facial e tracking conservador

## Escopo e estado de evidência

Código-fonte atualizado **a partir do R4.9/S3**, sem substituir os módulos anteriores. Nesta entrega há testes automatizados, mas **não há vídeo real nem arquivos completos `07_people_tracking.json`/`08_person_reid.json` do benchmark dos 742 micro-tracklets**. Portanto, **não** há evidência de redução da contagem 742, nem medição populacional de identidade correta. Somente as métricas novas, quando extraídas de uma execução real, permitem interpretar o funil.

## Problemas reais encontrados na implementação prévia

- Embeddings SFace só são criados com rosto detectado por YuNet. Um corpo detectado por HOG/YOLO não pode gerar SFace. Isso não é bug; é ausência de evidência facial.
- Se YuNet não encontra rosto, a implementação antiga não tentava segunda escala. Rostos menores e cortes de câmera curtos tinham baixa oportunidade de reconhecimento.
- O limiar de score YuNet era 0.85 fixo; `max_width` 960 reduz detalhes. Só havia agendamento extra para shots curtos.
- Qualidade visual (desfoque, tamanho, exposição, borda) não bloqueava embeddings ruins antes da etapa Re-ID.
- HOG de corpo inteiro não é detector ideal de pessoas sentadas; YOLO local estava restrito à configuração explícita.
- Os contadores de falta de embedding não distinguiam corpo sem rosto, detecção facial com baixa qualidade, SFace ausente e extração mal sucedida.
- Métricas heurísticas de fragmentação **não** correspondem a ID accuracy. Nenhuma anotação de verdade-terreno foi incluída.

## Mudanças

1. **YuNet multiescala limitada**: segunda inferência sobre frame ampliado 1.5× (apenas se orçamento de pixels permitir); inclui quadros com nenhum rosto e verificações periódicas quando há menos de dois rostos; NMS por IoU para evitar caixas duplicadas. Todas as coordenadas de landmarks/caixas resgatadas são convertidas de volta à resolução original antes de SFace. Contadores `face_rescue_calls`, `face_rescue_detected_faces`, `face_rescue_budget_skipped`.
2. **Evidência facial segura**: `assess_face` avalia tamanho em pixels, nitidez Laplaciana, exposição, clipping de borda, score e consistência dos landmarks oculares. Um rosto inadequado pode seguir no tracking/câmera, mas não produz embedding. `embedding_missing_reason` explica a lacuna por observação; `face_quality` é armazenada no tracking bruto.
3. **Retornos no corte de câmera**: `ShotBoundarySamplingPlan` coleta no máximo duas observações extras em cada shot longo (shots curtos continuam no plano antigo). Não atravessa limites semanticamente, nem cria medições de rosto fictícias. Métricas `boundary_*`.
4. **Pessoas sentadas**: `body_backend: auto` prefere YOLO-person **quando o modelo local estiver disponível**, sem download implícito; senão faz fallback explícito ao HOG. Rostos visíveis sem corpo detectado seguem sendo observações `FACE_ONLY_PERSON`. Detecção de pessoa sentada/ocluída **não é garantida** sem modelo apropriado.
5. **Re-ID estrito preservado**: similaridade facial e diferença para o segundo melhor concorrente, proibição de fusão de duas pessoas simultâneas, proteção especial para um único embedding de micro-tracklet. Posição da tela **nunca** determina identidade entre shots. A qualidade facial filtra embeddings antes de qualquer merge.
6. **Diagnóstico por causa**: `08_person_reid.json` inclui `embedding_gap_audit` e métricas `embedding_gap_tracklet_count`, `micro_embedding_absence_by_cause`. Não imputa faltas de evidência em runs antigos.
7. **Goldset humano**: CLI com amostragem estratificada entre micro/stable × com/sem embedding, distribuída temporalmente; CSV com `annotation_label` vazio e `annotation_status=unreviewed`. Com vídeo local, gera contact sheet real com caixa destacada. O avaliador só utiliza anotações `verified` e calcula falsos merges, falsos splits, precisão/recall por pares e identidades fragmentadas. Não preenche rótulos automaticamente.

## Executar no Windows Python 3.11

No diretório do projeto, usando o ambiente já instalado:

```bat
.venv\Scripts\python.exe scripts\dev\audit_tracking_s4.py "C:\caminho\da\analise" --output "C:\caminho\s4_audit"
```

A pasta/ZIP deve conter `07_people_tracking.json` e opcionalmente `08_person_reid.json`. Este comando **não** reexecuta Whisper, YOLO, MediaPipe ou vídeo. Para gerar folha visual, opcionalmente:

```bat
.venv\Scripts\python.exe scripts\dev\audit_tracking_s4.py "C:\caminho\da\analise" --output "C:\caminho\s4_audit" --video "C:\caminho\video.mp4"
```

Abra `identity_contact_sheet.jpg`, preencha `identity_annotations.csv`: mesmo indivíduo = mesma `annotation_label` **anônima** (por exemplo `G01`, `G02`), `annotation_status=verified`; marcação desconhecida: mantenha `unreviewed`.

```bat
.venv\Scripts\python.exe scripts\dev\audit_tracking_s4.py "C:\caminho\da\analise" --output "C:\caminho\s4_audit" --evaluate "C:\caminho\s4_audit\identity_annotations.csv"
```

Saídas: `tracking_s4_report.json`, `identity_annotations.csv`, `identity_contact_sheet.jpg` (se vídeo) e `identity_goldset_metrics.json` (se avaliado). Embeddings não são exportados para o CSV.

## Calibragem, recursos e rollout

- Defaults em `config/config.yaml`. Rescue e quality gate podem ser desligados em A/B (`face_rescue_upsample: false`, `face_quality_gate: false`). Desligar gate **reduz a segurança dos merges**.
- Usar modelos locais existentes em `models/` e testar no **Windows Python 3.11** com 1–3 min de vídeo de estúdio contendo cenas curtas, rostos pequenos e sentados. Esta execução não foi feita aqui.
- Compare before/after: micro sem embeddings por causa, novos embeddings qualificados, taxa de faces recuperadas, uso do YuNet extra, duração do estágio, pares false_merge/false_split na **mesma amostra anotada**. Não comparar só número de IDs.
- Calibrar thresholds com validação do usuário. O score de SFace e a similaridade cosseno **não são probabilidades calibradas**.
- Se houver múltiplos rostos fortemente ocluídos, considere detector facial treinado para perfis/oclusões ou pose/corpo, mas não inferir identidade civil nem afirmar suporte sem benchmark específico.
- Tracking, speaker↔person e camera só devem ser promovidos para READY após benchmarks correspondentes, não apenas por passar nos testes.
