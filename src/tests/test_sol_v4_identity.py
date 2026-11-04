"""SOL V4 B: synthetic identities/waveforms; no human accuracy or model inference."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from ldporto.active_speaker import build_active_speaker, build_global_affinity
from ldporto.config import DEFAULTS, load_config, merge, validate
from ldporto.person_reid import _face_neighbors, _conflict, build_person_identities
from ldporto.pipeline import _active_stage
from ldporto.speaker_windows import partition_evidence_slice, mouth_sample_diagnostics
from ldporto.speaker_roles import lag_consistency
from ldporto.vision import ActiveSpeakerEngine
from test_sol_v3_visual_diagnostics import controlled_signal_fixture


@pytest.mark.parametrize('start,end', [(0., 3.1), (7.152218750000001, 19.403468750000002),
                                      (0., 0.), (105.47203333333334, 112.82346875)])
def test_legacy_arithmetic_matches_existing_repeated_addition(start, end):
    expected, cursor = [], start
    while cursor < end:
        stop = min(end, cursor+3.)
        expected.append((cursor, stop)); cursor = stop
    assert partition_evidence_slice(start, end) == expected


@pytest.mark.parametrize('duration,parts', [(3.1, 2), (6.4, 3), (7.35143541666666, 3)])
def test_balanced_tail_recovers_short_measurement_part_without_lowering_gates(duration, parts):
    bounds = partition_evidence_slice(0., duration, policy='balanced_tail')
    assert len(bounds) == parts and bounds[0][0] == 0 and bounds[-1][1] == duration
    assert all(1.5 <= b-a <= 3 for a, b in bounds)
    assert all(bounds[i][1] == bounds[i+1][0] for i in range(len(bounds)-1))


@pytest.mark.parametrize('duration', [1., 2.9, 3., 4.5, 5.9, 6.])
def test_balancing_retains_legacy_when_no_recoverable_short_tail(duration):
    assert partition_evidence_slice(0., duration, policy='balanced_tail') == partition_evidence_slice(0., duration)


def test_unbalanceable_tail_keeps_legacy_and_config_default_is_unchanged():
    assert partition_evidence_slice(0., 3.5, min_audio_seconds=2., policy='balanced_tail') == [(0., 3.), (3., 3.5)]
    assert 'evidence_window_policy' not in DEFAULTS['active_speaker']
    cfg = merge(DEFAULTS, {'active_speaker': {'evidence_window_policy': 'balanced_tail'}})
    validate(cfg)
    assert cfg['active_speaker']['evidence_window_policy'] == 'balanced_tail'
    cfg['active_speaker']['evidence_window_policy'] = 'invented'
    with pytest.raises(ValueError, match='evidence_window_policy'):
        validate(cfg)


@pytest.mark.parametrize('bounds', [(0., float('nan')), (3., 0.), (0., True)])
def test_invalid_geometry_is_rejected(bounds):
    with pytest.raises(ValueError):
        partition_evidence_slice(*bounds)


def test_mouth_null_is_not_invented_landmark_failure():
    data = mouth_sample_diagnostics([{'time': 0., 'lip_opening': None, 'track_id': 'a'},
                                     {'time': .2, 'lip_opening': float('nan'), 'track_id': 'a'},
                                     {'time': 1., 'lip_opening': .3, 'track_id': 'a'}])
    assert data['missing_mouth_observation_count'] == data['invalid_mouth_value_count'] == 1
    assert data['maximum_observed_gap_seconds'] == .8
    assert 'null_does_not_prove_invalid_landmarks' in data['scope']


def signal_case(tmp_path, policy='legacy'):
    source, vision, _ = controlled_signal_fixture(tmp_path)
    vision['observations'] = [row for row in vision['observations'] if row['time'] < 3.6]
    vision['frames'] = [row for row in vision['frames'] if row['time'] < 3.6]
    vision['scene_intervals'] = [{'start': 0., 'end': 3.6, 'scene_id': 'SH1'}]
    diar = {'speakers': [{'speaker_id': 'S1'}], 'turns': [{'start': 0., 'end': 3.6, 'speaker': 'S1'}],
            'overlaps': []}
    cfg = load_config()
    cfg['active_speaker']['evidence_window_policy'] = policy
    ctx = SimpleNamespace(config=cfg)
    metadata = {'width': 1920, 'height': 1080, 'fps': 30, 'duration': 3.6}
    return source, vision, diar, ctx, metadata


def test_balanced_synthetic_signal_recalculates_two_windows_and_preserves_thresholds(tmp_path):
    source, vision, diar, ctx, metadata = signal_case(tmp_path, 'balanced_tail')
    data = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    assert data['window_planning']['balanced_slice_count'] == 1
    measured = [row for row in data['mappings'] if row['audio_measurement']['status'] == 'audio_window_read']
    assert len(measured) == 2 and all(row['candidates'] for row in measured)
    # The recorded first-frame boundary stays intact, including its short prefix.
    assert data['mappings'][0]['end'] == vision['frames'][0]['time']
    refined = build_active_speaker(diar, vision, data['mappings'], ctx.config['active_speaker'])['data']
    assert refined['mapping_summary'][0]['person_id'] == 'P1'
    assert any(row['active_person'] == 'P1' for row in refined['intervals'])
    assert ctx.config['active_speaker']['min_confidence'] == .55
    assert ctx.config['active_speaker']['min_consensus_windows'] == 2
    assert all(c['mouth_sample_diagnostics']['tracklet_count'] == 1 for row in data['mappings'] for c in row['candidates'])


def test_legacy_short_tail_does_not_create_second_independent_signal(tmp_path):
    source, vision, diar, ctx, metadata = signal_case(tmp_path)
    data = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    assert data['mappings'][-1]['audio_measurement']['status'] == 'skipped_short_audio_window'
    refined = build_active_speaker(diar, vision, data['mappings'], ctx.config['active_speaker'])['data']
    assert refined['mapping_summary'][0]['person_id'] is None
    assert not any(row['active_person'] for row in refined['intervals'])


def test_balanced_overlap_keeps_person_unknown_and_does_not_read_mixdown(tmp_path):
    source, vision, diar, ctx, metadata = signal_case(tmp_path, 'balanced_tail')
    diar['turns'].append({'start': 0., 'end': 3.6, 'speaker': 'S2'})
    diar['speakers'].append({'speaker_id': 'S2'})
    diar['overlaps'] = [{'start': 0., 'end': 3.6}]
    data = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    assert data['mappings'] and all(not row['candidates'] and row['person_id'] is None for row in data['mappings'])
    assert all(row['audio_measurement']['status'] == 'skipped_audio_overlap' for row in data['mappings'])


def test_balancing_does_not_bridge_cut_or_silence(tmp_path):
    source, vision, diar, ctx, metadata = signal_case(tmp_path, 'balanced_tail')
    vision['scene_intervals'] = [{'start': 0., 'end': 1.8, 'scene_id': 'SH1'},
                                 {'start': 1.8, 'end': 3.6, 'scene_id': 'SH2'}]
    for row in vision['observations'] + vision['frames']:
        row['scene_id'] = 'SH1' if row['time'] < 1.8 else 'SH2'
    wave, rate = sf.read(source, dtype='float32')
    sf.write(source, np.zeros_like(wave), rate)
    data = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    assert data['window_planning']['balanced_slice_count'] == 0
    assert any(row['end'] == 1.8 for row in data['mappings'])
    assert not any(row['candidates'] for row in data['mappings'])


def test_active_stage_preserves_engine_diagnostics_without_repeating_raw_mappings(tmp_path):
    source, vision, diar, ctx, metadata = signal_case(tmp_path, 'balanced_tail')
    result = _active_stage(ctx, {'mono': source}, diar, vision, metadata, ctx.config['active_speaker'])
    assert result['data']['window_planning']['balanced_slice_count'] == 1
    assert result['data']['measurement_failure_counts']['candidates_emitted'] > 0
    assert result['data']['observed_mouth_samples']['missing_mouth_observation_count'] == 0
    assert 'raw_mappings' not in result['data']


@pytest.mark.parametrize('cause,counter', [('duration', 'insufficient_visual_duration'),
                                         ('shot', 'shot_change_inside_evidence'),
                                         ('invalid', 'invalid_mouth_value')])
def test_actual_candidate_screening_causes_remain_separate_and_unknown(tmp_path, cause, counter):
    source, vision, diar, ctx, metadata = signal_case(tmp_path)
    for index, row in enumerate(vision['observations']):
        if row['person_id'] != 'P1':
            continue
        if cause == 'duration' and row['time'] > 1.6:
            row['lip_opening'] = None
        elif cause == 'shot':
            row['scene_id'] = 'SH1' if index % 4 else 'UNEXPECTED_SHOT'
        elif cause == 'invalid':
            row['lip_opening'] = float('nan')
    data = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    assert data['measurement_failure_counts'][counter] > 0
    assert not any(row['person_id'] for row in data['mappings'])


def test_small_gallery_scores_and_ties_are_exact_legacy():
    rng = np.random.default_rng(7)
    matrix = rng.normal(size=(311, 32)); matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    query = matrix[19]
    people = {str(i): {'template': vector} for i, vector in enumerate(matrix)}
    scores = matrix @ query
    ids = np.argsort(-scores, kind='stable')[:64]
    assert _face_neighbors(query, people, 64) == [(float(scores[i]), str(i)) for i in ids]


def test_large_gallery_uses_bounded_blocks_and_preserves_global_competitor(monkeypatch):
    gallery = {f'P{i:04}': {'template': np.array([0., 1.])} for i in range(2602)}
    gallery['P0003']['template'] = np.array([.95, math.sqrt(1-.95**2)])
    gallery['P2580']['template'] = np.array([1., 0.])
    original_stack, sizes = np.stack, []
    def measured_stack(values, *args, **kwargs):
        sizes.append(len(values)); return original_stack(values, *args, **kwargs)
    monkeypatch.setattr(np, 'stack', measured_stack)
    assert _face_neighbors(np.array([1., 0.]), gallery, 1) == [(1., 'P2580'), (.95, 'P0003')]
    assert max(sizes) <= 256
    gallery['P2580']['intervals'] = [(10., 12.)]
    assert _conflict({'first_seen': 11., 'last_seen': 13.}, gallery['P2580'])
    # Retrieval retains the simultaneous best; it never supplies only runner-up.
    assert _face_neighbors(np.array([1., 0.]), gallery, 2)[0][1] == 'P2580'


def test_large_gallery_ties_preserve_original_order_across_blocks():
    gallery = {f'P{i:04}': {'template': np.array([0., 1.])} for i in range(2602)}
    assert _face_neighbors(np.array([0., 1.]), gallery, 1) == [(1., 'P0000'), (1., 'P0001')]


def test_large_gallery_resource_failure_never_accepts_partial_gallery(monkeypatch):
    gallery = {str(i): {'template': np.array([0., 1.])} for i in range(2602)}
    original, calls = np.stack, []
    def fail_later(values, *args, **kwargs):
        calls.append(len(values))
        if len(calls) == 2:
            raise MemoryError('synthetic resource canary')
        return original(values, *args, **kwargs)
    monkeypatch.setattr(np, 'stack', fail_later)
    with pytest.raises(MemoryError):
        _face_neighbors(np.array([0., 1.]), gallery)


@pytest.mark.parametrize('query', [np.array([float('nan'), 0.]), np.zeros(4097), np.ones(1)])
def test_invalid_or_oversized_query_does_not_create_identity_evidence(query):
    assert _face_neighbors(query, {'P': {'template': np.ones(2)}}) == []


def synthetic_track(tid, start, vector, raw=None, online=None):
    return [dict(track_id=tid, person_id=raw or 'P_'+tid, time=start+i, scene_id='SH1',
                 face_visible=vector is not None, face_embedding=vector,
                 tracking_method='anonymous_face_embedding' if online is not None else 'new_identity',
                 same_person_confidence=online) for i in range(3)]


def test_reid_seeds_merges_unmapped_and_legacy_abstention_are_distinct():
    rows = synthetic_track('a', 0, [1., 0.]) + synthetic_track('b', 10, [1., 0.])
    rows += [dict(track_id='micro', person_id='Pmicro', time=20., scene_id='SH1', face_visible=False)]
    result = build_person_identities({'observations': rows})['data']
    metrics = result['metrics']
    assert metrics['reid_seed_track_count'] == metrics['reid_merged_track_count'] == metrics['reid_unmapped_track_count'] == 1
    assert metrics['reid_abstained_track_count'] == 2
    assert result['tracklet_to_person']['a'] == result['tracklet_to_person']['b']
    assert result['tracklet_to_person']['micro'] is None


def test_online_raw_identity_never_overrides_ambiguous_offline_margin():
    a = [1., 0.]; b = [math.cos(.02), math.sin(.02)]
    rows = synthetic_track('a', 0, a, raw='RAW') + synthetic_track('b', 0, b)
    rows += synthetic_track('c', 10, a, raw='RAW', online=.99)
    result = build_person_identities({'observations': rows})['data']
    assert result['tracklet_to_person']['c'] != result['tracklet_to_person']['a']
    assert result['metrics']['best_candidate_rejection_gates']['margin_below_required'] >= 1
    pairs = result['online_offline_review_pairs']
    assert pairs and all(pair['annotation_same_person'] is None and pair['auto_merge'] is False for pair in pairs)
    assert not result['outcome_diagnostics']['human_identity_accuracy_measured']


def test_benchmark_reads_only_relevant_verified_projection_chunks(tmp_path):
    script = Path(__file__).resolve().parents[2]/'scripts/dev/benchmark_speaker_windows_sol_v4.py'
    spec = importlib.util.spec_from_file_location('bounded_speaker_benchmark', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    data = json.dumps({'records': [{'time': 87., 'person_id': 'synthetic'}]}).encode()
    path = tmp_path/'observations.json'; path.write_bytes(data)
    chunk = {'path': path.name, 'sha256': hashlib.sha256(data).hexdigest(), 'record_count': 1, 'start': 87., 'end': 87.}
    summary = {'observation_projection': {'chunks': [chunk, dict(chunk, path='absent_ignored.json', start=900., end=901.)]}}
    (tmp_path/'people_summary.json').write_text(json.dumps(summary), encoding='utf-8')
    rows, consumed = module.load_projected_observations(tmp_path, module.SLICES)
    assert len(rows) == len(consumed) == 1
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='hash mismatch'):
        module.load_projected_observations(tmp_path, module.SLICES)


def test_tail_anchor_keeps_legacy_and_only_adds_bounded_short_tail_probe():
    legacy = partition_evidence_slice(10., 13.1)
    anchored = partition_evidence_slice(10., 13.1, policy='tail_anchor')
    assert anchored[:-1] == legacy
    assert anchored[-1] == (10.1, 13.1)
    assert 1.5 <= anchored[-1][1]-anchored[-1][0] <= 3.
    assert partition_evidence_slice(0., 4.5, policy='tail_anchor') == partition_evidence_slice(0., 4.5)
    cfg = merge(DEFAULTS, {'active_speaker': {'evidence_window_policy': 'tail_anchor'}})
    validate(cfg)
    assert 'evidence_window_policy' not in DEFAULTS['active_speaker']


def test_tail_anchor_preserves_all_legacy_scores_and_ids_without_acoustic_overlap(tmp_path):
    source, vision, diar, ctx, metadata = signal_case(tmp_path)
    legacy = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    ctx.config['active_speaker']['evidence_window_policy'] = 'tail_anchor'
    anchored = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    retained = [row for row in anchored['mappings'] if row.get('measurement_window_kind') != 'tail_anchor']
    assert retained == legacy['mappings']
    probes = [row for row in anchored['mappings'] if row.get('measurement_window_kind') == 'tail_anchor']
    assert len(probes) == 1 and probes[0]['measurement_overlap'] is True
    assert probes[0]['overlap'] is False
    assert anchored['window_planning']['tail_anchor_slice_count'] == 1


def test_overlapping_tail_probe_never_creates_second_independent_consensus_vote():
    # Deliberately strong SYNTHETIC duplicate evidence, not measured speech.
    candidate = {'person_id': 'P1', 'correlation': .99, 'correlation_lower_bound_proxy': .8,
                 'correlation_upper_bound_proxy': 1., 'audio_lag_seconds': 0.,
                 'sample_count': 14, 'track_stability': 1., 'face_visibility': 1.,
                 'visibility_coverage': .93, 'audio_activity_rms': .1}
    rows = [{'start': 0., 'end': 3., 'speaker_id': 'S1', 'evidence_window_id': 'LEGACY',
             'candidates': [dict(candidate, mouth_start=.1, mouth_end=2.9)]},
            {'start': .1, 'end': 3.1, 'speaker_id': 'S1', 'evidence_window_id': 'ANCHOR',
             'measurement_window_kind': 'tail_anchor', 'measurement_overlap': True,
             'overlap': False, 'candidates': [dict(candidate, mouth_start=.2, mouth_end=3.)]}]
    turns = [{'start': 0., 'end': 3.1, 'speaker': 'S1'}]
    summary, stable, affinity = build_global_affinity(turns, {'P1'}, rows, DEFAULTS['active_speaker'])
    assert not stable and summary[0]['person_id'] is None
    assert summary[0]['positive_windows'] == affinity[0]['evidence_windows'] == 1
    assert affinity[0]['evidence_refs'] == ['LEGACY']
    report = lag_consistency(rows, 'S1', 'P1', DEFAULTS['active_speaker'], turns)
    assert report['independent_windows'] == 1 and not report['consistent']


@pytest.mark.parametrize('boundary', ['cut', 'acoustic_overlap'])
def test_tail_anchor_respects_source_cut_and_acoustic_overlap(tmp_path, boundary):
    source, vision, diar, ctx, metadata = signal_case(tmp_path, 'tail_anchor')
    if boundary == 'cut':
        vision['scene_intervals'] = [{'start': 0., 'end': 1.8, 'scene_id': 'SH1'},
                                     {'start': 1.8, 'end': 3.6, 'scene_id': 'SH2'}]
        for row in vision['observations'] + vision['frames']:
            row['scene_id'] = 'SH1' if row['time'] < 1.8 else 'SH2'
    else:
        diar['turns'].append({'start': 0., 'end': 3.6, 'speaker': 'S2'})
        diar['speakers'].append({'speaker_id': 'S2'})
        diar['overlaps'] = [{'start': 0., 'end': 3.6}]
    data = ActiveSpeakerEngine().run(ctx, {'mono': source}, diar, vision, metadata)['data']
    if boundary == 'cut':
        assert not any(row.get('measurement_window_kind') == 'tail_anchor' for row in data['mappings'])
        assert all(not row['start'] < 1.8 < row['end'] for row in data['mappings'])
    else:
        assert all(row['overlap'] and not row['candidates'] for row in data['mappings'])
        assert all(row['audio_measurement']['status'] == 'skipped_audio_overlap' for row in data['mappings'])
