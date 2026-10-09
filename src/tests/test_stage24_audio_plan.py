"""Offline evidence fixtures and real FFmpeg synthetic audio, never real media."""
from copy import deepcopy
import json
import shutil
import subprocess
import zipfile

import numpy as np
import pytest

from ldporto.audio import plan_clip_audio, delivery_audio_filter
from ldporto.curator_delivery import prepare_plan, render_clip, file_sha256, validate_plan, canonical_hash
from test_s9_s10_s11_delivery import media, ready
import test_s9_s10_s11_delivery as delivery_fixtures


@pytest.mark.parametrize('label', ['performance', 'show_musical', 'music_performance', 'concert', 'musical'])
def test_performance_preserves_original(label):
    plan = plan_clip_audio([{'content_type': label}], [], 0, 3, instrumental=True)
    assert plan['audio_mode'] == 'original_performance'
    assert plan['instrumental_gain'] == 0
    assert delivery_audio_filter(plan) == '[0:a:0]anull[a]'


def test_interview_reactions_effects_and_voice_remain_separate():
    events = [{'start': 0, 'end': 2, 'type': 'speech'},
              {'start': 1, 'end': 2, 'type': 'laughter', 'origin': 'audience', 'inference': True},
              {'start': 2, 'end': 3, 'type': 'applause', 'origin': 'studio', 'origin_verified': True},
              {'start': 3, 'end': 4, 'type': 'sound_effect'}]
    before = deepcopy(events)
    plan = plan_clip_audio([{'content_type': 'interview'}], events, 0, 4, instrumental=True, gain=.06)
    assert events == before
    assert plan['audio_mode'] == 'source_plus_instrumental'
    assert [e['role'] for e in plan['events']] == ['voice', 'reaction', 'reaction', 'effect']
    assert [e['origin'] for e in plan['events']] == [None, None, 'studio', None]
    assert len(plan['humor_reaction_evidence']) == 3
    assert not plan['reaction_is_payoff_proof'] and not plan['stems_separated']
    assert plan['ducking_verified'] is None and plan['ducking_applied'] is False
    assert plan['listening_verified'] is None and not plan['publication_ready']


def test_unknown_music_role_blocks_overlay_without_inventing_provenance():
    plan = plan_clip_audio([], [{'start': -1, 'end': 2, 'type': 'music'}], 0, 3, instrumental=True)
    assert plan['audio_mode'] == 'source_original'
    assert plan['source_music_role'] is None and plan['events'][0]['origin'] is None
    assert plan['events'][0]['start'] == 0
    assert 'requires_listening' in plan['instrumental_reason']


def test_missing_and_outside_events_do_not_fabricate_reactions():
    events = [None, {'start': 0, 'end': float('nan'), 'type': 'music'},
              {'start': 8, 'end': 9, 'type': 'music'}, {'start': 2, 'end': 1, 'type': 'laughter'}]
    plan = plan_clip_audio([], events, 0, 3)
    assert plan['events'] == [] and plan['humor_reaction_evidence'] == []
    assert plan['audio_mode'] == 'source_original'


@pytest.mark.parametrize('gain', [-.1, .26, float('nan'), float('inf'), True, '0.1'])
def test_invalid_gain_fails(gain):
    with pytest.raises(ValueError, match='GAIN'):
        plan_clip_audio([], [], 0, 1, instrumental=True, gain=gain)


def test_zero_gain_disables_bed():
    assert plan_clip_audio([], [], 0, 1, instrumental=True, gain=0)['audio_mode'] == 'source_original'


@pytest.mark.parametrize('amplitude,bed,expected', [(.3, 0, .3), (.95, .95, None)])
def test_real_ffmpeg_mix_preserves_voice_gain_and_limits_sum(amplitude, bed, expected):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg unavailable')
    plan = plan_clip_audio([], [], 0, 1, instrumental=True, gain=.25)
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
           f'aevalsrc={amplitude}*sin(2*PI*440*t):s=48000:d=1', '-f', 'lavfi', '-i',
           f'aevalsrc={bed}*sin(2*PI*440*t):s=48000:d=1', '-filter_complex',
           delivery_audio_filter(plan), '-map', '[a]', '-f', 'f32le', '-c:a', 'pcm_f32le', '-']
    result = subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    samples = np.frombuffer(result.stdout, dtype='<f4')
    peak = float(np.max(np.abs(samples)))
    assert len(samples) == 48000
    assert peak <= .951
    if expected is not None:
        assert peak == pytest.approx(expected, abs=.001)


def test_actual_render_logs_mix_preserves_sources_and_refuses_overwrite(tmp_path, ready, media):
    hashes = (file_sha256(media), file_sha256(ready))
    plan = prepare_plan(ready, media, music_path=media, music_gain=.06)
    with zipfile.ZipFile(ready) as archive:
        assert json.loads(archive.read('audio/sound_events.json'))['events'] == []
    report = render_clip(plan, 0, tmp_path / 'render')
    log = report['audio_mix_log']
    assert 'normalize=0' in log['filter'] and 'volume=0.060000' in log['filter']
    assert log['plan']['ducking_applied'] is False
    assert log['encoded_peak_verified'] is None
    assert not report['publication_ready']
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', report['file'], '-vn',
        '-f', 'f32le', '-c:a', 'pcm_f32le', '-'], check=True, capture_output=True, timeout=30)
    samples = np.frombuffer(decoded.stdout, dtype='<f4')
    assert len(samples) > 0 and float(np.max(np.abs(samples))) < .999
    assert (file_sha256(media), file_sha256(ready)) == hashes
    with pytest.raises(FileExistsError, match='OVERWRITE'):
        render_clip(plan, 0, tmp_path / 'render')


def test_exported_music_hypothesis_suppresses_bed_only_on_overlapping_clip(tmp_path, media, monkeypatch):
    original = delivery_fixtures.analysis_fixture
    def with_events():
        data = original()
        data['audio_events'] = [{'start': 1, 'end': 2, 'type': 'music',
                                 'method': 'synthetic_fixture', 'inference': True},
                                {'start': 2, 'end': 3, 'type': 'laughter',
                                 'method': 'synthetic_fixture', 'inference': True}]
        return data
    monkeypatch.setattr(delivery_fixtures, 'analysis_fixture', with_events)
    package = delivery_fixtures.ready.__wrapped__(tmp_path, media)
    plan = prepare_plan(package, media, music_path=media)
    assert plan['clips'][0]['audio_mode'] == 'source_original'
    assert plan['clips'][1]['audio_mode'] == 'source_plus_instrumental'
    assert plan['clips'][0]['audio_plan']['humor_reaction_evidence'][0]['origin'] is None


def test_merged_or_overlapping_performance_is_protected():
    plan = plan_clip_audio([{'content_type': 'interview'}, {'category': 'musical'}],
                           [], 0, 3, instrumental=True)
    assert plan['audio_mode'] == 'original_performance'


def test_old_mix_plan_requires_new_plan_and_review(ready, media):
    plan = prepare_plan(ready, media, music_path=media)
    for clip in plan['clips']:
        clip.pop('audio_plan')
    plan['plan_sha256'] = canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    with pytest.raises(ValueError, match='REPLAN_AND_REVIEW_REQUIRED'):
        validate_plan(plan)
