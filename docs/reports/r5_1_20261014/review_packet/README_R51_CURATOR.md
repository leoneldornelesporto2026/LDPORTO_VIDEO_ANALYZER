# Consumo R5.1 no VIDEO CURATOR

1. Verifique SHA-256 do ZIP e todos os hashes de SECOND_CURATION_MANIFEST.json.
2. Leia SECOND_CURATION_SEMANTIC_HANDOFF.json e valide social/story_visual_handoff.json pelo schema enviado.
3. Resolva IDs em editorial/story_series_proposals.json, editorial/story_units.json e transcript/relevant_segments.jsonl.
4. Vincule o original pelo source_sha256; os intervalos são segundos absolutos da fonte. edit_mapping é proposta e exige confirmar a montagem. Não substitua os sete Reels existentes.
5. Consuma títulos, alternativas, captions, tokens de fala, destaques e capa como propostas. O Curator aplica seus presets de câmera, safe areas, watermark, instrumental, PNG final e render.
6. Nenhuma etapa de importação destes metadados exige Whisper, Qwen, visão ou Director. Não use um comando que dispare novamente o Analyzer. Importação automática na versão instalada do Curator não foi modificada nem comprovada: valide sua compatibilidade antes de aplicar a uma revisão nova.
7. Escuta, conferência de fatos, direitos, câmera, layout, preview e autorização de publicação continuam gates independentes.
