"""Chronological PDF views of the complete scene export, without inference.

Consumes contact sheets already produced by the visual exporter. This helper
never opens the original video, selects editorial candidates, or invents text.
"""
import json
import math
from decimal import Decimal
from pathlib import Path
import uuid

from .core import digest, file_hash
from .editorial_pdf import EditorialPDF
from .project_export import _logical, _safe_ancestors


RECEIPT_REF = 'VISUAL_SCENES_ATLAS_RECEIPT.json'
PRODUCER = 'ldporto.visual_scenes_atlas.v1'


def _millis(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def _stamp(value):
    # The capture index can retain microseconds as fractional milliseconds.
    # Keep those digits rather than silently relabelling a decoded timestamp.
    seconds, micros = divmod(round(Decimal(str(value)) * 1000), 1000000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    suffix = '%06d' % micros if micros % 1000 else '%03d' % (micros // 1000)
    return '%02d:%02d:%02d.%s' % (hours, minutes, seconds, suffix)


def _sheet_paths(scene):
    values = list(scene.get('contact_sheets') or [])
    if not values and scene.get('contact_sheet'):
        values = [scene['contact_sheet']]
    paths = []
    for value in values:
        name = value.get('path') if isinstance(value, dict) else value
        if not isinstance(name, str):
            raise ValueError('visual_scenes_atlas_contact_reference_invalid')
        _logical(name)
        if name not in paths:
            paths.append(name)
    return paths


def _segment_rows(rows):
    if isinstance(rows, dict):
        return rows.get('segments') or []
    return list(rows)


def _frames(row):
    return sorted(row.get('frames') or [], key=lambda item: item['timestamp_ms'])


def _sheets_for_part(scene, begin, end):
    sheets = _sheet_paths(scene)
    frames = _frames(scene)
    # The existing contact-sheet layout contains six chronological captures.
    # When the exporter supplies a different shape, preserve every sheet rather
    # than guessing which source frames it contains.
    if not frames or len(sheets) != math.ceil(len(frames) / 6):
        return sheets
    window_frames = {row.get('frame_id')
                     for window in scene.get('micro_windows') or []
                     if window['start_ms'] < end and window['end_ms'] > begin
                     for row in window.get('frames') or []}
    return [name for offset, name in enumerate(sheets)
            if any(begin <= row['timestamp_ms'] < end or row.get('frame_id') in window_frames
                   for row in frames[offset * 6:(offset + 1) * 6])]


def _validate_index(index):
    duration = index.get('video_duration_ms')
    if not _millis(duration) or duration <= 0:
        raise ValueError('visual_scenes_atlas_duration_ms_invalid')
    scenes = list(index.get('scenes') or [])
    seen = set()
    for scene in scenes:
        sid, start, end = scene.get('scene_id'), scene.get('start_ms'), scene.get('end_ms')
        if (not isinstance(sid, str) or not sid or sid in seen or not _millis(start)
                or not _millis(end) or not 0 <= start < end <= duration
                or not _millis(scene.get('duration_ms', end - start))
                or not math.isclose(scene.get('duration_ms', end - start), end - start,
                                    abs_tol=0.000001, rel_tol=0)):
            raise ValueError('visual_scenes_atlas_scene_identity_or_interval_invalid')
        seen.add(sid)
        for frame in scene.get('frames') or []:
            timestamp = frame.get('timestamp_ms')
            if not _millis(timestamp) or not start <= timestamp < end:
                raise ValueError('visual_scenes_atlas_frame_outside_scene')
        for window in scene.get('micro_windows') or []:
            a, b = window.get('start_ms'), window.get('end_ms')
            if not _millis(a) or not _millis(b) or not start <= a < b <= end:
                raise ValueError('visual_scenes_atlas_micro_window_invalid')
            if any(not _millis(frame.get('timestamp_ms')) or not a <= frame['timestamp_ms'] < b
                   for frame in window.get('frames') or []):
                raise ValueError('visual_scenes_atlas_frame_outside_micro_window')
        _sheet_paths(scene)
    return duration, sorted(scenes, key=lambda row: (row['start_ms'], row['end_ms'], row['scene_id']))


def build_visual_scenes_atlas(root, index, transcript_segments=(), *, partition_ms=600000):
    """Build one short atlas or consecutive ten-minute PDFs from existing sheets.

    Scene IDs survive partition boundaries. The receipt permits unchanged PDF
    reuse and atomic repair of owned PDFs; foreign existing files are preserved.
    """
    root = _safe_ancestors(root)
    duration, scenes = _validate_index(index)
    if not isinstance(partition_ms, int) or isinstance(partition_ms, bool) or partition_ms <= 0:
        raise ValueError('visual_scenes_atlas_partition_ms_invalid')
    segments = _segment_rows(transcript_segments)
    by_segment = {}
    for row in segments:
        sid = row.get('segment_id')
        if not sid or sid in by_segment:
            raise ValueError('visual_scenes_atlas_segment_id_invalid')
        by_segment[sid] = row
    sheets = {}
    for scene in scenes:
        for name in _sheet_paths(scene):
            path = _safe_ancestors(root / str(_logical(name)))
            if not path.is_relative_to(root):
                raise ValueError('visual_scenes_atlas_contact_outside_root')
            sheets[name] = {'path': path, 'sha256': file_hash(path) if path.is_file() else None}
    source_status = index.get('source_export_status', index.get('export_status', 'PARTIAL'))
    # Exporters merge this receipt into their index. Hash only PDF inputs, so
    # those receipt fields and run counters do not invalidate unchanged reuse.
    pdf_input = {key: index.get(key) for key in ('video_duration_ms', 'source_sha256', 'original_scene_count')}
    pdf_input.update(export_status=source_status, scenes=scenes)
    fingerprint = digest({'producer': PRODUCER, 'index': pdf_input, 'transcript_segments': segments,
        'partition_ms': partition_ms, 'contact_hashes': {name: value['sha256'] for name, value in sheets.items()}})
    receipt_path = root / RECEIPT_REF
    receipt = {}
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt.get('producer') == PRODUCER and receipt.get('fingerprint') == fingerprint:
            valid = True
            for row in receipt.get('pdfs') or []:
                path = _safe_ancestors(root / str(_logical(row['path'])))
                valid = valid and path.is_file() and file_hash(path) == row['sha256']
            if valid and receipt.get('pdfs'):
                return {**receipt, 'reused_unchanged': True}
    root.mkdir(parents=True, exist_ok=True)
    count = math.ceil(duration / partition_ms)
    planned = []
    for part in range(count):
        begin, end = part * partition_ms, min(duration, (part + 1) * partition_ms)
        name = 'VISUAL_SCENES_ATLAS.pdf' if count == 1 else 'VISUAL_SCENES_ATLAS_%03d_%03d_MIN.pdf' % (
            begin // 60000, math.ceil(end / 60000))
        path = root / name
        owned = next((row for row in receipt.get('pdfs') or [] if row.get('path') == name), None)
        may_rebuild = (receipt.get('producer') == PRODUCER and owned and path.is_file()
                       and file_hash(path) == owned.get('sha256'))
        if path.exists() and not may_rebuild:
            raise FileExistsError('visual_scenes_atlas_requires_new_revision:' + name)
        planned.append((begin, end, name))
    pdfs, failures = [], []
    for begin, end, name in planned:
        pdf = EditorialPDF('ATLAS VISUAL COMPLETO DAS CENAS',
            '%s–%s | tempo absoluto da fonte | estado visual %s' % (_stamp(begin), _stamp(end), source_status))
        pdf.section('Fonte, cobertura e leitura')
        pdf.text('SHA256 da fonte: ' + str(index.get('source_sha256') or 'não informado'), 9)
        pdf.text('Duração original: %s (%s ms). Este atlas: [%s, %s).' %
            (_stamp(duration), duration, _stamp(begin), _stamp(end)))
        pdf.text('Todas as cenas do índice são percorridas em ordem cronológica. A seleção editorial de Reels e Stories não limita este atlas. Capturas são amostras; não representam análise de todos os frames.')
        pdf.text('COMPLETE refere-se à cobertura visual validada no índice, independentemente do estado editorial. Este PDF não aprova nomes, descrições, enquadramentos, legendas, prévias ou publicação.')
        pdf.text('Descrições e falas existentes são reproduzidas com suas referências. Ausências permanecem declaradas, sem completar acontecimentos ou transcrições.')
        pdf.text('Contact sheets preservam as páginas existentes. Partições podem compartilhar uma microjanela e suas imagens na fronteira, sempre com os timestamps originais.', 9)
        selected = [scene for scene in scenes if scene['start_ms'] < end and scene['end_ms'] > begin]
        if not selected:
            failures.append({'pdf': name, 'reason': 'no_scene_entries_for_interval'})
            pdf.text('Sem entradas de cena ou fallback para este intervalo. Cobertura pendente.')
        for scene in selected:
            sid = scene['scene_id']
            kind = scene.get('kind', 'SCENE')
            pdf.section(sid + (' | FALLBACK_INTERVAL' if kind == 'FALLBACK_INTERVAL' else ''))
            pdf.text('Cena original: [%s, %s) | duração %s ms.' %
                (_stamp(scene['start_ms']), _stamp(scene['end_ms']), scene.get('duration_ms', scene['end_ms'] - scene['start_ms'])))
            a, b = max(begin, scene['start_ms']), min(end, scene['end_ms'])
            if a != scene['start_ms'] or b != scene['end_ms']:
                pdf.text('Trecho desta cena neste PDF: [%s, %s). O ID original permanece o mesmo.' % (_stamp(a), _stamp(b)), 9)
            description = scene.get('description')
            if isinstance(description, str) and description.strip():
                pdf.text('Descrição existente [%s]: %s' % (scene.get('description_status') or 'status não fornecido', description))
            else:
                pdf.text('Descrição: não analisada (NOT_ANALYZED); nenhum acontecimento foi inferido.')
            windows = [row for row in scene.get('micro_windows') or [] if row['start_ms'] < end and row['end_ms'] > begin]
            if windows:
                pdf.text('Microjanelas da cena, em tempo absoluto:', 10)
            else:
                failures.append({'scene_id': sid, 'pdf': name, 'reason': 'micro_windows_missing'})
                pdf.text('Microjanelas não disponíveis; conferir o índice e a cobertura da cena.')
            for window in windows:
                values = _frames(window)
                label = str(window.get('micro_id') or 'microjanela sem ID')
                pdf.text('%s | [%s, %s) | %d capturas: %s' % (label, _stamp(window['start_ms']),
                    _stamp(window['end_ms']), len(values), ', '.join(_stamp(row['timestamp_ms']) for row in values) or 'nenhuma'), 9)
                if not values:
                    failures.append({'scene_id': sid, 'micro_id': window.get('micro_id'), 'pdf': name,
                                     'reason': 'micro_window_without_valid_capture'})
            available = _sheets_for_part(scene, begin, end)
            shown = 0
            for reference in available:
                asset = sheets[reference]
                if asset['sha256'] is None:
                    failures.append({'scene_id': sid, 'pdf': name, 'path': reference, 'reason': 'contact_sheet_missing'})
                    pdf.text('Contact sheet ausente: ' + reference, 9)
                    continue
                try:
                    pdf.image(asset['path'].read_bytes(), sid + ' | ' + reference + ' | capturas com timestamps absolutos da fonte.')
                    shown += 1
                except (OSError, ValueError) as exc:
                    failures.append({'scene_id': sid, 'pdf': name, 'path': reference,
                                     'reason': 'contact_sheet_invalid', 'error_type': type(exc).__name__})
                    pdf.text('Contact sheet inválido: ' + reference, 9)
            if not shown:
                failures.append({'scene_id': sid, 'pdf': name, 'reason': 'no_valid_contact_sheet_for_interval'})
            ids = scene.get('transcript_segment_ids') or []
            if ids:
                pdf.text('Falas/legendas canônicas relacionadas:', 10)
            else:
                pdf.text('Falas/legendas relacionadas: nenhuma referência canônica disponível.', 9)
            for segment_id in ids:
                segment = by_segment.get(segment_id)
                if segment is None:
                    pdf.text(str(segment_id) + ' | texto não fornecido; consulte a referência canônica.', 9)
                else:
                    pdf.text(str(segment_id) + ' | ' + str(segment.get('text') or ''), 9)
        target = root / name
        temporary = root / ('.' + name + '.' + uuid.uuid4().hex + '.partial')
        try:
            info = pdf.save(temporary)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        pdfs.append({'path': name, 'sha256': file_hash(target), 'bytes': target.stat().st_size,
            'start_ms': begin, 'end_ms': end, 'pages': info['pages'],
            'scene_ids': [scene['scene_id'] for scene in selected], 'searchable': info['searchable']})
    status = ('FAILED' if source_status == 'FAILED' or not pdfs else
              'COMPLETE' if source_status == 'COMPLETE' and not failures else 'PARTIAL')
    result = {'producer': PRODUCER, 'fingerprint': fingerprint, 'source_sha256': index.get('source_sha256'),
        'pdfs': pdfs, 'scene_count': len(scenes), 'video_duration_ms': duration,
        'export_status': status, 'source_export_status': source_status, 'failures': failures,
        'preview_approved': False, 'publication_ready': False, 'reused_unchanged': False}
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return result
