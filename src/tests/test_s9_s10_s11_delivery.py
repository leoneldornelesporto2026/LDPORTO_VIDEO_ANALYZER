"""Real FFmpeg synthetic integration + fail-closed S9/S10/S11 contracts."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import subprocess

import pytest

from ldporto.curator_delivery import (prepare_plan, save_json, file_sha256, validate_plan,
                                      approve_canary, render_clip, render_batch,
                                      verify_approval, finalize_batch, verify_mp4)
from ldporto.performance_acceptance import evaluate_vision_ab, evaluate_semantic_ab, review_checkpoint_state
from ldporto.homologation_s11 import metric_delta, homologate
from ldporto.second_curation_export import build_core_package
from test_v43_handoff import analysis_fixture

ALL_REVIEWED = {key: True for key in ('editorial','commercial','subtitles','camera','audio','safe_area','payoff')}


@pytest.fixture(scope='module')
def media(tmp_path_factory):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('actual FFmpeg test requires both tools')
    target = tmp_path_factory.mktemp('s9_media')/'fixture.avi.mp4'
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
           '-i', 'testsrc2=size=320x180:rate=24', '-f', 'lavfi',
           '-i', 'sine=frequency=440:sample_rate=44100', '-t', '5', '-c:v', 'libx264',
           '-threads', '2', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(target)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return target


@pytest.fixture
def ready(tmp_path, media):
    data = analysis_fixture()
    data['metadata'].update(duration=5, width=320, height=180, fps=24, sha256=file_sha256(media))
    data['metadata']['source']['id'] = 'synthetic_only'
    data['transcript_segments'] = [
        {'segment_id':'S0','start':0,'end':1,'speaker':'SP1','text':'Vamos falar sobre isso.'},
        {'segment_id':'S1','start':1,'end':3,'speaker':'SP1','text':'Uma historia com final.'},
        {'segment_id':'S2','start':3,'end':5,'speaker':'SP1','text':'Agora outra historia.'},
    ]
    data['topics'][0].update(start=0,end=5)
    data['shots'][0].update(start=0,end=5)
    data['main_moments'][0].update(ideal_start=1,ideal_end=3, core_moment={'start':1,'end':3,'text':'Uma historia com final.'}, evidence_segment_ids=['S1'])
    second = deepcopy(data['main_moments'][0])
    second.update(moment_id='M2',ideal_start=3,ideal_end=4.7,core_moment={'start':3,'end':4.7,'text':'Agora outra historia.'},evidence_segment_ids=['S2'])
    data['main_moments'].append(second)
    data['editorial_shortlist'] = ['M1','M2']
    data['social_output'] = {'story_readiness':'READY', 'stories': [
        {'story_id':'STORY_001','candidate_id':'M1','start':1,'end':3,'title':'Historia um'},
        {'story_id':'STORY_002','candidate_id':'M2','start':3,'end':4.7,'title':'Historia dois'},
    ]}
    output = build_core_package(data, source=media, output_dir=tmp_path/'packages')
    assert output['state'] == 'READY'
    return Path(output['path'])


def test_s9_real_ffmpeg_canary_with_full_approval_and_independent_batch(tmp_path, ready, media):
    plan = prepare_plan(ready, media)
    assert len(plan['clips']) == 2
    assert all(c['render_layout'] == 'source_preserve_blurred_fill' for c in plan['clips'])
    canary = render_clip(plan, 0, tmp_path/'canary', draft_captions=True)
    assert canary['status'] == 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW'
    assert canary['probe']['width'] == 1080 and canary['probe']['height'] == 1920
    assert canary['probe']['audio_count'] == 1 and canary['publication_ready'] is False
    with pytest.raises(ValueError, match='CHECKLIST'):
        approve_canary(plan, canary, {'editorial': True}, reviewer='QA')
    approval = approve_canary(plan, canary, ALL_REVIEWED, reviewer='Synthetic-Test-Reviewer')
    manifest = render_batch(plan, approval, canary, tmp_path/'batch', draft_captions=True)
    assert len(manifest['clips']) == 2
    assert manifest['state'] == 'REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE'
    assert all(Path(c['file']).is_file() for c in manifest['clips'])
    assert manifest['clips'][0]['sha256'] == canary['sha256']
    with pytest.raises(ValueError, match='MISSING_PER_CLIP'):
        finalize_batch(plan, manifest, {'clips': []})
    reviews = {'clips': [{'id': c['id'], 'sha256': c['sha256'], 'reviewer': 'Synthetic-Test-Reviewer',
                          'checklist': ALL_REVIEWED} for c in manifest['clips']]}
    final = finalize_batch(plan, manifest, reviews)
    assert final['state'] == 'REVIEWED_FINAL_FILES' and final['publication_ready'] is False


def test_s9_tampering_and_invalid_subtitle_approval_blocks(ready, media, tmp_path):
    plan = prepare_plan(ready, media)
    changed = deepcopy(plan)
    changed['clips'][0]['title_suggestion'] = 'CLICKBAIT NÃO SUSTENTADO'
    with pytest.raises(ValueError, match='TAMPERED'):
        validate_plan(changed)
    canary = render_clip(plan, 0, tmp_path/'canary')
    approval = approve_canary(plan, canary, ALL_REVIEWED, reviewer='QA')
    with Path(canary['file']).open('ab') as stream:
        stream.write(b'changed!')
    with pytest.raises(ValueError, match='APPROVAL_INVALIDATED'):
        verify_approval(plan, approval, canary)


def test_s9_source_sha_and_partial_packages_fail_closed(ready, media, tmp_path):
    different = tmp_path/'different.mp4'
    different.write_bytes(b'incorrect-video')
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        prepare_plan(ready, different)
    incomplete = analysis_fixture()
    pkg = build_core_package(incomplete, output_dir=tmp_path/'partial')
    with pytest.raises(ValueError, match='NOT_READY'):
        prepare_plan(pkg['path'], media)


def test_s9_commercial_exclusion_survives_plan(tmp_path, ready, media, monkeypatch):
    from ldporto import curator_delivery as delivery
    # Input validation executes first; when an included candidate is disallowed
    # downstream it must fail even if a stale story row still references it.
    monkeypatch.setattr(delivery, '_safe_candidate', lambda candidate: False)
    with pytest.raises(ValueError, match='COMMERCIAL_OR_UNREVIEWABLE'):
        prepare_plan(ready, media)


def test_s10_measured_parallel_requires_box_equivalence_and_gain():
    sample = {'sample_count': 12, 'detection_boxes_identical': True, 'detector_calls_identical': True,
              'cpu_parallel_available': True, 'speedup_x': 1.24}
    assert evaluate_vision_ab(sample)['local_opt_in_recommended'] is True
    sample['detection_boxes_identical'] = False
    assert evaluate_vision_ab(sample)['local_opt_in_recommended'] is False
    assert evaluate_semantic_ab({'samples': [{'index': 0, 'modes': {'legacy': {'status': 'valid_first_pass', 'elapsed_seconds': 10},
                                                'compact': {'status': 'valid_first_pass', 'elapsed_seconds': 6}}}]})['safe_to_enable_automatically'] is False


def test_s10_resume_is_readonly():
    result = review_checkpoint_state({'stage_status': {'04_transcription': {'status':'ok','cache_hit': True},
                                                       '16_understanding': {'status':'failed'}}})
    assert result['cache_mutated'] is False
    assert result['replay_needed_stages'] == ['16_understanding']
    assert result['stages'][0]['reuse_safe'] is True


def test_s11_deltas_and_human_approval_are_not_invented(tmp_path):
    before = {'status':'AVAILABLE', 'metrics':{'resolved_focus_coverage': 0.04}}
    after = {'status':'AVAILABLE', 'metrics':{'resolved_focus_coverage': 0.25}}
    assert metric_delta(before, after)['resolved_focus_coverage']['delta'] == pytest.approx(.21)
    report = homologate()
    assert report['release_status'] == 'BLOCKED_OR_PENDING'
    assert 'HUMAN_EDITORIAL_REVIEW_PENDING' in report['blockers']
    assert report['ready_to_publish'] is False


def test_s9_compiled_manual_decisions_preserve_title_timing_and_recommendations(tmp_path, ready, media):
    d = {'schema_version': '4.4.0', 'source_sha256': file_sha256(media),
         'input_package_sha256': file_sha256(ready), 'provider': 'manual_json',
         'actions': [{'decision_id':'REVIEW_M1', 'action':'approve', 'candidate_ids':['M1'],
                      'reason':'Janela completa revisável.', 'title':'Título baseado no áudio',
                      'suggested_layout':'source_preserve'}]}
    decisions = save_json(tmp_path/'decisions.json', d)
    plan = prepare_plan(ready, media, decisions_path=decisions)
    assert len(plan['clips']) == 1
    assert plan['clips'][0]['id'] == 'REVIEW_M1_01'
    assert plan['clips'][0]['title_suggestion'] == 'Título baseado no áudio'
    assert plan['clips'][0]['source_layout_recommendation'] == 'source_preserve'
    assert plan['decisions_explicit'] and plan['decisions_sha256'] == file_sha256(decisions)


def test_s9_instrumental_bed_is_included_but_never_changes_source_and_karaoke_is_blocked(tmp_path, ready, media):
    plan = prepare_plan(ready, media, music_path=media)
    assert plan['music_sha256'] == file_sha256(media)
    assert plan['clips'][0]['audio_mode'] == 'source_plus_instrumental'
    assert not plan['clips'][0]['karaoke_allowed']
    assert plan['clips'][0]['word_evidence_count'] == len(plan['clips'][0]['words'])
    report = render_clip(plan, 0, tmp_path/'with_bed')
    assert report['status'] == 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW'
    assert report['audio_mode'] == 'source_plus_instrumental'
