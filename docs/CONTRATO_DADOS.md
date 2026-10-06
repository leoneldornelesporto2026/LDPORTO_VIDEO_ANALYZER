> Extensão v3: [CAMERA_DIRECTOR_V3.md](CAMERA_DIRECTOR_V3.md) e schemas/. Este contrato v1 permanece como referência histórica; campos de confiança do active speaker v3 são heurísticos e explicitamente não calibrados.

# Contrato de dados — schema 1.0

## Coordenadas

- start/end: segundos absolutos desde o início visual do vídeo.
- Intervalos são tratados como [start, end), exceto medições instantâneas.
- Bounding boxes: x, y, width, height normalizados em 0–1.
- confidence null: não existe probabilidade confiável fornecida.
- inference true: conclusão estimada por modelo/regra, não observação garantida.
- method: origem da medição ou inferência.

## Palavras

word preserva a unidade reconhecida. raw preserva o espaço/pontuação usados para
reconstruir a fala. Um token Whisper pode conter formas que não são uma palavra
lexical simples. Timestamps são estimativas por atenção.

Campos: word_id, word, raw, start, end, confidence, speaker, segment_id,
needs_review, timestamp_method, speaker_candidates, speech_overlap.

Imported words podem usar confidence null. O programa não fabrica probabilidades.
Um JSON com só segments é aceito, mas não recebe timestamps artificiais por palavra.

## Pessoas

people.json resume IDs anônimos. people_observations.json registra observações
por amostra. Nome civil fica null.

bbox_kind=face significa que bbox não é uma detecção de corpo.
safe_crop_possible refere-se à caixa definida por crop_target.

tracking_confidence fica null no matching por IoU/embedding, pois a similaridade
não é uma probabilidade calibrada. tracking_similarity conserva a medida real.

## Associação voz/pessoa

speaker_person_mapping.json usa visible_person=null se não resolvido.
association_evidence_score é correlação Pearson, não 91% de certeza.
association_confidence fica null sem calibração.

É possível fornecer uma correção manual no YAML:

    vision:
      manual_mapping_file: "C:/Dados/mapping.json"

Exemplo de mapping.json:

    [
      {
        "start": 0.0,
        "end": 120.0,
        "speaker": "SPEAKER_00",
        "person_id": "PERSON_001",
        "evidence": "Conferido por mim na entrevista"
      }
    ]

IDs precisam existir nos resultados. O intervalo manual precisa cobrir
integralmente o turn ao qual será aplicado nesta versão.
O matching manual não altera o reconhecimento das palavras.

## Timeline

Inclui intervalos de silêncio/sem fala para cobrir 0 até a duração final.
Mudanças de locutor, cena e tópico têm fronteiras próprias.

visible_people e people_positions são amostras próximas, com visual_observed_at.
Ausência de detecção não prova ausência física de uma pessoa.

active_person depende de voz vinculada e pessoa visível. Um rosto dominante pode
ficar sem foco quando não há vínculo confiável.

## Insights editoriais

topics inclui evidências por segment_id e method.
No modo heuristic, semantic_topic_change é null e summary é null.

editorial_moments apresenta categorias, contexto, limites candidatos e métricas
independentes. Scores LLM são subjetivos; scores sem evidência ficam null.
Não existe viral_score agregado.

complete_sentence é um teste de pontuação, não garantia linguística de completude.
A revisão humana deve conferir se a ideia está encerrada.

llm_insights.json mantém a transcrição completa por segmento e as informações
editoriais. Evita arrays de frames, caixas por amostra e palavras redundantes.
Dados detalhados continuam em analysis.json, words.json e people_observations.json.

## Compatibilidade com o editor futuro

O segundo programa deverá ler timestamps absolutos e associar plano editorial aos
segment_id/word_id. Não confiar numa estimativa de crop sem verificar continuidade,
qualidade visual, visibilidade e contexto.

Não existe cut_plan.json definitivo nesta fase. O futuro contrato de renderização
precisa ser acordado depois de escolher os cortes.
