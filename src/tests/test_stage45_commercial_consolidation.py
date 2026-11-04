"""Offline counterfactuals; historical JSON is ASR, screenshots are never OCR."""
import json
from pathlib import Path

import pytest

from ldporto.commercial_gate import apply_commercial_refinement, targeted_ocr
from ldporto.ocr import normalize_commercial_observation
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_export import _final_commercial_classification
from test_s8_commercial_graphics_stories import _moment


def refine(texts, visual=None, graphics=None, suspect=False, disabled=False):
    segments = [dict(segment_id=f'S{i}', start=i*10, end=(i+1)*10, text=t)
                for i, t in enumerate(texts)]
    candidate = {**_moment('M', 0, len(texts)*10), 'commercial_visual_suspected': suspect}
    return apply_commercial_refinement({'main_moments': [candidate]}, segments, visual or [], {},
        graphics=graphics, commercial_visual=targeted_ocr('never-opened.mp4', [], {'enabled': False}) if disabled else None)


def test_historical_openbox_json_split_turns_keeps_literal_asr_and_blocks_shortlist():
    fixture = json.loads((Path(__file__).parent / 'fixtures/v44/commercial_false_negatives.json').read_text(encoding='utf-8'))
    real = fixture['candidates'][0]
    # Counterfactual boundaries, not reconstructed timings/speakers of the real run.
    words = real['text'].split()
    texts = [' '.join(words[i:i+25]) for i in range(0, len(words), 25)]
    result = refine(texts)
    row = result['main_moments'][0]
    assert row['commercial_classification']['eligibility'] == 'excluded'
    assert result['editorial_shortlist'] == []
    assert all(o['source'] == 'asr' for o in row['commercial_observations'])
    assert ' '.join(o['text'] for o in row['commercial_observations']) == ' '.join(words)
    assert fixture['source_sha256'] and real['moment_id'] != 'MOMENT_00011_0003'


@pytest.mark.parametrize('method', [None, 'manual_contact_sheet', 'tesseract_candidate_frame_s8'])
def test_off_and_qr_never_auto_eligible_with_neutral_asr(method):
    visual = [dict(start=5, end=99, source='ocr', text='Openbox ６０% OFF QR CODE', method=method,
                   confidence=.9, persistence_sample_count=3)]
    result = refine(['Uma conversa sobre a infancia.'], visual)
    row = result['main_moments'][0]
    assert row['commercial_classification']['eligibility'] == 'review'
    assert not row['default_shortlist_eligible'] and not result['editorial_shortlist']
    observation = row['commercial_observations'][-1]
    assert observation['start'] == observation['end'] == 5
    assert observation['continuity_established'] is False
    if method != 'tesseract_candidate_frame_s8':
        assert observation['text'] is None and observation['normalized_text'] is None
        assert row['commercial_classification']['review_reason'] == 'commercial_visual_unmeasured'
        assert not any(s.get('modality') == 'visual_text' for s in row['commercial_classification']['evidence_spans'])
    else:
        assert observation['text'] == visual[0]['text']
        assert '60% off' in observation['normalized_text']


def test_disabled_ocr_and_explicit_suspicion_has_required_reason():
    result = refine(['Uma historia.'], suspect=True, disabled=True)
    row = result['main_moments'][0]
    assert row['commercial_classification']['review_reason'] == 'commercial_visual_unmeasured'
    assert not result['editorial_shortlist']
    assert all(o['source'] == 'asr' for o in row['commercial_observations'])


def test_station_event_call_split_asr_and_partial_overlap_are_blocked():
    result = refine(['A Copa do Mundo e na Jovem Pan.', 'Acompanhe com a gente.'])
    row = result['main_moments'][0]
    assert row['commercial_classification']['eligibility'] == 'excluded'
    assert row['commercial_classification']['commercial_kind'] == 'institutional_promotion'
    assert result['commercial_blocks'][0]['segment_ids'] == ['S0', 'S1']
    assert not result['editorial_shortlist']
    package = build_second_curation_package({**result, 'transcript_segments': [
        dict(segment_id=f'S{i}', start=i*10, end=(i+1)*10, text=t)
        for i, t in enumerate(['A Copa do Mundo e na Jovem Pan.', 'Acompanhe com a gente.'])]})
    candidate = package['candidates'][0]
    assert candidate['commercial_observations'] == row['commercial_observations']
    assert _final_commercial_classification(candidate)['eligibility'] == 'excluded'
    assert not candidate['publication_ready']


@pytest.mark.parametrize('text', [
    'Na reportagem discutimos a Openbox e o preco dos moveis.',
    'A historia da Jovem Pan durante a Copa do Mundo.',
    'A vinheta dizia: acompanhe a Copa na Jovem Pan.',
    'Nao assista a Copa na Jovem Pan.',
])
def test_editorial_brand_or_quoted_station_call_has_no_commercial_exclusion(text):
    row = refine([text])['main_moments'][0]
    assert row['commercial_classification']['eligibility'] == 'eligible'


def test_export_catches_station_promo_without_prior_classification():
    result = _final_commercial_classification(dict(transcript_literal='Assista a Copa na Jovem Pan.'))
    assert result['eligibility'] == 'excluded'
    assert result['commercial_score'] is None


@pytest.mark.parametrize('kind,expected', [('lower_third', 'eligible'), ('qr_code', 'review'), ('vinheta', 'review')])
def test_graphic_observations_never_supply_inferred_text(kind, expected):
    graphics = {'intervals': [dict(start=0, end=10, moment_id='M', regions=[
        dict(kind=kind, confidence=.75, evidence={'sample_count': 8}, ocr_text=['INFERRED 60% OFF'])])]}
    row = refine(['Uma historia.'], graphics=graphics)['main_moments'][0]
    assert row['commercial_classification']['eligibility'] == expected
    gc = row['commercial_observations'][-1]
    assert gc['source'] == 'gc' and gc['text'] is None
    assert gc['commercial_confirmed'] is None


def test_unmeasured_export_text_is_review_without_visual_evidence_spans():
    candidate = dict(transcript_literal='Uma historia.', commercial_visual_evidence=[
        dict(start=2, text='Compre agora R$ 79', source='ocr', method='manual_contact_sheet')])
    result = _final_commercial_classification(candidate)
    assert result['eligibility'] == 'review'
    assert result['review_reason'] == 'commercial_visual_unmeasured'
    assert not any(s.get('modality') == 'visual_text' for s in result['evidence_spans'])


def test_manual_flag_overrides_ocr_method_and_invalid_time_is_rejected():
    assert normalize_commercial_observation(dict(start=float('nan'), text='OFF')) is None
    result = normalize_commercial_observation(dict(start=1, text='60% OFF',
        method='tesseract_keyframe', manually_inferred=True))
    assert result['text'] is None and result['measurement_state'] == 'not_measured'


def test_export_manifest_and_audit_trace_observations_without_publication(tmp_path):
    import zipfile
    from test_v43_handoff import analysis_fixture
    from ldporto.second_curation_export import build_core_package, validate_core_package
    analysis = analysis_fixture()
    analysis['main_moments'][0]['commercial_visual_suspected'] = True
    result = apply_commercial_refinement(analysis, analysis['transcript_segments'], [], {},
        commercial_visual=targeted_ocr('never-opened.mp4', [], {'enabled': False}))
    package = build_core_package(result, output_dir=tmp_path)
    assert validate_core_package(package['path'])['checksums_valid']
    with zipfile.ZipFile(package['path']) as archive:
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        audit = json.loads(archive.read(manifest['commercial_audit_ref']))
        candidate = json.loads(archive.read('candidates/M1.json'))
        assert audit[0]['observations'] == candidate['commercial_observations']
        assert audit[0]['commercial']['review_reason'] == 'commercial_visual_unmeasured'
        assert audit[0]['observations'][0]['segment_id'] == 'S1'
        assert candidate['publication_ready'] is False
        assert not candidate['default_shortlist_eligible']
        assert manifest['preview_approved'] is False and manifest['publication_ready'] is False
