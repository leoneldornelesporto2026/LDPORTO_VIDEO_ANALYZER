"""Controlled signal/metadata regressions, without downloaded models or GPU."""
from copy import deepcopy
from types import SimpleNamespace
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from director_fixtures import fixture as camera_fixture, turn
from ldporto import body_model_paths
from ldporto.active_speaker import build_active_speaker
from ldporto.audiovisual_diagnostics import annotate_window_observations
from ldporto.camera_director import build_camera_director
from ldporto.config import DEFAULTS, load_config
from ldporto.core import Context, external_fingerprints
from ldporto.core import write_json
from ldporto.compact_artifacts import compact_analysis_document
from ldporto.vision import ActiveSpeakerEngine, load_local_yolo
from ldporto.vision_checkpoint import VisionCheckpointStore
from test_s5_speaker_person_active import fixture as speaker_fixture
from test_stage25_body_backends import no_network


def test_measured_candidates_below_threshold_are_not_missing_measurement():
    diar, vision, raw = speaker_fixture()
    for row in raw:
        row['candidates'] = [dict(row['candidates'][0], correlation=.54006,
                                  correlation_lower_bound_proxy=.0385)]
    original = deepcopy(raw)
    data = build_active_speaker(diar, vision, raw, DEFAULTS['active_speaker'])['data']
    assert raw == original
    summary = data['mapping_summary'][0]
    assert summary['raw_audio_windows'] == summary['candidate_evidence_windows'] == 2
    assert summary['independent_affinity_windows'] == 2
    assert summary['qualified_positive_windows'] == summary['evidence_windows'] == 0
    assert summary['measurement_status'] == 'measured_no_qualified_consensus'
    assert summary['person_id'] is None
    assert data['speaker_person_diagnostics'][0]['window_diagnostics']['CORRELATION_BELOW_CONSENSUS_MINIMUM'] == 2
    assert 'MAPPED_PERSON_NOT_IN_LOCAL_CANDIDATES' not in data['speaker_person_diagnostics'][0]['window_diagnostics']
    assert data['metrics']['candidate_signal_window_count'] == 2
    assert data['metrics']['qualified_local_signal_window_count'] == 0
    assert all(row['active_person'] is None for row in data['intervals'])
    for window in data['active_speaker_evidence']:
        candidate = window['signal_diagnostic']['candidates'][0]
        assert candidate['required_correlation'] == .55
        assert 'CORRELATION_BELOW_MINIMUM' in candidate['rejection_reasons']
        assert candidate['audio_lag_seconds'] == .04


def test_visual_diagnostic_reports_actual_pixel_samples_without_creating_an_occlusion():
    rows = [{'start': 0., 'end': 1.}]
    vision = {'frames': [{'time': .2}, {'time': .4}], 'observations': [
        {'time': .2, 'face_visible': True, 'lip_opening': .1,
         'face_quality': {'face_width_px': 16, 'face_height_px': 20}},
        {'time': .4, 'face_visible': True, 'lip_opening': None}]}
    annotate_window_observations(rows, vision, {'width': 320, 'height': 240, 'fps': 15}, 28)
    data = rows[0]['visual_measurement']
    assert data['sampled_frame_times'] == [.2, .4]
    assert data['mouth_frame_times'] == [.2]
    assert data['face_observation_count'] == 2 and data['face_pixel_quality_sample_count'] == 1
    assert data['face_pixel_status_counts'] == {'insufficient_face_pixels': 1}
    assert data['physical_occlusion_verified'] is None
    assert not data['continuous_visibility_verified']


def controlled_signal_fixture(tmp_path):
    """Synthetic envelope/lip annotations, not human speech or detector outputs."""
    rate, duration = 2000, 13
    rng = np.random.default_rng(324)
    amplitudes = rng.uniform(.03, .3, size=duration*8)
    samples = np.arange(duration*rate)
    envelope = amplitudes[np.minimum(samples//(rate//8), len(amplitudes)-1)]
    audio = (envelope*np.sin(2*np.pi*200*samples/rate)).astype(np.float32)
    path = tmp_path/'controlled_signal.wav'
    sf.write(path, audio, rate, subtype='FLOAT')
    observations, frames = [], []
    for index, amplitude in enumerate(amplitudes):
        stamp = index/8+.0625
        speaking = 'P1' if stamp < 6 else 'P2'
        frames.append(dict(time=stamp, visible_people=['P1', 'P2'], scene_id='SH1'))
        for person in ('P1', 'P2'):
            observations.append(dict(time=stamp, person_id=person, track_id=person, scene_id='SH1',
                face_visible=True, lip_opening=float(amplitude) if person == speaking else .02,
                mouth_activity=.1 if person == speaking else 0.,
                face_quality={'face_width_px': 120, 'face_height_px': 180}))
    vision = {'people': [{'person_id': 'P1'}, {'person_id': 'P2'}],
              'observations': observations, 'frames': frames,
              'scene_intervals': [{'start': 0., 'end': duration, 'scene_id': 'SH1'}]}
    diar = {'speakers': [{'speaker_id': 'S1'}, {'speaker_id': 'S2'}],
            'turns': [dict(start=0., end=6., speaker='S1'), dict(start=6., end=12., speaker='S2'),
                      dict(start=12., end=13., speaker='S1'), dict(start=12., end=13., speaker='S2')],
            'overlaps': [dict(start=12., end=13.)]}
    return path, vision, diar


def test_two_voice_controlled_signal_executes_measurement_and_abstains_on_overlap(tmp_path):
    source, vision, diar = controlled_signal_fixture(tmp_path)
    cfg = load_config()
    ctx = Context(tmp_path/'not_real_video.mp4', tmp_path/'output', cfg, 'controlled', logging.getLogger('controlled'))
    raw = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision,
                                   {'width': 1920, 'height': 1080, 'fps': 30, 'duration': 13})['data']['mappings']
    data = build_active_speaker(diar, vision, raw, cfg['active_speaker'])['data']
    assert {r['speaker_id']: r['person_id'] for r in data['mapping_summary']} == {'S1': 'P1', 'S2': 'P2'}
    assert {r['active_person'] for r in data['intervals'] if r['active_person']} == {'P1', 'P2'}
    assert all(r['active_person'] is None for r in data['intervals'] if r['overlap'])
    measured = [r for r in raw if r.get('audio_measurement', {}).get('status') == 'audio_window_read']
    assert len(measured) == 4
    assert all(r['audio_measurement']['sample_count'] > 0 and r['visual_measurement']['mouth_frame_times'] for r in measured)
    assert data['metrics']['signal_window_status_counts']['audio_overlap'] == 2


def test_canonical_body_path_uses_legacy_only_when_configured_file_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(body_model_paths, 'ROOT', tmp_path)
    canonical = tmp_path/'models/body/yolo11n.pt'
    legacy = tmp_path/'yolo11n.pt'
    legacy.write_bytes(b'legacy synthetic placeholder')
    selected, report = body_model_paths.select_body_model_path('models/body/yolo11n.pt')
    assert selected == legacy and report['legacy_compatibility_used']
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b'configured synthetic placeholder')
    selected, report = body_model_paths.select_body_model_path('models/body/yolo11n.pt')
    assert selected == canonical and not report['legacy_compatibility_used']
    cfg = load_config()['vision']
    cfg['yolo_model'] = str(canonical)
    canonical.write_bytes(b'')
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=lambda *a: pytest.fail('invalid configured file')))
    model, report = load_local_yolo(cfg)
    assert model is None and report['model_validation_reason'] == 'empty_file'
    assert not report['legacy_compatibility_used']


def test_legacy_body_model_mutation_invalidates_fingerprints_and_chunk_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(body_model_paths, 'ROOT', tmp_path)
    legacy = tmp_path/'yolo11n.pt'
    legacy.write_bytes(b'first synthetic bytes')
    cfg = load_config()
    cfg['vision']['yolo_model'] = str(tmp_path/'models/body/yolo11n.pt')
    cfg['vision']['body_backend'] = 'yolo'
    ctx = Context(tmp_path/'not_video.mp4', tmp_path/'output', cfg, 'controlled', logging.getLogger('controlled'))
    first_hashes = external_fingerprints(cfg, '07_people_tracking')
    first_chunk = VisionCheckpointStore(ctx, cfg['vision']).model_hash
    legacy.write_bytes(b'second synthetic bytes')
    assert external_fingerprints(cfg, '07_people_tracking') != first_hashes
    assert VisionCheckpointStore(ctx, cfg['vision']).model_hash != first_chunk


def test_body_legacy_alias_does_not_bypass_a_link_in_the_configured_path(tmp_path, monkeypatch):
    (tmp_path/'yolo11n.pt').write_bytes(b'synthetic placeholder')
    configured = tmp_path/'models/body/yolo11n.pt'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == configured.parent or original(path))
    selected, report = body_model_paths.select_body_model_path('models/body/yolo11n.pt', root=tmp_path)
    assert selected == configured and not report['legacy_compatibility_used']


def test_passive_body_diagnostic_never_loads_or_promotes_model(tmp_path, monkeypatch):
    path = tmp_path/'synthetic.pt'
    path.write_bytes(b'not real weights')
    cfg = load_config()['vision']
    cfg['yolo_model'] = str(path)
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=lambda *a: pytest.fail('passive diagnostic loaded weights')))
    data = body_model_paths.body_model_diagnostics(cfg)
    assert data['diagnostic_scope'] == 'passive_local_metadata'
    assert data['model_loaded'] is data['inference_executed'] is False
    assert data['readiness'] == 'NOT_READY' and data['local_smoke_validated'] is None
    json.dumps(data, allow_nan=False)


def test_local_yolo_privacy_disables_events_without_persisting_user_settings(tmp_path, monkeypatch):
    class PersistentSettings(dict):
        def __setitem__(self, *args):
            pytest.fail('User settings persistence invoked')
        def update(self, *args, **kwargs):
            pytest.fail('User settings persistence invoked')
    settings = PersistentSettings(sync=True, hub=True)
    events = SimpleNamespace(enabled=True)
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(SETTINGS=settings))
    monkeypatch.setitem(sys.modules, 'ultralytics.utils', SimpleNamespace(SETTINGS=settings, ONLINE=True))
    monkeypatch.setitem(sys.modules, 'ultralytics.utils.events', SimpleNamespace(events=events))
    monkeypatch.setenv('YOLO_CONFIG_DIR', str(tmp_path/'user_settings'))
    report = body_model_paths.configure_local_yolo_privacy()
    assert not settings['sync'] and not settings['hub'] and not events.enabled
    assert not sys.modules['ultralytics.utils'].ONLINE
    assert report['user_settings_modified'] is False
    assert not (tmp_path/'user_settings').exists()


def test_camera_replay_hydrates_compact_persistent_visual_sidecars_and_checks_hashes(tmp_path):
    from scripts.dev.audit_camera_s6 import replay, assess
    metadata, vision, shots = camera_fixture(8)
    analysis = {'metadata': metadata, 'people_observations': vision['observations'],
                'video_analysis': {'frame_samples': vision['frames']}}
    write_json(tmp_path/'people_observations.json', analysis['people_observations'])
    write_json(tmp_path/'video_analysis.json', analysis['video_analysis'])
    write_json(tmp_path/'analysis.json', compact_analysis_document(analysis, tmp_path))
    write_json(tmp_path/'08_person_reid.json', {'data': {'metrics': {'persistent_person_count': 1}}})
    write_json(tmp_path/'01_metadata.json', {'data': metadata})
    write_json(tmp_path/'shots.json', shots)
    write_json(tmp_path/'active_speaker.json', [turn(0, 8)])
    result = replay(tmp_path)
    assert any(row['focus_person'] for row in result['timeline'])
    assert assess(result)['zoom']['zoom_gate_diagnostics']['source']['width'] == metadata['width']
    write_json(tmp_path/'people_observations.json', [])
    with pytest.raises(ValueError, match='Checksum'):
        replay(tmp_path)


@pytest.mark.parametrize('resolution,grounded', [((1280, 720), True), ((320, 240), False)])
def test_camera_can_act_on_positive_fixture_and_reports_parallel_240p_barriers(resolution, grounded):
    duration = 30 if grounded else 12
    metadata, vision, shots = camera_fixture(duration)
    metadata.update(width=resolution[0], height=resolution[1])
    voice = dict(turn(0, duration), active_speaker_state='CONFIRMED' if grounded else 'UNCERTAIN',
                 active_person='PERSON_A' if grounded else None)
    moment = {'moment_id': 'SYNTHETIC_HOOK', 'start': 0, 'end': 10, 'categories': ['hook'],
              'hook_score': .9, 'evidence_segment_ids': ['ANNOTATED_SEGMENT']}
    data = build_camera_director(metadata, vision, shots, [voice], [],
                                {'output_width': 540, 'output_height': 960},
                                main_moments=[moment] if grounded else [])['data']
    audit = data['metrics']['zoom_gate_diagnostics']
    assert audit['window_count_denominator'] == len(data['focus_window_audit'])
    assert audit['stages']['render']['delivery_verified'] is None
    assert not audit['publication_approval_inferred']
    if grounded:
        assert data['metrics']['zoom_accepted_event_count'] > 0
        assert any(r['focus_person'] for r in data['timeline'])
    else:
        assert all(r['layout'] == 'full_frame' for r in data['timeline'])
        codes = {r['code'] for r in audit['additional_root_causes']}
        assert {'NO_CONFIRMED_AUDIO_VISUAL_TARGET', 'NO_GROUNDED_EDITORIAL_BEAT', 'upscale_limit'} <= codes
        assert data['metrics']['zoom_zero_root_cause'] == 'NO_GROUNDED_EDITORIAL_BEAT'


def test_rendered_synthetic_canaries_consume_motion_and_preserve_negative_source(tmp_path):
    from scripts.dev.sol_v3_camera_canary import run_canaries
    report = run_canaries(tmp_path/'canaries')
    positive, negative = report['cases']
    assert positive['director_focused'] and positive['accepted_zoom_events'] > 0
    assert positive['rendered_motion']
    scales = positive['rendered_motion'][0]['scale_samples']
    assert scales[-1][1] > scales[0][1]
    assert not negative['director_focused'] and negative['accepted_zoom_events'] == 0
    assert negative['rendered_motion'] == []
    for case in report['cases']:
        assert case['rendered_frames'] == 30
        assert not case['publication_ready'] and not case['human_review']
        for frame in case['observed_frames']:
            assert len(frame['decoded_pixels_sha256']) == 64
            assert frame['synthetic_marker_pixels'] > 0
            assert frame['synthetic_marker_minimum_margin_fraction'] > .1
            assert frame['laplacian_variance'] > 0
