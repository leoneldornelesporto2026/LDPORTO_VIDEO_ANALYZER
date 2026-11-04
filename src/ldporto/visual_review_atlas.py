"""Human-readable atlas of existing Visual Frame Handoffs.

No video inference, automatic approvals or geometry interpolation. Source frames
are sparse evidence; the PDF never claims continuous visual coverage. All paths
are rooted in the produced per-piece handoff, not externally supplied links.
"""
from collections import Counter
import json
from pathlib import Path

from .core import file_hash
from .editorial_pdf import EditorialPDF
from .project_export import _logical


ATLAS_REF = 'VISUAL_FRAME_HANDOFF/REVISAO_VISUAL_POR_CORTE.pdf'
COVERAGE_REF = 'VISUAL_FRAME_HANDOFF/RELATORIO_COBERTURA_VISUAL.json'


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _read_piece(root, name):
    if not isinstance(name, str) or '/' in name or '\\' in name:
        raise ValueError('unsafe_visual_piece_id')
    _logical(name)
    folder = root / 'VISUAL_FRAME_HANDOFF' / name
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError('visual_piece_directory_missing:' + name)
    return folder


def build_visual_review_atlas(package_directory, pieces, *, source_sha256, revision):
    """Write one searchable atlas and a machine-checkable gap ledger.

    The atlas includes an existing per-piece contact sheet, not one exported
    PNG per media frame. The raw evidence stays indexed in FULL_AUDIT.
    """
    root = Path(package_directory)
    pdf = EditorialPDF('ATLAS VISUAL PARA SEGUNDA CURADORIA',
        'R6.2 | revisao humana obrigatoria | amostragem, nao video frame a frame')
    pdf.section('Como utilizar o atlas')
    pdf.text('Cada secao corresponde a um Reel ou parte de Story. A folha de contato contem frames amostrados da fonte, com tempos absolutos e tempos do corte. A geometria completa disponivel fica nos JSONs da respectiva peca.')
    pdf.text('ATENCAO: uma imagem amostrada NAO comprova visibilidade continua entre os tempos. Crop/zoom e posicionamento de texto precisam ser verificados no video original e no MP4 renderizado pelo Curator.')
    pdf.text('Se houver ausencia de frames, pessoas, instrumentos, regioes da cabeca/maos ou cameras, consulte as lacunas declaradas no RELATORIO_COBERTURA_VISUAL.json; nao preencha os vazios com suposicoes.')
    pdf.text('Referencias: camera_keyframes.json, visual_tracks.json, safe_areas.json, storyboard.json, scene_transitions.json e frame_index.json por peca.')
    report_rows = []
    ids = set()
    for index, piece in enumerate(pieces, 1):
        piece_id = piece['piece_id']
        if piece_id in ids:
            raise ValueError('visual_atlas_duplicate_piece')
        ids.add(piece_id)
        directory = _read_piece(root, piece_id)
        manifest = _read(directory / 'visual_handoff_manifest.json')
        frames = _read(directory / 'frame_index.json')
        tracks = _read(directory / 'visual_tracks.json')
        safe = _read(directory / 'safe_areas.json')
        camera = _read(directory / 'camera_keyframes.json')
        storyboard = _read(directory / 'storyboard.json')
        count = len(frames.get('frames') or [])
        camera_rows = camera.get('segments') or []
        mode_counts = Counter(str(x.get('mode', 'UNKNOWN')) for x in camera_rows)
        number_tracks = len(tracks.get('tracks') or [])
        n_instruments = int(tracks.get('instrument_observation_count') or 0)
        missing = len(frames.get('missing_frames') or [])
        gaps = list(manifest.get('gaps') or [])
        if count == 0:
            gaps.append('no_captured_source_frames')
        if number_tracks == 0:
            gaps.append('no_visual_tracks_for_piece')
        if not camera_rows:
            gaps.append('no_camera_segments')
        if n_instruments == 0:
            gaps.append('no_measured_instrument_observations')
        if safe.get('platform_margins_status') == 'unknown':
            gaps.append('title_caption_safe_zone_not_verified')
        gaps.append('continuous_visual_coverage_not_proven')
        gaps.append('head_and_hands_full_extent_not_proven')
        # JSON refs are always kept even when PDF samples are unavailable.
        refs = {key:'VISUAL_FRAME_HANDOFF/'+piece_id+'/'+key for key in (
            'visual_handoff_manifest.json','frame_index.json','visual_tracks.json',
            'safe_areas.json','camera_keyframes.json','scene_transitions.json',
            'thumbnail_candidates.json','storyboard.json')}
        row = {
            'piece_id':piece_id, 'piece_type':piece['piece_type'],
            'series_ids':piece.get('series_ids') or [], 'source_intervals':piece.get('source_intervals') or [],
            'captured_frames':count, 'missing_requested_frames':missing,
            'sampling_proposals':frames.get('sampling_proposals'),
            'omitted_sampling_proposals':frames.get('omitted_sampling_proposals'),
            'observations_in_time_filter':manifest.get('coverage',{}).get('observation_count',0),
            'visual_tracks':number_tracks, 'instrument_observations':n_instruments,
            'camera_segments':len(camera_rows), 'camera_mode_counts':dict(mode_counts),
            'storyboard_beats':len(storyboard.get('beats') or []),
            'continuous_visual_coverage_confirmed':False,
            'camera_final_render_verified':False,
            'overlay_placement_approved':False,
            'caption_preflight_ref':piece.get('caption_preflight_ref'),
            'human_review_required':True, 'publication_ready':False,
            'gap_codes':sorted(set(gaps)), 'detail_refs':refs,
        }
        report_rows.append(row)
        pdf.section('%03d | %s | %s' % (index, piece['piece_type'], piece_id))
        pdf.text('Frames capturados: %d | solicitados sem imagem: %d | tracking: %d | instrumentos observados: %d' % (
            count, missing, number_tracks, n_instruments))
        pdf.text('Segmentos de camera: %d | beats no storyboard: %d | modos: %s' % (
            len(camera_rows), len(storyboard.get('beats') or []),
            ', '.join('%s=%d' % (key,value) for key,value in mode_counts.most_common()) or 'nao informados'))
        intervals = row['source_intervals']
        for interval in intervals[:8]:
            pdf.text('Intervalo fonte: %.3f a %.3f segundos' % (float(interval['start']),float(interval['end'])))
        if len(intervals)>8:
            pdf.text('Intervalos adicionais: %d; veja o manifest JSON.' % (len(intervals)-8))
        pdf.text('Pendencias: '+', '.join(row['gap_codes']), 8)
        pdf.text('Camera: '+refs['camera_keyframes.json']+' | geometrias de origem; nao aprovadas.', 8)
        pdf.text('Tracklets: '+refs['visual_tracks.json']+' | observacoes esparsas, sem identidade nominal.', 8)
        pdf.text('Legendas: '+str(row['caption_preflight_ref'] or 'nao referenciadas'), 8)
        contact_rel = ((frames.get('contact_sheet') or {}).get('path'))
        if isinstance(contact_rel,str):
            sheet = directory / contact_rel
            # Accept only fixed internally generated sheet location.
            if contact_rel == 'contact_sheets/timeline.jpg' and sheet.is_file():
                pdf.image(sheet.read_bytes(), 'Folha de contato: fontes amostradas; recortes laranja sao propostas, nao verificacao de render.')
            else:
                pdf.text('Sem folha de contato validada; consulte frame_index.json.')
        else:
            pdf.text('Sem folha de contato capturada; a revisao do video original e necessaria.')
    overview = {
        'schema_version':'LDP_VISUAL_REVIEW_COVERAGE_R62_V1', 'revision':revision,
        'source_sha256':source_sha256, 'piece_count':len(report_rows),
        'reels':sum(1 for r in report_rows if r['piece_type']=='REEL'),
        'stories':sum(1 for r in report_rows if r['piece_type']=='STORY'),
        'captured_frames_total':sum(r['captured_frames'] for r in report_rows),
        'missing_requested_frames_total':sum(r['missing_requested_frames'] for r in report_rows),
        'pieces_without_source_frames':sum(not r['captured_frames'] for r in report_rows),
        'continuous_visual_coverage_confirmed':False,
        'editorial_state':'PARTIAL','human_review_required':True,
        'preview_approved':False,'publication_ready':False,
        'pdf_is_sparse_review_atlas_not_full_video':True,
        'render_geometry_verified':False,
        'heavy_evidence_in_full_audit':True,
        'pieces':report_rows,
    }
    report_path=root/COVERAGE_REF
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(overview,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    path=root/ATLAS_REF
    pdf_result=pdf.save(path)
    return {'pdf_ref':ATLAS_REF,'pdf_sha256':file_hash(path),'coverage_ref':COVERAGE_REF,
        'coverage_sha256':file_hash(report_path),'pdf_pages':pdf_result['pages'],'piece_count':len(report_rows)}
