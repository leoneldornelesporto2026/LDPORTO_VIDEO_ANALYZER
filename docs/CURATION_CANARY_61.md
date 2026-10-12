# Canário curto de curadoria 9:16 — etapa 61

A fixture offline codifica mídia sintética, queima uma legenda de teste, decodifica
1080×1920 com áudio e valida o core ZIP temporário por CRC/SHA. Ela comprova o
contrato técnico: `unit_fixture_pass`, `real_canary_not_run`. Não comprova OCR
real, transcrição, identidade, escuta, legibilidade nem qualidade editorial.

```powershell
python -m pytest -q src/tests/test_stage61_curation_canary.py -p no:cacheprovider --tb=short
```

Para uma execução real, fornecer e autorizar **um arquivo curto de 10–30s** e
seu JSON de evidência atual (metadata.sha256 exato, duração/dimensões,
main_moments com moment_id/ideal_start/ideal_end, transcript_segments existentes).
Não apontar para o episódio longo ou para mídia histórica do Clóvis.
Não existe transcrição nova neste comando. OCR Tesseract local é obrigatório;
não há instalação/download nem fallback para declarar OCR medido.

```powershell
python scripts/dev/curation_canary61.py --analysis caminho/evidencia_curta.json --source caminho/curto.mp4 --candidate-id M1 --output diagnostics/canary61_novo --authorize-short-media
```

O diretório deve ser novo. Fonte ausente/hash diferente, falta de autorização ou
intervalo fora dos limites impedem gerar MP4. O recibo sai no stdout; quando a
execução começa também fica em CANARY61.json. Exit 0 significa somente
`real_canary_pass` técnico; exit 2 significa não executado ou reprovado, com
reason_codes. Nenhum estado concede aprovação/publicação humana. A CLI não
gera ZIP, lote, upload ou serviços externos.

Reaproveita câmera atual; sem câmera, preserva a fonte inteira. Guarda camera.mp4,
captions.ass (SHA), preview.mp4 e recibos de decodificação, áudio, timestamps
de segmentos, OCR da fonte/saída com hashes de frames e movimento realmente
consumido pelo renderizador. Os timestamps continuam provenientes do JSON;
tom de teste não é fala real. Zoom consumido em frames não equivale a zoom
editorial aprovado.

viewport_audit compara caixas completas de cabeça (incluindo queixo), olhos,
texto e GC/QR nos instantes fornecidos com o crop interpolado e safe area.
Campos opcionais: people_observations[].head_bbox/eyes_bbox/time,
commercial_visual_s8.texts[].bbox/observed_at,
broadcast_graphics.intervals[].regions[].bbox/observed_at, normalizados 0–1.
Não infere cabeça/olhos a partir de rosto Haar. Ausências ficam NOT_MEASURED;
projeção de fonte não comprova segurança contínua nem texto codificado.
FACE_OR_HEAD_CLIPPED impõe preview_approved=false. Textos/GC cortados ou conflito
com a zona proposta de legenda exigem revisão. A legenda ASS usa o estilo atual;
a zona proposta da auditoria não é uma certificação desse compositor.

Homologar no Windows: fonts/libass e Tesseract por+eng instalados, caixas realmente
observadas vinculadas à fonte, cabeça/queixo/olhos ao longo do corte, GC/QR,
legendas completas e legíveis, escuta/timestamps e zoom proposto versus entregue.
Inspecionar o preview e registrar parecer humano por hash nos gates existentes.
READY da curadoria e canário técnico não significam PUBLISH_READY.
