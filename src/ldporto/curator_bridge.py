"""Read-only, fail-closed bridge from validated second-curation ZIP to legacy Curator V2.

The independent Curator application is not bundled or verified by this bridge.
The bridge produces *suggestions* for the Curator; it never marks a clip or video
as publication-ready, nor invents camera or visual observations.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import re
import tempfile
import zipfile

from .second_curation_export import validate_core_package


def _read_json(archive, name):
    return json.loads(archive.read(name))


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def _safe_score(value, fallback=0.5):
    try:
        number = float(value)
        return max(0.0, min(1.0, number)) if math.isfinite(number) else fallback
    except (TypeError, ValueError):
        return fallback


def audit_second_curation_package(package_path):
    package_path = Path(package_path)
    result = validate_core_package(package_path)
    report = {'validation': result, 'bridge_possible': False, 'publication_ready': False,
              'requires_manual_review': True, 'input_path': str(package_path)}
    if result['status'] != 'valid':
        report['blockers'] = ['package_invalid'] + result.get('errors', [])[:20]
        return report
    with zipfile.ZipFile(package_path) as z:
        manifest = _read_json(z, 'SECOND_CURATION_MANIFEST.json')
        shortlist = _read_json(z, 'editorial/default_shortlist.json').get('candidate_ids', [])
        candidates = _read_json(z, 'editorial/candidate_catalog.json').get('candidates', [])
        social = _read_json(z, 'social/stories_manifest.json') if 'social/stories_manifest.json' in z.namelist() else {}
    by_id = {candidate['candidate_id']: candidate for candidate in candidates}
    blockers = []
    for capability in ('editorial_ready', 'transcript_ready', 'visual_ready'):
        if not manifest.get('readiness', {}).get(capability):
            blockers.append(capability + '_false')
    if not shortlist:
        blockers.append('no_editorial_shortlist')
    if any(not by_id.get(cid, {}).get('default_shortlist_eligible', False) or
           not by_id.get(cid, {}).get('publication_eligible', False) or
           by_id.get(cid, {}).get('commercial_classification', {}).get('eligibility') == 'excluded'
           for cid in shortlist):
        blockers.append('shortlist_contains_ineligible_candidate')
    report.update(bridge_possible=not blockers, blockers=blockers, candidate_count=len(candidates),
                  shortlist_count=len(shortlist), story_count=len(social.get('stories', [])),
                  story_readiness=social.get('story_readiness'),
                  upstream_readiness=manifest.get('readiness', {}),
                  important='Compatible bridge is a curation input, NOT a publishable final render.')
    return report


def export_legacy_curator_bridge(package_path, output_dir):
    """Build a separate directory readable by Curator V2's find_analysis/load_bundle.

    Refuses PARTIAL packages and never overwrites a pre-existing analysis. This
    allows the existing Curator to continue its own human preview/approval gate.
    """
    package_path = Path(package_path)
    report = audit_second_curation_package(package_path)
    if not report['bridge_possible']:
        raise ValueError('Curator bridge blocked: ' + ', '.join(report['blockers']))
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path) as z:
        metadata = _read_json(z, 'source/metadata.json')
        catalog = _read_json(z, 'editorial/candidate_catalog.json')['candidates']
        selection = _read_json(z, 'editorial/default_shortlist.json')['candidate_ids']
        manifest = _read_json(z, 'SECOND_CURATION_MANIFEST.json')
        segment_rows = [json.loads(line) for line in z.read('transcript/relevant_segments.jsonl').decode('utf-8').splitlines() if line]
        word_rows = ([json.loads(line) for line in z.read('transcript/relevant_words.jsonl').decode('utf-8').splitlines() if line]
                     if 'transcript/relevant_words.jsonl' in z.namelist() else [])
        speakers = _read_json(z, 'people/speakers.json') if 'people/speakers.json' in z.namelist() else []
    by_id = {candidate['candidate_id']: candidate for candidate in catalog}
    source = metadata.get('source') or {}
    source_id = str(source.get('id') or (metadata.get('sha256') or 'video')[:12])
    source_id = re.sub(r'[^A-Za-z0-9_-]', '_', source_id)[:60]
    if not source_id:
        raise ValueError('Missing safe video ID')
    target = output_dir / (source_id + '_SECOND_CURATION_BRIDGE')
    if target.exists():
        raise FileExistsError(f'Refusing to overwrite previous Curator bridge: {target}')
    words_by_seg = defaultdict(list)
    for word in word_rows:
        if word.get('segment_id'):
            words_by_seg[word['segment_id']].append(word)
    editorial, review = [], []
    for rank, cid in enumerate(selection, 1):
        candidate = by_id[cid]
        generated = candidate.get('generated_copy') or {}
        title = generated.get('title_idea') or candidate.get('topic') or (candidate.get('transcript_literal') or '')[:80]
        strength = _safe_score((candidate.get('editorial_scores') or {}).get('editorial_strength'),
                               _safe_score(candidate.get('ranking_confidence')))
        editorial.append({'moment_id': cid, 'possible_start': candidate['start'],
                          'possible_end': candidate['end'], 'start': candidate['start'], 'end': candidate['end'],
                          'text': candidate.get('transcript_literal', ''), 'confidence': strength,
                          'editorial': {'score': strength}, 'reason': 'Second-curation shortlist suggestion; human review required',
                          'categories': [candidate.get('content_type') or 'editorial_content'],
                          'context_required': bool(candidate.get('context_requirement') not in (None, 'none')),
                          'commercial_classification': candidate.get('commercial_classification'),
                          'candidate_state': 'CURATOR_REVIEW_REQUIRED'})
        review.append({'moment_id': cid, 'title_idea': title, 'editorial_score': strength,
                       'why': 'First-pass suggestion only; review context, transcription and commercial safety.'})
    captions = []
    for segment in segment_rows:
        raw_words = words_by_seg.get(segment.get('segment_id'), [])
        # Never turn uncertain ASR words into karaoke timings without a review pass.
        valid = bool(raw_words) and all(w.get('alignment_verified') is True and w.get('audio_verified') is True and not w.get('needs_review')
                                        and not w.get('timestamp_suspect') and not w.get('speech_overlap')
                                        and isinstance(w.get('start'), (int, float)) and isinstance(w.get('end'), (int, float))
                                        and segment['start'] <= w['start'] < w['end'] <= segment['end'] for w in raw_words)
        captions.append({'start': segment['start'], 'end': segment['end'], 'text': segment.get('text') or '',
                         'display_text': segment.get('text') or '', 'words': raw_words if valid else [],
                         'subtitle_review_required': True, 'human_audio_verified': False,
                         'word_highlight_enabled': bool(valid),
                         'status': 'DRAFT_REQUIRES_LISTENING'})
    with tempfile.TemporaryDirectory(prefix='.curator_bridge_', dir=output_dir) as temp:
        root = Path(temp)
        legacy_analysis = {'metadata': metadata, 'transcript_segments': segment_rows,
                           'speakers': speakers, 'analysis_status': 'curator_bridge_requires_review',
                           'curator_bridge': {'source_package_sha256': hashlib.sha256(package_path.read_bytes()).hexdigest(),
                                             'publication_ready': False, 'human_review_required': True,
                                             'camera_evidence': 'not_transferred_use_source_preserve'}}
        _write_json(root/'analysis.json', legacy_analysis)
        _write_json(root/'editorial_moments.json', editorial)
        _write_json(root/'ollama_editorial_review.json', {'top_moments': review})
        _write_json(root/'llm_insights.json', {'segments': segment_rows})
        _write_json(root/'words.json', word_rows)
        _write_json(root/'caption_segments.json', captions)
        _write_json(root/'speakers.json', speakers)
        _write_json(root/'speaker_person_mapping.json', [])
        _write_json(root/'timeline.json', [])
        _write_json(root/'scenes.json', [])
        _write_json(root/'people_observations.json', [])
        _write_json(root/'video_analysis.json', {'frame_samples': []})
        _write_json(root/'questions_answers.json', [])
        _write_json(root/'BRIDGE_PROVENANCE.json', {
            'bridge_schema': '1.0', 'analyzer_build': manifest.get('analyzer_build'),
            'source_sha256': metadata.get('sha256'), 'source_video_id': source_id,
            'input_zip_sha256': hashlib.sha256(package_path.read_bytes()).hexdigest(),
            'shortlist_count': len(selection), 'subtitle_segments_requiring_review': sum(c['subtitle_review_required'] for c in captions),
            'final_render_validated': False, 'publication_ready': False, 'human_approval_required': True,
            'important': 'This bridge does not transfer trustworthy original visual observations; Curator must preserve source without them.'})
        (root/'LEIA_ANTES_DO_CURATOR.txt').write_text(
            'Ponte de compatibilidade para L.D.PORTO VIDEO CURATOR V2.\n'
            'Aponte paths.analysis_root para a pasta PAI deste diretório.\n'
            'Entre com a URL/id do vídeo no Curator, faça CURAR, TESTAR 1 CORTE, revise visual/legendas/comercial e APROVAR TESTE.\n'
            'Sem evidência visual bruta transferida: enquadramento deve preservar a fonte.\n'
            'Nunca significa READY TO POST; o vídeo original deve ser localizado pelo Curator.\n',
            encoding='utf-8')
        root.rename(target)
    return {'path': str(target), 'analysis_root_for_curator': str(output_dir),
            'video_id': source_id, 'shortlist_count': len(selection),
            'subtitle_segments_requiring_review': sum(c['subtitle_review_required'] for c in captions),
            'publication_ready': False, 'final_render_validated': False}
