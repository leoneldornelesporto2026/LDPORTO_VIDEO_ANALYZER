"""Create only a synthetic editorial PDF for independent Windows reader checks."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'src'))

from ldporto.editorial_pdf import EditorialPDF

import cv2
import numpy as np

fixture_root = Path(__file__).resolve().parent
folder = (fixture_root / sys.argv[1]).resolve() if len(sys.argv) > 1 else fixture_root
if not folder.is_relative_to(fixture_root):
    raise ValueError('fixture_output_outside_visual_report')
folder.mkdir(parents=True, exist_ok=True)
pdf = EditorialPDF('Teste sintético de revisão – João, ação e música',
                   'Sem mídia real, sem inferência, sem aprovação de publicação.')
pdf.section('Áudio, evidências e limites')
pdf.text('Ação, coração e música: café às três. São Paulo – revisão de legendas.',
         url='https://example.invalid/synthetic-source?t=12')
pdf.text('Separação de caracteres: espaço normal / espaço\u00a0inseparável; hífen-normal / hífen\u00adopcional.')
pdf.text('Identificador longo: ' + 'SYNTHETIC_' + '0123456789ABCDEF' * 12)
image = np.zeros((160, 400, 3), dtype=np.uint8)
image[:, :100] = (40, 70, 220)
image[:, 100:200] = (50, 200, 70)
image[:, 200:300] = (210, 90, 35)
image[:, 300:] = (40, 200, 220)
cv2.putText(image, 'SYNTHETIC ONLY', (45, 90), cv2.FONT_HERSHEY_SIMPLEX, .9,
            (255, 255, 255), 2)
ok, data = cv2.imencode('.jpg', image)
if not ok:
    raise ValueError('synthetic_jpeg_fixture_failed')
pdf.image(data.tobytes(), 'Imagem sintética de teste. Não representa frame de vídeo ou evidência do show.')
for section in range(4):
    pdf.section('Seção sintética %d – transcrição e pendências' % (section + 1))
    for row in range(16):
        pdf.text('%02d:%02d · SPEAKER_SYNTHETIC · Trecho sintético %d: revisão de câmera, palavras, '
                 'aceleração, margem segura e evidência. Não é transcrição real.' %
                 (section, row, section * 16 + row))
path = folder / 'synthetic_editorial.pdf'
result = pdf.save(path)
report = {'scope': 'synthetic_pdf_no_source_media_or_inference', 'pdf': path.name,
          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), **result}
(folder / 'fixture_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
