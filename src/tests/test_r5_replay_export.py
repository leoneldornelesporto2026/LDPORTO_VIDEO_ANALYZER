"""Real small filesystem replays, no models or audiovisual decoding."""
from copy import deepcopy
import json
from pathlib import Path
import zipfile

import pytest

from ldporto.core import file_hash, write_json
from ldporto.narrative_handoff import ARTIFACTS
from ldporto.narrative_replay import replay_narrative_analysis, narrative_replay_plan
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_stage06_report_coherence import fixture
from test_s2_pipeline_integrity import _tamper_with_fresh_hashes


def snapshot(tmp_path):
    from ldporto.understanding import build_story_arcs, _validate_story_arcs_contract
    from ldporto.second_curation import build_second_curation_package
    a = fixture()
    a['metadata'].update(schema_version='2.0', analyzer_version='4.4.0', sha256='a'*64)
    a['story_arcs'], _ = _validate_story_arcs_contract(build_story_arcs(
        {'segments': a['transcript_segments']}, a['topics'], a.get('questions_answers')), a['transcript_segments'])
    a['camera_plan'] = {'selected_global_path': [{'planner_id': 'SYNTHETIC_PLAN',
        'start': 0, 'end': a['metadata']['duration']}]}
    a['second_curation_package'] = build_second_curation_package(a)
    a['social_output'] = {'stories': [], 'title_suggestions': [], 'publication_ready': False}
    folder = tmp_path/'snapshot'
    folder.mkdir()
    write_json(folder/'analysis.json', a)
    for key, value in a.items():
        if isinstance(value, list) or key in {'second_curation_package', 'camera_plan'}:
            write_json(folder/(key + '.json'), value)
    write_json(folder/'stories_manifest.json', a['social_output'])
    checkpoint = folder/'cache'/('a'*16)/'04_transcription.json'
    checkpoint.parent.mkdir(parents=True)
    write_json(checkpoint, {'scope': 'synthetic persisted evidence only', 'segments': a['transcript_segments']})
    checksums = {p.name: file_hash(p) for p in folder.glob('*.json')}
    write_json(folder/'manifest.json', {'artifact_checksums': checksums})
    return folder, a


def test_real_filesystem_editorial_replay_is_cached_and_preserves_inputs(tmp_path):
    folder, a = snapshot(tmp_path)
    before = {p.name: file_hash(p) for p in folder.glob('*.json')}
    first = replay_narrative_analysis(folder, tmp_path/'derived')
    second = replay_narrative_analysis(folder, tmp_path/'derived')
    assert first['new_model_calls'] == 0 and second['cache_hit'] is True
    assert first['package_sha256'] == second['package_sha256']
    assert first['canonical_qa_modified'] is False and first['original_candidates_modified'] is False
    assert {p.name: file_hash(p) for p in folder.glob('*.json')} == before
    assert validate_core_package(Path(first['result']['path']))['status'] == 'valid'
    with zipfile.ZipFile(first['result']['path']) as z:
        names = set(z.namelist())
        assert set(ARTIFACTS.values()) <= names
        assert {'SECOND_CURATION_NARRATIVE_HANDOFF.json', 'CODEX_ANALYZER_REVIEW.md',
            'SECOND_CURATION_HANDOFF_VALIDATION.json', 'README_SECOND_CURATION.md',
            'schemas/narrative_handoff.schema.json'} <= names
        assert json.loads(z.read('social/stories_candidates.json')) == []
        assert json.loads(z.read('social/title_suggestions.json')) == []
        assert json.loads(z.read('SECOND_CURATION_NARRATIVE_HANDOFF.json'))['publication_ready'] is False
        catalog = json.loads(z.read('editorial/candidate_catalog.json'))['candidates']
        assert catalog[0]['evidence_references']['planner_ids'] == ['SYNTHETIC_PLAN']
        assert catalog[0]['eligible_for_human_review'] == a['second_curation_package']['candidates'][0]['eligible_for_human_review']


def test_replay_after_failure_reuses_only_hash_verified_bundle(tmp_path, monkeypatch):
    folder, _ = snapshot(tmp_path)
    import ldporto.second_curation_export as exporter
    original = exporter.build_core_package
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic interruption before export')
    monkeypatch.setattr(exporter, 'build_core_package', fail)
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        replay_narrative_analysis(folder, tmp_path/'derived')
    assert json.loads((tmp_path/'derived/replay_state.json').read_text())['status'] == 'bundle_validated'
    monkeypatch.setattr(exporter, 'build_core_package', original)
    result = replay_narrative_analysis(folder, tmp_path/'derived')
    assert result['cache_hit'] is True and result['validation']['status'] == 'valid'


def test_changed_input_rejected_before_reusing_completed_replay(tmp_path):
    folder, _ = snapshot(tmp_path)
    replay_narrative_analysis(folder, tmp_path/'derived')
    path = folder/'transcript_segments.json'
    rows = json.loads(path.read_text())
    rows[0]['text'] = 'changed canonical source'
    write_json(path, rows)
    with pytest.raises(ValueError, match='checksum mismatch'):
        replay_narrative_analysis(folder, tmp_path/'derived')


def test_missing_persisted_planner_reference_blocks_replay_without_changing_gates(tmp_path):
    folder, _ = snapshot(tmp_path)
    (folder/'camera_plan.json').unlink()  # Only the temporary synthetic fixture.
    # This fixture also embeds collections; remove that copy to model a compact snapshot.
    document = json.loads((folder/'analysis.json').read_text())
    document.pop('camera_plan')
    write_json(folder/'analysis.json', document)
    manifest = json.loads((folder/'manifest.json').read_text())
    manifest['artifact_checksums']['analysis.json'] = file_hash(folder/'analysis.json')
    write_json(folder/'manifest.json', manifest)
    with pytest.raises(ValueError, match='replay_source_references_unresolved'):
        replay_narrative_analysis(folder, tmp_path/'derived')


@pytest.mark.parametrize('mode', ['editorial', 'targeted_repair', 'full'])
def test_mode_plans_never_automatically_execute_models(mode):
    plan = narrative_replay_plan(mode)
    assert plan['automatic_full_processing'] is False and plan['model_calls'] == 0
    assert plan['publication_ready'] is False


def test_broken_narrative_reference_rejected_with_fresh_manifest_hashes(tmp_path):
    folder, _ = snapshot(tmp_path)
    result = replay_narrative_analysis(folder, tmp_path/'derived')
    def mutate(data):
        data['artifact_refs']['units'] = 'editorial/NONEXISTENT.json'
    checked = _tamper_with_fresh_hashes(result['result']['path'], tmp_path/'bad.zip',
                                      'SECOND_CURATION_NARRATIVE_HANDOFF.json', mutate)
    assert checked['status'] == 'failed' and checked['checksums_valid'] is True
    assert any('narrative:' in error for error in checked['errors'])


@pytest.mark.parametrize('name,expected', [('ponte', 1), ('navio', 0)])
def test_cross_section_entity_retrieval_requires_literal_source_and_never_claims_causality(name, expected):
    from test_r5_narrative_handoff import narrative_fixture
    from ldporto.narrative_handoff import build_narrative_handoff, validate_narrative_handoff
    analysis, candidates = narrative_fixture()
    analysis['transcript_segments'][-1]['text'] = 'Mais adiante, a ponte recebeu uma inspeção.'
    analysis['story_arcs'] = [{'story_arc_id': 'ARC_' + sid, 'kind': 'discussion_segment',
        'evidence_segment_ids': [sid]} for sid in ('S0', 'S4')]
    analysis['program_sections'] = [{'section_id': 'SECTION_' + sid, 'evidence_segment_ids': [sid]}
                                    for sid in ('S0', 'S4')]
    analysis['entities'] = [{'name': name, 'type': 'object', 'evidence_segment_ids': ['S0', 'S4']}]
    bundle = build_narrative_handoff(analysis, candidates)
    assert validate_narrative_handoff(bundle, analysis['transcript_segments'], candidates, analysis['metadata'])['status'] == 'valid'
    edges = bundle['artifacts'][ARTIFACTS['graph']]['edges']
    retrieved = [e for e in edges if e['relation'] == 'related_context_candidate']
    assert len(retrieved) == expected
    assert all(e['evidence_status'] == 'retrieval_only_no_causality_or_continuity_confirmation' for e in retrieved)
    assert not any(e['relation'] == 'causes' for e in edges)
