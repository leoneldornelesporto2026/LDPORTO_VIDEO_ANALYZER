"""Synthetic benchmark only: actual sampling/fusion with mocked OCR; no TV accuracy."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import cv2
import numpy as np
import pytest

from ldporto.commercial_gate import (targeted_ocr, apply_commercial_refinement,
                                    commercial_benchmark_metrics, candidate_visual_coverage, commercial_risk)
from ldporto.integrity_contracts import capability_contract, audit_editorial_contract
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_s8_commercial_graphics_stories import _moment

FIXTURE = Path(__file__).parent / 'fixtures/stage55_commercial_synthetic.json'
CASES = json.loads(FIXTURE.read_text(encoding='utf-8'))['cases']


def test_fixture_is_immutable():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == '81298196b4006f83e1cf3bc9c25dd82b243fbcf877e294f0c0122c4dfba9b164'


def synthetic_frame(text):
    """Code-native frame recipe, including a decorative representative QR grid."""
    image = np.full((400, 800, 3), 255, dtype=np.uint8)
    cv2.putText(image, text, (20, 290), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 2)
    if 'QR' in text:
        for y in range(11):
            for x in range(11):
                if (x * 3 + y * 7) % 5 < 3:
                    cv2.rectangle(image, (660 + x*8, 50 + y*8),
                                  (667 + x*8, 57 + y*8), (0, 0, 0), -1)
    return image


def run_case(case, tmp_path, monkeypatch, *, samples=None):
    from ocr_test_support import mock_ocr_runtime
    mock_ocr_runtime(monkeypatch)
    media = tmp_path / 'synthetic55.media'
    media.write_bytes(b'stage55 synthetic source; no real media')
    calls = []
    class Capture:
        def __init__(self, *_): pass
        def isOpened(self): return True
        def set(self, *_): pass
        def read(self): return True, synthetic_frame(case['ocr'] or '')
        def release(self): pass
    monkeypatch.setattr(cv2, 'VideoCapture', Capture)
    def recognize(*args, **kwargs):
        calls.append(kwargs['lang'])
        if len(calls) == case.get('fail_sample'):
            raise RuntimeError('synthetic OCR timeout')
        text = case['ocr'] if samples is None or len(calls) <= samples else ''
        return {'text': [text], 'conf': ['95'], 'block_num': [1], 'par_num': [1],
                'line_num': [1], 'left': [20], 'top': [270], 'width': [620], 'height': [25]}
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(
        Output=types.SimpleNamespace(DICT='dict'), TesseractError=RuntimeError,
        get_tesseract_version=lambda: 'synthetic55', image_to_data=recognize))
    moment = _moment(case['id'], 0, 10)
    receipt = targeted_ocr(media, [moment], {'enabled': case['ocr'] is not None, 'languages': 'eng'})
    segments = [dict(segment_id='S1', start=0, end=10, text=case['speech'])]
    graphics = {'intervals': [dict(start=0, end=10, moment_id=case['id'],
        regions=[dict(kind=case['gc'], confidence=.75, evidence={'sample_count': 8})])]} if case['gc'] else {}
    result = apply_commercial_refinement({'main_moments': [moment]}, segments, receipt['texts'], {},
                                        commercial_visual=receipt, graphics=graphics)
    return {**result, 'transcript_segments': segments, 'commercial_visual_s8': receipt}, calls


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_annotated_scenarios_actual_sampling_and_fusion(case, tmp_path, monkeypatch):
    result, calls = run_case(case, tmp_path, monkeypatch)
    row = result['main_moments'][0]
    assert row['commercial_risk']['state'] == case['expected']
    assert row['commercial_risk']['probability'] is None
    assert row['commercial_coverage']['continuous_visual_coverage'] is None
    assert calls == ([] if case['ocr'] is None else ['eng'] * 3)
    if case['expected'] != 'measured_no_ad_evidence':
        assert result['editorial_shortlist'] == []
    else:
        assert row['commercial_classification']['eligibility'] == 'eligible'
    package = build_second_curation_package(result)
    candidate = package['candidates'][0]
    assert candidate['commercial_risk'] == row['commercial_risk']
    assert candidate['commercial_coverage'] == row['commercial_coverage']
    assert candidate['publication_ready'] is False
    if case['ocr']:
        for o in row['commercial_observations']:
            if o['source'] == 'ocr':
                assert o['original_text'] == case['ocr']
                assert len(o['source_frame_hash']) == 64
                assert o['source_frame_hash'] == o['decoded_frame_sha256']
                assert o['bbox'] and o['confidence'] == .95
                assert o['continuity_established'] is False


def test_one_frame_cannot_be_probable_or_confirmed(tmp_path, monkeypatch):
    case = next(c for c in CASES if c['id'] == 'probable')
    result, _ = run_case(case, tmp_path, monkeypatch, samples=1)
    assert result['main_moments'][0]['commercial_risk']['state'] == 'requires_review'
    assert not result['editorial_shortlist']


def test_partial_remains_useful_not_fatal_and_outside_window_unmeasured(tmp_path, monkeypatch):
    case = next(c for c in CASES if c['id'] == 'partial')
    result, _ = run_case(case, tmp_path, monkeypatch)
    result['stage_status'] = {'17c_commercial_visual': {'status': 'partial'}}
    assert capability_contract(result)['stages']['17c_commercial_visual']['state'] == 'measured_partial'
    assert not audit_editorial_contract(result)['errors']
    coverage = result['main_moments'][0]['commercial_coverage']
    assert coverage['state'] == 'partially_failed'
    assert coverage['sampling_coverage'] == 2/3
    outside = apply_commercial_refinement({'main_moments': [_moment('OUTSIDE', 20, 30)]},
        [dict(segment_id='S2', start=20, end=30, text='Uma historia.')],
        result['commercial_visual_s8']['texts'], {}, commercial_visual=result['commercial_visual_s8'])
    assert outside['main_moments'][0]['commercial_risk']['state'] == 'not_measured'
    assert not outside['editorial_shortlist']


def test_empty_successful_ocr_is_sampled_not_absent(tmp_path, monkeypatch):
    case = {**CASES[2], 'ocr': ''}
    result, _ = run_case(case, tmp_path, monkeypatch)
    row = result['main_moments'][0]
    assert row['commercial_risk']['state'] == 'measured_no_ad_evidence'
    assert row['commercial_coverage']['measured_frames'] == 3
    assert result['commercial_visual_s8']['texts'] == []


def test_benchmark_counts_require_annotations_and_preserve_unknown():
    assert commercial_benchmark_metrics([])['commercial_false_negative_candidates'] is None
    annotations = {'annotation_kind': 'synthetic_fixture', 'labels': [
        {'candidate_id': c['id'], 'expected_ad': c['expected_ad']} for c in CASES]}
    rows = [{'moment_id': c['id'], 'commercial_risk': {'state': c['expected']}} for c in CASES]
    assert commercial_benchmark_metrics(rows, annotations)['commercial_false_negative_candidates'] == []
    rows[0]['commercial_risk']['state'] = 'measured_no_ad_evidence'
    assert commercial_benchmark_metrics(rows, annotations)['commercial_false_negative_candidates'] == ['offer']
    assert commercial_benchmark_metrics([], annotations)['commercial_false_negative_candidates'] is None
    assert commercial_benchmark_metrics(rows, annotations)['precision'] is None


def test_all_frames_failed_is_not_measured_not_partial_measurement():
    coverage = candidate_visual_coverage(_moment('M', 0, 10), {'candidate_coverage': {
        'M': {'requested_frames': 3, 'measured_frames': 0, 'failed_frames_or_ocr': 3}}}, [])
    assert coverage['state'] == 'not_measured'
    assert coverage['sampling_coverage'] == 0
    assert coverage['continuous_visual_coverage'] is None


def test_legacy_exclusion_never_fabricates_confirmation():
    coverage = candidate_visual_coverage(_moment('M', 0, 10), {}, [])
    risk = commercial_risk({'eligibility': 'excluded'}, [], coverage)
    assert risk['state'] == 'requires_review'
    assert 'upstream_exclusion_preserved_confirmation_unavailable' in risk['reason_codes']


def test_manifest_integrity_and_no_publication(tmp_path, monkeypatch):
    from ldporto import second_curation_export
    from test_v43_handoff import analysis_fixture
    case = CASES[0]
    analysis = analysis_fixture()
    # Keep the fixture's canonical IDs and transcript; apply the real refinement.
    analysis['transcript_segments'][1]['text'] = case['speech']
    refined = apply_commercial_refinement(analysis, analysis['transcript_segments'], [], {})
    class StagingVerified(Exception): pass
    def inspect_staging(path):
        # Exercise the actual directory manifest/validator; stop before compression.
        root = Path(path)
        assert root.is_dir()
        validation = validate_core_package(root)
        assert validation['checksums_valid'] and validation['status'] == 'valid'
        manifest = json.loads((root / 'SECOND_CURATION_MANIFEST.json').read_text(encoding='utf-8'))
        catalog = json.loads((root / 'editorial/candidate_catalog.json').read_text(encoding='utf-8'))['candidates']
        assert not manifest['workflow']['publication_ready'] and not manifest['workflow']['preview_approved']
        assert catalog[0]['commercial_risk']['state'] == 'confirmed_ad'
        assert not catalog[0]['default_shortlist_eligible']
        assert not catalog[0]['publication_ready']
        (root / 'candidates/M1.json').write_text('{}', encoding='utf-8')
        assert not validate_core_package(root)['checksums_valid']
        raise StagingVerified()
    monkeypatch.setattr(second_curation_export, 'validate_core_package', inspect_staging)
    with pytest.raises(StagingVerified):
        build_core_package(refined, output_dir=tmp_path / 'package')
    assert not list(tmp_path.rglob('*.zip'))


@pytest.mark.skipif(os.environ.get('LDPORTO_STAGE55_REAL_OCR') != '1',
                    reason='Opt-in synthetic Tesseract only: LDPORTO_STAGE55_REAL_OCR=1')
def test_opt_in_tesseract_on_authored_synthetic_offer(tmp_path):
    executable = shutil.which('tesseract')
    if not executable:
        pytest.skip('Tesseract executable unavailable; no installation requested')
    image = tmp_path / 'synthetic_offer.png'
    cv2.imwrite(str(image), synthetic_frame('Openbox 60% OFF QR CODE'))
    completed = subprocess.run([executable, str(image), 'stdout', '-l', 'eng', '--psm', '11'],
                               capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    assert '60%' in completed.stdout and 'OFF' in completed.stdout.upper()
    # This proves execution on this synthetic image only, never TV accuracy.
