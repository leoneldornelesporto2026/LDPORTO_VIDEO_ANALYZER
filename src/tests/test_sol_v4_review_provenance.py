"""Media binding and replay provenance; small local fixtures, no model execution."""
from copy import deepcopy
from pathlib import Path

import pytest

from ldporto.core import file_hash
from ldporto.review_media import (build_source_media_references, resolve_review_media,
                                 review_player_html, validate_media_references)
from ldporto.build_provenance import (editorial_replay_provenance, analysis_provenance,
                                      validate_editorial_replay)


def fixture(tmp_path):
    source = tmp_path/'original.mp4'
    source.write_bytes(b'synthetic source bytes, not real audiovisual evidence')
    preview = tmp_path/'source_previews'/'C1'/'source_preserve.mp4'
    preview.parent.mkdir(parents=True)
    preview.write_bytes(b'synthetic preview bytes')
    meta = {'sha256': file_hash(source)}
    candidate = {'candidate_id': 'C1', 'start': 100.25, 'end': 140.5}
    manifest = {'source_sha256': meta['sha256'], 'results': [{**candidate,
        'preview_path': preview.relative_to(tmp_path).as_posix(),
        'bytes': preview.stat().st_size, 'sha256': file_hash(preview)}]}
    return source, preview, meta, candidate, manifest


def test_media_bound_to_hash_id_and_exact_interval_not_name_or_position(tmp_path):
    source, preview, meta, c, manifest = fixture(tmp_path)
    refs = build_source_media_references(meta, c, manifest)
    assert validate_media_references(refs, meta, c) == []
    assert resolve_review_media(refs, source)['start'] == 100.25
    assert resolve_review_media(refs, source, kind='audio')['end'] == 140.5
    found = resolve_review_media(refs, kind='preview', preview_root=tmp_path)
    assert found['path'] == preview and found['start'] == 0 and found['end'] == 40.25
    assert refs['original_audio']['kind'] == 'original_video_audio_stream'
    assert refs['preview_approved'] is False and refs['existing_previews'][0]['preview_approved'] is False
    assert str(tmp_path) not in str(refs)
    for field, wrong in [('candidate_id', 'C2'), ('start', 99), ('end', 141)]:
        other = {**c, field: wrong}
        assert build_source_media_references(meta, other, manifest)['existing_previews'] == []
    assert build_source_media_references({'sha256': 'unknown'}, c) is None


@pytest.mark.parametrize('kind', ['audio', 'video', 'preview'])
def test_modified_media_is_rejected_even_with_correct_filename(tmp_path, kind):
    source, preview, meta, c, manifest = fixture(tmp_path)
    refs = build_source_media_references(meta, c, manifest)
    (preview if kind == 'preview' else source).write_bytes(b'changed source')
    with pytest.raises(ValueError):
        resolve_review_media(refs, source, kind, tmp_path)


@pytest.mark.parametrize('path', ['../outside.mp4', '/outside.mp4', 'C:/outside.mp4', 'source_previews/../../x'])
def test_untrusted_preview_path_cannot_escape_media_root(tmp_path, path):
    source, preview, meta, c, manifest = fixture(tmp_path)
    refs = build_source_media_references(meta, c, manifest)
    refs['existing_previews'][0]['locator']['path'] = path
    assert 'invalid_preview_binding' in validate_media_references(refs, meta, c)
    with pytest.raises(ValueError):
        resolve_review_media(refs, source, 'preview', tmp_path)


def test_export_binding_rejects_changed_source_hash_timestamp_or_claimed_approval(tmp_path):
    _, _, meta, c, manifest = fixture(tmp_path)
    refs = build_source_media_references(meta, c, manifest)
    for key, value in [('source_sha256', 'f'*64), ('source_interval', {'start': 0, 'end': 4}),
                       ('preview_approved', True)]:
        bad = {**refs, key: value}
        assert validate_media_references(bad, meta, c)
    bad = deepcopy(refs)
    bad['existing_previews'][0]['preview_approved'] = True
    assert validate_media_references(bad, meta, c)


def test_local_player_seeks_correct_time_preserves_pending_state_and_escapes_labels(tmp_path):
    source, _, meta, c, manifest = fixture(tmp_path)
    refs = build_source_media_references(meta, c, manifest)
    resolved = resolve_review_media(refs, source)
    resolved['candidate_id'] = '<script>evil()</script>'
    document = review_player_html(resolved)
    assert '#t=100.25,140.5' in document and 'm.currentTime=t.start' in document
    assert 'timeupdate' in document and 'm.pause()' in document
    assert '<script>evil()' not in document and 'autoplay' not in document
    assert 'não aprova' in document and '<video ' in document
    assert '<audio ' in review_player_html({**resolved, 'kind': 'audio'})


def test_replay_code_inputs_and_checkpoints_are_hashed_without_new_inference_claim(tmp_path):
    source, _, meta, _, _ = fixture(tmp_path)
    analysis = {'metadata': meta, 'run_manifest': {'analyzer_build': 'OLD', 'code_fingerprint': 'OLD'}}
    replay = editorial_replay_provenance(analysis, {'01.json': source}, {'analysis.json': source},
        ['editorial_potential'], ['editorial_potential', 'second_curation_export'])
    assert replay['reused_checkpoints']['01.json']['sha256'] == meta['sha256']
    assert replay['replay_code']['review_media.py']['sha256'] == file_hash(
        Path(__file__).parents[1]/'ldporto'/'review_media.py')
    identity = analysis_provenance(analysis)
    assert identity['build_mismatch'] is True  # Never hidden by the replay block.
    assert validate_editorial_replay(replay, meta['sha256'], identity) == []
    assert replay['new_model_calls'] == 0 and not replay['full_pipeline_execution_attested']
    for key in ('new_audiovisual_inference', 'full_pipeline_execution_attested', 'publication_ready'):
        assert validate_editorial_replay({**replay, key: True}, meta['sha256'], identity)
    with pytest.raises(ValueError, match='non_editorial_replay_stage'):
        editorial_replay_provenance(analysis, {}, {}, [], ['YOLO'])


def test_replay_hash_or_identity_disagreement_is_not_accepted(tmp_path):
    source, _, meta, _, _ = fixture(tmp_path)
    analysis = {'metadata': meta}
    replay = editorial_replay_provenance(analysis, {'01.json': source}, {'analysis.json': source}, [],
                                          ['second_curation_export'])
    identity = analysis_provenance(analysis)
    bad = deepcopy(replay)
    bad['replay_exporter']['code_fingerprint'] = 'forged'
    assert validate_editorial_replay(bad, meta['sha256'], identity)
    bad = deepcopy(replay)
    bad['reused_artifacts']['analysis.json']['sha256'] = 'bad'
    assert validate_editorial_replay(bad, meta['sha256'], identity)


@pytest.mark.parametrize('change', ['media_timestamp', 'preview_approval', 'replay_inference'])
def test_export_rejects_semantic_binding_tamper_even_with_fresh_member_hashes(tmp_path, change):
    from test_stage06_report_coherence import fixture as analysis_fixture
    from test_s2_pipeline_integrity import _tamper_with_fresh_hashes
    from ldporto.second_curation_export import build_core_package
    source, _, meta, _, _ = fixture(tmp_path)
    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = meta['sha256']
    analysis['editorial_replay_provenance'] = editorial_replay_provenance(analysis,
        {'01.json': source}, {'analysis.json': source}, [], ['second_curation_export'])
    result = build_core_package(analysis, output_dir=tmp_path/'package',
                                cfg={'second_curation_visual_candidate_limit': 0})
    if change == 'replay_inference':
        member = 'provenance/editorial_replay.json'
        mutate = lambda data: data.update(new_audiovisual_inference=True)
    else:
        member = 'editorial/candidate_catalog.json'
        def mutate(data):
            refs = data['candidates'][0]['source_media_references']
            if change == 'media_timestamp':
                refs['source_interval']['start'] += 1
            else:
                refs['preview_approved'] = True
    checked = _tamper_with_fresh_hashes(result['path'], tmp_path/'tampered.zip', member, mutate)
    assert checked['status'] == 'failed' and checked['checksums_valid'] is True
