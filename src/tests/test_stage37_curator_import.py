"""Offline decisions and synthetic media only; no independent Curator application."""
from copy import deepcopy
import json
import zipfile

import pytest
from jsonschema import ValidationError

from ldporto import curator_delivery as delivery
from ldporto.second_curation_decisions import compile_decisions
from test_s9_s10_s11_delivery import media, ready
from test_v44_second_curation import catalog, decisions


def document(package, source, **action):
    return {'schema_version': '4.4.0', 'provider': 'manual_json',
            'source_sha256': delivery.file_sha256(source),
            'input_package_sha256': delivery.file_sha256(package),
            'actions': [{'decision_id': 'EDIT', 'action': 'shrink', 'candidate_ids': ['M1'],
                         'reason': 'Synthetic review only', 'title': 'Título alternativo',
                         'windows': [{'start': 1.5, 'end': 2.5}], **action}]}


def test_dry_run_commit_replay_and_title_invalidation(tmp_path, ready, media):
    previous = delivery.prepare_plan(ready, media)
    unchanged = deepcopy(previous)
    path, state = tmp_path/'decisions.json', tmp_path/'import.json'
    delivery.save_json(path, document(ready, media))
    draft = delivery.import_decisions(ready, media, path, state_path=state, previous_plan=previous, dry_run=True)
    assert not state.exists() and previous == unchanged
    clip = draft['plan']['clips'][0]
    assert (clip['start'], clip['end'], clip['duration']) == (1.5, 2.5, 1)
    assert clip['segments'] == [{'start': 0, 'end': 1, 'text': 'Uma historia com final.'}]
    assert clip['title_suggestion'] == 'Título alternativo'
    assert clip['preview_approved'] is None and not clip['publish_ready']
    assert draft['plan']['curator_integration']['independent_app_verified'] is None
    committed = delivery.import_decisions(ready, media, path, state_path=state, previous_plan=previous)
    assert committed['plan'] == draft['plan']
    before = state.read_bytes(), state.stat().st_mtime_ns
    replay = delivery.import_decisions(ready, media, path, state_path=state)
    assert replay['replayed'] and not replay['committed'] and len(replay['journal']) == 1
    assert (state.read_bytes(), state.stat().st_mtime_ns) == before
    delivery.save_json(path, document(ready, media, title='Outra sugestão'))
    newer = delivery.import_decisions(ready, media, path, state_path=state)
    assert len(newer['journal']) == 2 and newer['plan']['plan_sha256'] != committed['plan']['plan_sha256']
    assert newer['journal'][-1]['previous_plan_sha256'] == committed['plan']['plan_sha256']
    assert newer['journal'][-1]['invalidated'] == ['preview', 'canary_approval', 'batch_review']


@pytest.mark.parametrize('fault', ['bounds', 'id', 'title', 'source_hash', 'package_hash', 'missing_hash', 'layout'])
def test_invalid_decision_does_not_modify_state_or_previous_plan(tmp_path, ready, media, fault):
    path, state = tmp_path/'decisions.json', tmp_path/'import.json'
    valid = document(ready, media)
    delivery.save_json(path, valid)
    previous = delivery.import_decisions(ready, media, path, state_path=state)['plan']
    original = deepcopy(previous)
    before = state.read_bytes()
    bad = deepcopy(valid)
    if fault == 'bounds': bad['actions'][0]['windows'] = [{'start': 3, 'end': 1}]
    if fault == 'id': bad['actions'][0]['candidate_ids'] = ['UNKNOWN']
    if fault == 'title': bad['actions'][0]['title'] = '  '
    if fault == 'source_hash': bad['source_sha256'] = '0'*64
    if fault == 'package_hash': bad['input_package_sha256'] = '0'*64
    if fault == 'missing_hash': bad.pop('input_package_sha256')
    if fault == 'layout': bad['actions'][0]['suggested_layout'] = 'invented_tracking'
    delivery.save_json(path, bad)
    with pytest.raises((ValueError, ValidationError)):
        delivery.import_decisions(ready, media, path, state_path=state, previous_plan=previous)
    assert state.read_bytes() == before and previous == original


def test_wrong_source_file_and_tampered_journal_block(tmp_path, ready, media):
    path, state = tmp_path/'decisions.json', tmp_path/'import.json'
    delivery.save_json(path, document(ready, media))
    delivery.import_decisions(ready, media, path, state_path=state)
    wrong = tmp_path/'wrong.bin'
    wrong.write_bytes(b'incorrect-source')
    before = state.read_bytes()
    with pytest.raises(ValueError, match='SOURCE_MODIFIED|PROVENANCE'):
        delivery.import_decisions(ready, wrong, path, state_path=state)
    assert state.read_bytes() == before
    corrupt = delivery.load_json(state)
    corrupt['journal'][0]['decisions']['actions'][0]['title'] = 'tampered'
    delivery.save_json(state, corrupt)
    with pytest.raises(ValueError, match='JOURNAL_TAMPERED'):
        delivery.import_decisions(ready, media, path, state_path=state)


def test_interval_recomputes_words_qa_camera_and_subtitle(tmp_path, ready, media, monkeypatch):
    # Stub only additional dependent evidence, after real package audit.
    # This exercises planner behavior, not package validation of those stub rows.
    read = zipfile.ZipFile.read
    def dependent_read(archive, name, *args, **kwargs):
        data = read(archive, name, *args, **kwargs)
        if name == 'editorial/candidate_catalog.json':
            parsed = json.loads(data)
            parsed['candidates'][0]['question_answer_linkage'] = ['Q', 'MISSING']
            return json.dumps(parsed).encode()
        if name == 'editorial/qa_pairs.json':
            return json.dumps([{'question_id': 'Q', 'question_start': 1, 'question_end': 1.5,
                               'answer_start': 1.5, 'answer_end': 3, 'question_answer_complete': True}]).encode()
        if name == 'camera/candidate_camera_plans.json':
            return b'[{"candidate_id":"M1","keyframes":[{"time":1}]}]'
        if name == 'subtitles/subtitle_review_s7.json':
            return b'{"candidates":{"M1":{"approval_state":"APPROVED"}}}'
        if name == 'transcript/relevant_words.jsonl':
            return b'{"word_id":"W","word":"fixture","start":1.6,"end":2,"alignment_verified":true}\n'
        return data
    monkeypatch.setattr(delivery, 'audit_second_curation_package', lambda p: {'bridge_possible': True})
    monkeypatch.setattr(zipfile.ZipFile, 'read', dependent_read)
    path = tmp_path/'decisions.json'
    delivery.save_json(path, document(ready, media))
    plan = delivery.prepare_plan(ready, media, decisions_path=path)
    clip = plan['clips'][0]
    assert clip['words'][0]['start'] == pytest.approx(.1)
    assert clip['words'][0]['alignment_verified'] is True
    assert clip['words'][0]['audio_verified'] is None and not clip['karaoke_allowed']
    assert not clip['camera_recommendations']
    assert clip['subtitle_status'] == 'DRAFT_REQUIRES_LISTENING'
    qa = {q['question_id']: q for q in clip['qa_validation']}
    assert qa['Q']['interval_complete'] is False and qa['Q']['question_answer_complete'] is None
    assert qa['MISSING']['interval_complete'] is None


def test_commercial_and_invalid_commercial_decision():
    assert compile_decisions(decisions(ids=['AD']), catalog(), {'sha256': 'HASH', 'duration': 100}) == []
    with pytest.raises(ValueError, match='interval'):
        compile_decisions(decisions(ids=['AD'], windows=[{'start': 99, 'end': 98}]),
                          catalog(), {'sha256': 'HASH', 'duration': 100})


def test_no_stale_evidence_refs_after_time_edit():
    result = compile_decisions(decisions('expand', windows=[{'start': 50, 'end': 60}]),
                               catalog(), {'sha256': 'HASH', 'duration': 100}, segments=[])
    assert result[0]['evidence_segment_ids'] == []


def test_atomic_commit_failure_preserves_state(tmp_path, ready, media, monkeypatch):
    path, state = tmp_path/'decisions.json', tmp_path/'import.json'
    delivery.save_json(path, document(ready, media))
    delivery.import_decisions(ready, media, path, state_path=state)
    before = state.read_bytes()
    delivery.save_json(path, document(ready, media, title='new'))
    def fail(*args):
        raise OSError('synthetic replace failure')
    monkeypatch.setattr(delivery.os, 'replace', fail)
    with pytest.raises(OSError):
        delivery.import_decisions(ready, media, path, state_path=state)
    assert state.read_bytes() == before
    assert not list(tmp_path.glob('.curator_import_*'))


def test_expanded_interval_cannot_cover_commercial_candidate(tmp_path, ready, media, monkeypatch):
    read = zipfile.ZipFile.read
    def excluded_candidate(archive, name, *args, **kwargs):
        data = read(archive, name, *args, **kwargs)
        if name == 'editorial/candidate_catalog.json':
            parsed = json.loads(data)
            parsed['candidates'][1]['content_type'] = 'advertisement'
            parsed['candidates'][1]['commercial_classification']['eligibility'] = 'excluded'
            return json.dumps(parsed).encode()
        return data
    # Isolate the downstream commercial gate with explicit synthetic catalog.
    monkeypatch.setattr(delivery, 'audit_second_curation_package', lambda p: {'bridge_possible': True})
    monkeypatch.setattr(zipfile.ZipFile, 'read', excluded_candidate)
    path = tmp_path/'decisions.json'
    delivery.save_json(path, document(ready, media, action='expand', windows=[{'start': 1, 'end': 4}]))
    with pytest.raises(ValueError, match='INTERVAL_CONTAINS_COMMERCIAL'):
        delivery.import_decisions(ready, media, path, dry_run=True)


def test_music_hash_preserved_and_change_blocks_replay(tmp_path, ready, media):
    music = tmp_path/'synthetic_music.mp4'
    music.write_bytes(media.read_bytes())
    path, state = tmp_path/'decisions.json', tmp_path/'import.json'
    delivery.save_json(path, document(ready, media))
    first = delivery.import_decisions(ready, media, path, state_path=state, music_path=music, music_gain=.06)
    assert first['plan']['music_sha256'] == delivery.file_sha256(music)
    assert first['plan']['clips'][0]['audio_plan']['listening_verified'] is None
    again = delivery.import_decisions(ready, media, path, state_path=state)
    assert again['replayed'] and again['plan'] == first['plan']
    before = state.read_bytes()
    with music.open('ab') as handle:
        handle.write(b'synthetic change')
    with pytest.raises(ValueError, match='INSTRUMENTAL_MODIFIED'):
        delivery.import_decisions(ready, media, path, state_path=state)
    assert state.read_bytes() == before


def test_new_plan_invalidates_old_canary_approval(tmp_path, ready, media):
    path = tmp_path/'decisions.json'
    delivery.save_json(path, document(ready, media))
    old = delivery.prepare_plan(ready, media)
    new = delivery.import_decisions(ready, media, path, previous_plan=old, dry_run=True)['plan']
    with pytest.raises(ValueError, match='APPROVAL_INVALIDATED'):
        delivery.verify_approval(new, {'batch_authorized': True, 'plan_sha256': old['plan_sha256']}, {})


def test_cli_dry_run_writes_no_state(tmp_path, ready, media, monkeypatch, capsys):
    import sys
    from scripts.dev.curator_s9 import main
    path, state = tmp_path/'decisions.json', tmp_path/'import.json'
    delivery.save_json(path, document(ready, media))
    monkeypatch.setattr(sys, 'argv', ['curator_s9.py', 'import-decisions', '--package', str(ready),
                                    '--source', str(media), '--decisions', str(path),
                                    '--state', str(state), '--dry-run'])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report['dry_run'] and not report['committed'] and not state.exists()
