from copy import deepcopy
from pathlib import Path
import pytest
from ldporto.second_curation_decisions import compile_decisions, ManualJsonProvider


def catalog():
    return {'candidates': [{'candidate_id': 'A', 'start': 0, 'end': 40, 'transcript_literal': 'Uma história.', 'segment_ids': ['S1'], 'content_type': 'editorial_content'},
                           {'candidate_id': 'B', 'start': 40, 'end': 80, 'transcript_literal': 'O desfecho.', 'segment_ids': ['S2'], 'content_type': 'editorial_content'},
                           {'candidate_id': 'AD', 'start': 80, 'end': 100, 'segment_ids': ['S3'], 'content_type': 'advertisement'}]}


def decisions(action='approve', ids=None, **extra):
    return {'schema_version': '4.4.0', 'source_sha256': 'HASH', 'provider': 'manual_json',
            'actions': [{'decision_id': 'D1', 'action': action, 'candidate_ids': ids or ['A'], 'reason': 'Evidência literal.', **extra}]}


def test_promote_merge_split_boundaries_and_commercial_gate():
    metadata = {'sha256': 'HASH', 'duration': 100}
    assert compile_decisions(decisions('promote'), catalog(), metadata)[0]['curation_source'] == 'SECOND_CURATOR'
    merged = compile_decisions(decisions('merge', ['A', 'B']), catalog(), metadata)
    assert merged[0]['start'] == 0 and merged[0]['end'] == 80
    split = compile_decisions(decisions('split', windows=[{'start': 0, 'end': 20}, {'start': 20, 'end': 40}]), catalog(), metadata)
    assert len(split) == 2
    assert compile_decisions(decisions('approve', ['AD']), catalog(), metadata) == []
    with pytest.raises(ValueError):
        compile_decisions(decisions(windows=[{'start': 0, 'end': 101}]), catalog(), metadata)
    with pytest.raises(ValueError):
        compile_decisions(decisions(ids=['MISSING']), catalog(), metadata)


def test_wrong_source_hash_and_ungrounded_evidence_are_rejected():
    with pytest.raises(ValueError):
        compile_decisions(decisions(), catalog(), {'sha256': 'OTHER', 'duration': 100})
    with pytest.raises(ValueError):
        compile_decisions(decisions(evidence_segment_ids=['ABSENT']), catalog(), {'sha256': 'HASH', 'duration': 100})


def test_manual_provider_needs_no_external_api():
    package = {'catalog': catalog(), 'metadata': {'sha256': 'HASH', 'duration': 100}}
    assert ManualJsonProvider(decisions()).curate(package) == decisions()


@pytest.mark.parametrize('preview', [False, True])
def test_promoted_candidate_gets_visuals_without_losing_other_candidates(tmp_path, monkeypatch, preview):
    import zipfile
    import json
    import cv2
    import numpy as np
    from test_v43_handoff import analysis_fixture
    from ldporto.core import file_hash
    from ldporto.second_curation_export import build_core_package, generate_visuals_on_demand, validate_core_package
    if preview:
        from ldporto import second_curation_export
        def render_fixture(source, timeline, metadata, path, *args):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'preview-reference-fixture')
            return {'status':'ok'}
        monkeypatch.setattr(second_curation_export,'render_preview',render_fixture)
    video = tmp_path / 'short.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 180))
    for _ in range(40):
        writer.write(np.full((180, 320, 3), 100, dtype=np.uint8))
    writer.release()
    analysis = analysis_fixture()
    analysis['metadata'].update(sha256=file_hash(video), duration=4)
    analysis['transcript_segments'] = [{'segment_id': 'S1', 'start': 0, 'end': 4, 'text': 'Uma história.', 'speaker': 'SP1'}]
    analysis['main_moments'] = [{**analysis['main_moments'][0], 'moment_id': 'M1', 'ideal_start': 0, 'ideal_end': 2,
                               'core_moment': {'start': 0, 'end': 2}},
                              {**analysis['main_moments'][0], 'moment_id': 'M2', 'ideal_start': 2, 'ideal_end': 4,
                               'core_moment': {'start': 2, 'end': 4}}]
    package = build_core_package(analysis, output_dir=tmp_path / 'packages')
    before = file_hash(package['path'])
    result = generate_visuals_on_demand(package['path'], video, ['M2'], tmp_path / 'on-demand', preview=preview)
    assert file_hash(package['path']) == before
    assert validate_core_package(result['path'])['status'] == 'valid'
    with zipfile.ZipFile(result['path']) as archive:
        catalog = json.loads(archive.read('editorial/candidate_catalog.json'))
        assert len(catalog['candidates']) == 2
        assert next(r for r in catalog['candidates'] if r['candidate_id'] == 'M2')['visual_refs']
        if preview:
            reference=next(r for r in catalog['candidates'] if r['candidate_id']=='M2')['preview_reference']
            assert reference['package'] == Path(result['media_path']).name
            with zipfile.ZipFile(result['media_path']) as media:
                import hashlib
                assert hashlib.sha256(media.read(reference['member'])).hexdigest()==reference['sha256']
