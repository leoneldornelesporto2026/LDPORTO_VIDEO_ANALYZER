"""Offline fixtures: geometry/temporal evidence, no real OCR accuracy claims."""
import sys
import types
from pathlib import Path
from copy import deepcopy

import cv2
import numpy as np
import pytest

from ldporto.broadcast_graphics import detect_graphics
from ldporto.commercial_gate import targeted_ocr
from ldporto.editorial import classify_content
from ldporto.ocr import OcrEngine, validate_observations


def observation(t, **extra):
    return {'text': 'MARCA R$ 79 desconto compre agora', 'source': 'ocr',
            'start': t, 'end': t, 'observed_at': t, 'moment_id': 'M',
            'bbox': {'x': .1, 'y': .7, 'width': .6, 'height': .1},
            'confidence': .9, **extra}


@pytest.mark.parametrize('desk', [False, True])
def test_black_background_and_dark_studio_desk_are_not_gc(desk):
    image = np.zeros((180, 320, 3), dtype=np.uint8)
    if desk:
        cv2.rectangle(image, (0, 125), (319, 173), (90, 90, 90), 2)
    assert detect_graphics([image.copy() for _ in range(8)])['regions'] == []


def test_realistic_lower_third_fixture_requires_text_components():
    frames = []
    for i in range(8):
        image = np.zeros((180, 320, 3), dtype=np.uint8)
        cv2.circle(image, (30+i*15, 45), 15, (180, 180, 180), -1)
        cv2.rectangle(image, (0, 125), (319, 173), (70, 70, 70), -1)
        cv2.putText(image, 'CONVIDADO NO ESTUDIO', (10, 155),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 1)
        frames.append(image)
    regions = detect_graphics(frames)['regions']
    assert len(regions) == 1 and regions[0]['kind'] == 'lower_third'
    assert regions[0]['evidence']['glyph_component_count'] >= 5
    assert regions[0]['uncertain'] and regions[0]['commercial_confirmed'] is None
    assert not detect_graphics(frames[:2])['regions']


def test_price_fixture_has_sampled_persistence_without_claiming_continuity():
    rows = validate_observations([observation(t) for t in (1., 2., 3.)])
    assert all(not row['uncertain'] and row['temporal_validated'] for row in rows)
    assert all(row['persistence_sample_count'] == 3 for row in rows)
    assert all(row['commercial_confirmed'] is None and not row['continuity_established'] for row in rows)
    assert classify_content('Conversa editorial.', visual_evidence=rows)['eligibility'] == 'review'


@pytest.mark.parametrize('case', ['single', 'duplicate', 'moving', 'invalid', 'gap', 'low_confidence'])
def test_unvalidated_ocr_cannot_prove_commercial(case):
    rows = [observation(t) for t in (1., 2., 3.)]
    if case == 'single': rows = rows[:1]
    if case == 'duplicate': rows = [observation(1.) for _ in range(3)]
    if case == 'moving':
        for i, row in enumerate(rows): row['bbox']['x'] += i*.1
    if case == 'invalid':
        for row in rows: row['bbox']['width'] = 2.
    if case == 'gap': rows = [observation(t) for t in (1., 50., 100.)]
    if case == 'low_confidence':
        for row in rows: row['confidence'] = .45
    rows = validate_observations(rows)
    assert all(row['uncertain'] for row in rows)
    assert classify_content('Entrevista.', visual_evidence=rows)['eligibility'] == 'review'


def test_disabled_ocr_never_imports_or_opens_video():
    ctx = types.SimpleNamespace(config={'ocr': {'enabled': False}})
    assert OcrEngine().run(ctx, {})['data']['measurement_state'] == 'not_measured'
    result = targeted_ocr('nonexistent.mp4', [], {'enabled': False})
    assert result['measurement_state'] == 'not_measured' and result['commercial_present'] is None


def test_missing_tesseract_is_not_measured(monkeypatch):
    def missing(): raise OSError('missing executable')
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(get_tesseract_version=missing))
    result = targeted_ocr('nonexistent.mp4', [], {'enabled': True})
    assert result['status'] == 'unavailable' and result['measurement_state'] == 'not_measured'
    ctx = types.SimpleNamespace(config={'ocr': {'enabled': True, 'tesseract_cmd': ''}})
    assert OcrEngine().run(ctx, {})['data']['measurement_state'] == 'not_measured'


@pytest.mark.parametrize('failure', [False, True])
def test_targeted_export_with_mocked_price_and_ocr_failures(monkeypatch, failure):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    cv2.putText(image, 'R$79', (20, 80), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 1)
    class Capture:
        def __init__(self, *_): pass
        def isOpened(self): return True
        def set(self, *_): pass
        def read(self): return True, image.copy()
        def release(self): pass
    def recognize(*args, **kwargs):
        if failure: raise RuntimeError('fixture timeout')
        return deepcopy({'text': ['R$79'], 'conf': ['90'], 'block_num': [1],
                         'par_num': [1], 'line_num': [1], 'left': [20], 'top': [65],
                         'width': [60], 'height': [18]})
    monkeypatch.setattr(cv2, 'VideoCapture', Capture)
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(
        Output=types.SimpleNamespace(DICT='dict'), TesseractError=RuntimeError,
        get_tesseract_version=lambda: 'fixture', image_to_data=recognize))
    result = targeted_ocr('fixture.mp4', [{'moment_id': 'M', 'start': 0, 'end': 4}], {'enabled': True})
    assert result['commercial_present'] is None
    if failure:
        assert result['measurement_state'] == 'not_measured' and result['status'] == 'partial'
        assert result['failed_frames_or_ocr'] == 3 and not result['texts']
    else:
        assert result['measured_frames'] == 3
        assert all(row['bbox'] and row['confidence'] == .9 and not row['uncertain']
                   and row['observed_at'] == row['start'] == row['end'] for row in result['texts'])
    # The keyframe engine uses the same evidence validator and handles failure.
    monkeypatch.setattr(cv2, 'imread', lambda *_: image.copy())
    ctx = types.SimpleNamespace(output=Path('.'), config={'ocr': {
        'enabled': True, 'tesseract_cmd': '', 'languages': 'por+eng', 'max_frames': 3}})
    engine = OcrEngine().run(ctx, {'thumbnails': [{'path': 'fixture.jpg', 'time': t} for t in (1., 2., 3.)]})
    assert engine['data']['measurement_state'] == ('not_measured' if failure else 'measured')
    if not failure:
        assert len(engine['data']['texts']) == 3
        assert all(not row['uncertain'] for row in engine['data']['texts'])
