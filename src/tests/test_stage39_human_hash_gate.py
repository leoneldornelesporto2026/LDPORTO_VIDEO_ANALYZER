"""Offline/synthetic gate contracts. Checklists here are never human evidence."""
from copy import deepcopy
from pathlib import Path

import pytest

from ldporto import curator_delivery as d
from ldporto import homologation_s11 as h
from test_s9_s10_s11_delivery import media, ready, ALL_REVIEWED


@pytest.fixture
def gate(tmp_path, ready, media):
    # No inference or render required: real bytes, mocked technical validation only.
    plan = d.prepare_plan(ready, media)
    mp4, ass = tmp_path/'fixture.mp4', tmp_path/'fixture.ass'
    mp4.write_bytes(b'SYNTHETIC_GATE_BYTES_NOT_PLAYABLE')
    ass.write_text('SYNTHETIC SUBTITLES', encoding='utf-8')
    report = {'id': plan['clips'][0]['id'], 'file': str(mp4), 'sha256': d.file_sha256(mp4),
              'status': 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW',
              'plan_sha256': plan['plan_sha256'], 'source_sha256': plan['source_sha256'],
              'package_sha256': plan['package_sha256'],
              'subtitle_artifacts': {'ass': {'file': str(ass), 'sha256': d.file_sha256(ass)}}}
    return plan, report


@pytest.fixture(autouse=True)
def technical_stub(monkeypatch):
    monkeypatch.setattr(d, 'verify_mp4', lambda *a, **kw: {'status': 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW'})


@pytest.mark.parametrize('field,value', [('title_suggestion', 'changed title'), ('start', 0.5),
                                         ('render_layout', 'changed frame'), ('audio_mode', 'changed music')])
def test_rehashed_audiovisual_override_invalidates_old_approval(gate, field, value):
    plan, report = gate
    approval = d.approve_canary(plan, report, ALL_REVIEWED, reviewer='SYNTHETIC_ONLY')
    plan['clips'][0][field] = value
    plan['plan_sha256'] = d.canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    with pytest.raises(ValueError, match='APPROVAL_INVALIDATED'):
        d.verify_approval(plan, approval, report)


@pytest.mark.parametrize('kind', ['ass', 'srt', 'mp4', 'report'])
def test_artifact_override_after_approval_blocks(gate, tmp_path, kind):
    plan, report = gate
    if kind == 'srt':
        srt = tmp_path/'fixture.srt'
        srt.write_text('SYNTHETIC SRT', encoding='utf-8')
        report['subtitle_artifacts']['srt'] = {'file': str(srt), 'sha256': d.file_sha256(srt)}
    approval = d.approve_canary(plan, report, ALL_REVIEWED, reviewer='SYNTHETIC_ONLY')
    if kind == 'report':
        report['audio_mix_log'] = {'listening_verified': True}
    else:
        path = report['file'] if kind == 'mp4' else report['subtitle_artifacts'][kind]['file']
        with Path(path).open('ab') as stream:
            stream.write(b'OVERRIDE')
    with pytest.raises(ValueError):
        d.verify_approval(plan, approval, report)


@pytest.mark.parametrize('check', ['listening', 'audio_sync', 'legibility', 'payoff'])
@pytest.mark.parametrize('pending', [None, False, 'true'])
def test_critical_human_checks_never_automatically_checked(gate, check, pending):
    plan, report = gate
    checks = {**ALL_REVIEWED, check: pending}
    with pytest.raises(ValueError, match='CHECKLIST_NOT_COMPLETE'):
        d.approve_canary(plan, report, checks, reviewer='SYNTHETIC_ONLY')
    assert checks[check] is pending


def test_decision_bytes_rechecked_after_approval(gate, tmp_path):
    plan, report = gate
    decisions = tmp_path/'decisions.json'
    decisions.write_text('{}', encoding='utf-8')
    plan.update(decisions_path=str(decisions), decisions_explicit=True, decisions_sha256=d.file_sha256(decisions))
    plan['plan_sha256'] = d.canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    report['plan_sha256'] = plan['plan_sha256']
    approval = d.approve_canary(plan, report, ALL_REVIEWED, reviewer='SYNTHETIC_ONLY')
    decisions.write_text('{"override":true}', encoding='utf-8')
    with pytest.raises(ValueError, match='DECISIONS_MODIFIED'):
        d.verify_approval(plan, approval, report)


@pytest.mark.parametrize('path_key,hash_key,error', [
    ('source_video', 'source_sha256', 'SOURCE_MODIFIED'),
    ('music_file', 'music_sha256', 'INSTRUMENTAL_MODIFIED'),
    ('package_path', 'package_sha256', 'PACKAGE_MODIFIED')])
def test_external_dependency_bytes_invalidate_approval(gate, tmp_path, path_key, hash_key, error):
    plan, report = gate
    dependency = tmp_path/'dependency.bin'
    dependency.write_bytes(b'SYNTHETIC_DEPENDENCY')
    plan[path_key], plan[hash_key] = str(dependency), d.file_sha256(dependency)
    plan['plan_sha256'] = d.canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    report.update(plan_sha256=plan['plan_sha256'], source_sha256=plan['source_sha256'],
                  package_sha256=plan['package_sha256'])
    approval = d.approve_canary(plan, report, ALL_REVIEWED, reviewer='SYNTHETIC_ONLY')
    dependency.write_bytes(b'OVERRIDDEN_DEPENDENCY')
    with pytest.raises(ValueError, match=error):
        d.verify_approval(plan, approval, report)


def test_batch_membership_partial_and_stale_individual_reviews(gate):
    plan, report = gate
    approval = d.approve_canary(plan, report, ALL_REVIEWED, reviewer='SYNTHETIC_ONLY')
    batch = {'state': 'PARTIAL', 'plan_sha256': plan['plan_sha256'], 'clips': [report],
             'canary_approval': approval, 'canary_report': report,
             'canary_approval_sha256': d.canonical_hash(approval)}
    with pytest.raises(ValueError, match='BATCH_NOT_READY'):
        d.finalize_batch(plan, batch, {})
    batch['state'] = 'REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE'
    with pytest.raises(ValueError, match='MEMBERSHIP'):
        d.finalize_batch(plan, batch, {})
    second = deepcopy(report)
    second['id'] = plan['clips'][1]['id']
    batch['clips'].append(second)
    reviews = {'clips': [{'id': c['id'], 'sha256': c['sha256'], 'checklist': ALL_REVIEWED,
                         'reviewer': 'SYNTHETIC_ONLY', 'plan_sha256': plan['plan_sha256'],
                         'render_report_sha256': d.canonical_hash(c)} for c in batch['clips']]}
    assert d.finalize_batch(plan, batch, reviews)['publication_ready'] is False
    reviews['clips'][1]['render_report_sha256'] = 'old-report'
    with pytest.raises(ValueError, match='PER_CLIP_REVIEW_PENDING'):
        d.finalize_batch(plan, batch, reviews)


def test_homologation_partial_batch_cannot_replace_individual_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(h, '_runtime_checks', lambda: {'python311_windows': True,
        'gpu': {'available': False}, 'ollama_local': {'reachable': False}, 'ffmpeg_encoder_libx264': True})
    batch = d.save_json(tmp_path/'batch.json', {'state': 'PARTIAL', 'clips': []})
    result = h.homologate(batch_manifest=batch)
    assert 'BATCH_HASH_BOUND_INDEPENDENT_REVIEW_PENDING' in result['blockers']
    assert result['ready_to_publish'] is False
    assert result['editorial_human_approval'] is False
