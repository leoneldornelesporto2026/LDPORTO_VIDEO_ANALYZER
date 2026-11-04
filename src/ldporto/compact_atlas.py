"""Searchable R6.3 atlas from existing indexed evidence; no inference or media I/O.

All detected scene rows and all Reel/Story IDs remain visible. Shared contact
sheets are embedded once as PDF image objects, even when several pieces use one.
The JSONs remain the structured source; this PDF cannot approve a camera/render.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

from .core import file_hash
from .editorial_pdf import EditorialPDF
from .project_export import _logical, _safe_ancestors


PDF_REF = '08_REPORTS/VISUAL_ATLAS.pdf'
_HASH = re.compile(r'^[a-f0-9]{64}$')


class _SharedImagePDF(EditorialPDF):
    """Keep the existing PDF layout/writer; reuse identical JPEG XObjects."""

    def __init__(self, *args):
        super().__init__(*args)
        self.image_by_hash = {}
        self.shared_image_reuses = 0

    def image(self, jpeg, caption=''):
        checksum = hashlib.sha256(jpeg).hexdigest()
        previous = self.image_by_hash.get(checksum)
        index = len(self.images)
        super().image(jpeg, caption)
        if previous is None:
            self.image_by_hash[checksum] = index
            return
        self.images.pop()
        old_ref, shared_ref = ('/I%d Do' % index).encode(), ('/I%d Do' % previous).encode()
        for page in self.pages:
            if index in page['images']:
                page['images'] = list(dict.fromkeys(previous if item == index else item for item in page['images']))
                page['commands'] = [command.replace(old_ref, shared_ref) for command in page['commands']]
        self.shared_image_reuses += 1


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _asset(root, reference):
    path = _safe_ancestors(root / str(_logical(reference)))
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('compact_atlas_asset_missing:' + reference)
    return path


def _document(root, reference, default=None):
    return json.loads(_asset(root, reference).read_text(encoding='utf-8')) if reference else default


def _rows(value, key):
    return value.get(key, []) if isinstance(value, dict) else value if isinstance(value, list) else []


def _label(value, fallback='UNKNOWN; evidência não registrada.'):
    if value in (None, '', [], {}):
        return fallback
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return str(value)


def _interval_text(rows):
    return '; '.join('%.3f–%.3f s' % (row['start'], row['end']) for row in rows
                     if _number(row.get('start')) and _number(row.get('end')))


def _jpeg(path):
    blob = path.read_bytes()
    if blob.startswith(b'\xff\xd8'):
        return blob
    # Mechanical format adaptation for the existing JPEG-only PDF writer.
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('compact_atlas_image_not_decodable:' + path.name)
    got, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not got:
        raise ValueError('compact_atlas_image_conversion_failed:' + path.name)
    return encoded.tobytes()


def _indexed_assets(root, atlas_index, source_sha256, duration):
    frames, sheets = {}, {}
    for row in atlas_index.get('frames') or []:
        fid = row.get('frame_id')
        if not isinstance(fid, str) or not fid or fid in frames:
            raise ValueError('compact_atlas_frame_id_missing_or_duplicate')
        if row.get('source_sha256') != source_sha256:
            raise ValueError('compact_atlas_frame_source_identity_mismatch:' + fid)
        if not _number(row.get('source_time_s')) or not 0 <= row['source_time_s'] < duration:
            raise ValueError('compact_atlas_frame_timestamp_invalid:' + fid)
        path = _asset(root, row['path'])
        if file_hash(path) != row.get('sha256'):
            raise ValueError('compact_atlas_frame_checksum_mismatch:' + fid)
        frames[fid] = row
    for row in atlas_index.get('contact_sheets') or []:
        sid = row.get('sheet_id')
        if not isinstance(sid, str) or not sid or sid in sheets:
            raise ValueError('compact_atlas_sheet_id_missing_or_duplicate')
        if file_hash(_asset(root, row['path'])) != row.get('sha256'):
            raise ValueError('compact_atlas_sheet_checksum_mismatch:' + sid)
        sheets[sid] = row
    return frames, sheets


def build_compact_atlas(root, *, metadata, scenes, reels, stories, series, atlas_index,
                        coverage, limitations, revision):
    """Write ``08_REPORTS/VISUAL_ATLAS.pdf`` from compact package-relative refs.

    The global transcript is loaded once. A piece uses indexed segment IDs, never
    a summary substituted for canonical text. Existing destinations are rejected.
    """
    root = _safe_ancestors(root)
    source_sha256 = metadata.get('sha256') or metadata.get('source_sha256')
    if not _HASH.fullmatch(str(source_sha256)) or not revision:
        raise ValueError('compact_atlas_source_identity_or_revision_invalid')
    duration = metadata.get('duration')
    if not _number(duration) or duration <= 0:
        raise ValueError('compact_atlas_source_duration_invalid')
    source = metadata.get('source') or {}
    title = metadata.get('title') or source.get('title') or source.get('id') or 'Vídeo com identidade SHA256 registrada'
    scene_by_id = {}
    for scene in scenes:
        sid, a, b = scene.get('scene_id'), scene.get('start'), scene.get('end')
        if not sid or sid in scene_by_id or not (_number(a) and _number(b) and 0 <= a < b <= duration + 1e-6):
            raise ValueError('compact_atlas_scene_id_or_interval_invalid')
        scene_by_id[sid] = scene
    piece_ids = [row.get('candidate_id') for row in reels] + [row.get('story_id') for row in stories]
    if any(not value for value in piece_ids) or len(piece_ids) != len(set(piece_ids)):
        raise ValueError('compact_atlas_piece_id_missing_or_duplicate')
    frames, sheets = _indexed_assets(root, atlas_index, source_sha256, duration)
    transcript_ref = '02_TRANSCRIPT/transcript_segments.json'
    segments = _rows(_document(root, transcript_ref, []), 'segments')
    by_segment = {}
    for row in segments:
        sid = row.get('segment_id')
        if not sid or sid in by_segment:
            raise ValueError('compact_atlas_canonical_segment_id_missing_or_duplicate')
        if not (_number(row.get('start')) and _number(row.get('end'))
                and 0 <= row['start'] < row['end'] <= duration + 1e-6):
            raise ValueError('compact_atlas_canonical_segment_time_invalid')
        by_segment[sid] = row
    global_camera_ref = '07_CAMERA/camera_decisions.json'
    global_camera = _document(root, global_camera_ref, {}) if (root / global_camera_ref).is_file() else {}
    decision_by_id = {row['decision_id']: row for row in _rows(global_camera, 'decisions') if row.get('decision_id')}
    sheets_for_frame = {}
    for sid, sheet in sheets.items():
        for fid in sheet.get('frame_ids') or []:
            sheets_for_frame.setdefault(fid, sid)
    jpeg_cache = {}
    def image(reference):
        if reference not in jpeg_cache:
            jpeg_cache[reference] = _jpeg(_asset(root, reference))
        return jpeg_cache[reference]
    pdf = _SharedImagePDF('ATLAS VISUAL · ' + str(title), 'R6.3 · segunda curadoria · revisão ' + str(revision))
    pdf.section('A · Panorama da fonte e cobertura')
    pdf.text('Identidade SHA256: ' + source_sha256, 9)
    pdf.text('Duração original: %.3f segundos. Fonte: %s.' % (duration, _label(source.get('id'))))
    pdf.text('Este atlas organiza evidências já persistidas. Imagens são amostras temporais; não comprovam visibilidade contínua, identidade nominal, segurança de crop, zoom entregue ou aprovação humana.')
    pdf.text('Os JSONs são a fonte estruturada das decisões. A segunda curadoria poderá substituir as sugestões de câmera; o Curator ainda verifica geometria, render e gates humanos.')
    pdf.text('Índice completo: %d cenas, %d Reels, %d Stories/partes e %d séries propostas. Nenhuma cena foi omitida deste índice.' %
             (len(scenes), len(reels), len(stories), len(series)))
    pdf.text('Imagens únicas no índice: %d. Folhas de contato compartilhadas: %d. As mesmas folhas podem reaparecer nas peças sem duplicar o bitmap dentro deste PDF.' % (len(frames), len(sheets)))
    scalar_coverage = {key: value for key, value in coverage.items() if not isinstance(value, (list, dict))}
    pdf.text('Métricas declaradas no relatório de cobertura: ' + _label(scalar_coverage), 8)
    pdf.text('Consulte 00_OVERVIEW/navigation_index.json, 01_TIMELINE/scene_index.json e 08_REPORTS/COVERAGE_REPORT.json para os índices completos e as lacunas medidas.', 9)
    pdf.section('Índice de todas as cenas e planos')
    missing_refs, scenes_without_frames, missing_segments = [], [], []
    for scene in scenes:
        sid = scene['scene_id']
        pdf.text('%s | %.3f–%.3f s | plano %s | geometria %s' %
            (sid, scene['start'], scene['end'], _label(scene.get('shot_type'), 'UNKNOWN'),
             _label(scene.get('geometry_state'), 'UNKNOWN')), 9)
        pdf.text('Pessoas em amostras: %s | frames: %s | pendências: %s' %
            (_label(scene.get('person_ids'), 'UNKNOWN'), _label(scene.get('frame_ids'), 'sem imagem'),
             _label(scene.get('missing_evidence'), 'nenhuma lacuna adicional declarada; amostragem continua limitada')), 8)
        if not scene.get('frame_ids'):
            scenes_without_frames.append(sid)
        for fid in scene.get('frame_ids') or []:
            if fid not in frames:
                missing_refs.append({'owner_id': sid, 'frame_id': fid})
    pdf.section('Contatos globais em ordem temporal')
    ordered_sheets = sorted(sheets.values(), key=lambda row: min(
        (frames[fid]['source_time_s'] for fid in row.get('frame_ids') or [] if fid in frames), default=duration))
    for sheet in ordered_sheets:
        known = [frames[fid] for fid in sheet.get('frame_ids') or [] if fid in frames]
        times = '%.3f–%.3f s' % (min(row['source_time_s'] for row in known), max(row['source_time_s'] for row in known)) if known else 'tempo desconhecido'
        pdf.text(sheet['sheet_id'] + ' | ' + times, 10)
        pdf.image(image(sheet['path']), 'Cenas: ' + _label(sheet.get('scene_ids'), 'UNKNOWN') + '. Frames e tempos completos: 06_VISUAL_ATLAS/atlas_index.json.')
    def gallery(piece):
        ordered = sorted((frames[fid] for fid in piece.get('frame_ids') or [] if fid in frames), key=lambda row: row['source_time_s'])
        if not ordered:
            pdf.text('SEM IMAGEM ASSOCIADA: inspecionar os intervalos originais desta peça; nenhuma aparência visual foi presumida.', 9)
        shown = set()
        for frame in ordered:
            fid = frame['frame_id']
            sid = sheets_for_frame.get(fid)
            key = sid or fid
            if key in shown:
                continue
            shown.add(key)
            if sid:
                sheet = sheets[sid]
                matched = [row for row in ordered if sheets_for_frame.get(row['frame_id']) == sid]
                caption = 'Peça: ' + ', '.join('%s @ %.3f s' % (row['frame_id'], row['source_time_s']) for row in matched)
                pdf.image(image(sheet['path']), sid + ' | ' + caption)
            else:
                pdf.image(image(frame['path']), fid + ' | fonte %.3f s | sem contato global associado.' % frame['source_time_s'])
        for fid in piece.get('frame_ids') or []:
            if fid not in frames:
                missing_refs.append({'owner_id': piece.get('candidate_id') or piece.get('story_id'), 'frame_id': fid})
    def piece_detail(piece, ident, kind):
        editorial = _document(root, piece.get('editorial_ref'), {}) or {}
        storyboard = _document(root, piece.get('visual_storyboard_ref'), {}) or {}
        camera = _document(root, piece.get('camera_geometry_ref'), {}) or {}
        captions = _document(root, piece.get('caption_evidence_ref'), {}) or {}
        pdf.section(kind + ' · ' + ident)
        pdf.text('Fonte original: ' + (_interval_text(piece.get('source_intervals') or []) or 'UNKNOWN'))
        if kind == 'Reel':
            pdf.text('Ranking original: ' + _label(piece.get('rank_original')))
        pdf.text('Resumo registrado: ' + _label(editorial.get('summary')))
        pdf.text('Gancho registrado, sujeito a revisão: ' + _label(editorial.get('hook') or editorial.get('original_hook')))
        pdf.text('Títulos propostos, sem aprovação: ' + _label(editorial.get('title_proposals')))
        pdf.text('Scores/critérios originais: ' + _label(editorial.get('original_scores')), 8)
        if isinstance(piece.get('person_ids'), list):
            observed_people = piece['person_ids']
            people_scope = 'Pessoas com observações nos intervalos da peça'
        else:
            observed_people = sorted({pid for sid in piece.get('scene_ids') or [] for pid in
                (scene_by_id.get(sid) or {}).get('person_ids') or []})
            people_scope = 'Pessoas registradas nas cenas associadas; presença no corte não verificada'
        pdf.text('Cenas: ' + _label(piece.get('scene_ids'), 'UNKNOWN') + '. ' + people_scope + ': ' + _label(observed_people, 'UNKNOWN'), 9)
        pdf.text('Instrumentos observados: ' + _label(piece.get('instrument_ids') or editorial.get('instrument_ids') or editorial.get('instruments'), 'UNKNOWN; nenhuma associação comprovada fornecida.'))
        beats = storyboard.get('beats') or []
        actions = [row.get('observed_action') or row.get('action_description') for row in beats
            if (row.get('observed_action') or row.get('action_description')) not in (None, '', 'UNKNOWN')]
        pdf.text('Ação principal registrada: ' + _label(actions, 'UNKNOWN; o atlas não inferiu ações a partir das miniaturas.'))
        pdf.text('Câmera proposta / geometria: ' + _label(camera.get('summary') or camera.get('geometry_state') or camera.get('sufficiency') or camera.get('status')))
        decisions = [decision_by_id[ident] for ident in camera.get('decision_ids') or [] if ident in decision_by_id]
        if decisions:
            counts = {}
            for decision in decisions:
                mode = decision.get('mode') or 'UNKNOWN'
                counts[mode] = counts.get(mode, 0) + 1
            pdf.text('Modos propostos por segmento: ' + _label(counts), 9)
            pdf.text('Alvos propostos, sem identidade nominal: ' + _label(sorted({pid for row in decisions
                for pid in row.get('target_person_ids') or []}), 'UNKNOWN'), 9)
        pdf.text('Trajetórias observadas referenciadas: %d. Planos de câmera referenciados: %d. Preservação de cabeça completa, mãos e instrumentos depende de evidência própria.' %
            (len(camera.get('trajectory_ids') or []), len(camera.get('decision_ids') or [])), 9)
        pdf.text('JSON de câmera: ' + _label(piece.get('camera_geometry_ref')) + '. Risco de corte e áreas protegidas devem ser conferidos com a geometria observada, independentemente do modo sugerido.', 8)
        pdf.text('Estado de legenda: ' + _label(captions.get('status') or captions.get('caption_status')))
        pdf.text('Estado editorial: ' + _label(editorial.get('review_status') or piece.get('review_state')) + '. Aprovação humana: pendente.')
        gallery(piece)
        pdf.text('Transcrição canônica disponível associada, sem preencher lacunas:', 10)
        available = 0
        for sid in piece.get('transcript_segment_ids') or []:
            row = by_segment.get(sid)
            if row is None:
                missing_segments.append({'owner_id': ident, 'segment_id': sid})
                pdf.text(sid + ' | referência sem segmento disponível.', 9)
                continue
            available += 1
            pdf.text('%s | %.3f–%.3f s | %s' % (sid, row['start'], row['end'], row.get('text', '')), 9)
        if not available:
            pdf.text('SEM TRANSCRIÇÃO ASSOCIADA disponível nos IDs fornecidos; tipo de áudio e conteúdo permanecem incertos.', 9)
        pdf.text('Pendências da peça: ' + _label(editorial.get('missing_evidence') or storyboard.get('missing_evidence') or camera.get('missing_evidence'), 'Verificar amostragem, alinhamento, identidade e regiões protegidas nos JSONs.'), 8)
    pdf.section('B · Reels e evidências por candidato')
    for piece in reels:
        piece_detail(piece, piece['candidate_id'], 'Reel')
    pdf.section('C · Stories e continuidade narrativa')
    story_by_id = {row['story_id']: row for row in stories}
    missing_story_refs = []
    for row in series:
        pdf.text(str(row.get('series_id')) + ' | ' + _label(row.get('title'), 'Tema não confirmado.'), 11)
        pdf.text('Continuidade registrada: ' + _label(row.get('continuity_status'), 'CONTINUITY_UNVERIFIED'))
        pdf.text('Ordem proposta das partes: ' + _label(row.get('part_ids')))
        for part_id in row.get('part_ids') or []:
            if part_id not in story_by_id:
                missing_story_refs.append({'series_id': row.get('series_id'), 'story_id': part_id})
        pdf.text('A ordem apresentada é uma proposta vinculada à fonte e não prova um arco completo ou encerramento.', 9)
    for piece in stories:
        piece_detail(piece, piece['story_id'], 'Story')
        pdf.text('Séries associadas: ' + _label(piece.get('series_ids'), 'INDEPENDENT_MOMENT'))
        continuity = _document(root, piece.get('continuity_ref'), {}) or {}
        pdf.text('Continuidade e função narrativa: ' + _label(continuity or piece.get('continuity_status'), 'CONTINUITY_UNVERIFIED'))
    pdf.section('D · Evidência insuficiente e inspeções necessárias')
    pdf.text('Cenas sem imagens: %d. Referências de frames ausentes: %d. Referências de transcrição ausentes: %d. Partes de série não resolvidas: %d.' %
        (len(scenes_without_frames), len(missing_refs), len(missing_segments), len(missing_story_refs)))
    pdf.text('Cenas sem imagem: ' + _label(scenes_without_frames, 'Nenhuma cena sem referência de imagem no índice; isso não certifica cobertura contínua.'), 8)
    pdf.text('Referências visuais sem entrada: ' + _label(missing_refs, 'Nenhuma referência ausente detectada.'), 8)
    pdf.text('Transcrições não resolvidas: ' + _label(missing_segments, 'Nenhuma referência ausente detectada.'), 8)
    pdf.text('Continuidade sem parte resolvida: ' + _label(missing_story_refs, 'Nenhuma referência ausente detectada.'), 8)
    pdf.text('Limitações fornecidas pelo exportador: ' + _label(limitations), 8)
    pdf.text('Pessoas anônimas, instrumentos não localizados, tracking fragmentado, alinhamento pendente e câmeras incertas permanecem como lacunas. Ausência de observação não significa ausência da pessoa, instrumento ou obstáculo.')
    pdf.text('Nenhuma aprovação de crop, legenda, prévia ou publicação foi criada por este PDF. Consulte timestamps e dados espaciais antes de decidir; quando faltarem, inspecione o original nesses intervalos.')
    path = root / PDF_REF
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('compact_atlas_revision_already_exists')
    staged = path.with_name('.VISUAL_ATLAS_' + uuid.uuid4().hex + '.partial.pdf')
    result = pdf.save(staged)
    if not staged.read_bytes().startswith(b'%PDF-'):
        raise ValueError('compact_atlas_pdf_header_invalid')
    staged.replace(path)
    return {'pdf_ref': PDF_REF, 'pdf_sha256': file_hash(path), 'pdf_bytes': path.stat().st_size,
        'pdf_pages': result['pages'], 'searchable': result['searchable'],
        'unique_embedded_images': len(pdf.images), 'shared_image_reuses': pdf.shared_image_reuses,
        'scene_count': len(scenes), 'reel_count': len(reels), 'story_count': len(stories), 'series_count': len(series),
        'scenes_without_frames': scenes_without_frames, 'missing_frame_references': missing_refs,
        'missing_transcript_references': missing_segments, 'missing_story_references': missing_story_refs,
        'source_sha256': source_sha256, 'revision': revision,
        'editorial_state': 'PARTIAL', 'continuous_visual_coverage_confirmed': False,
        'preview_approved': False, 'publication_ready': False}
