"""Offline consumers of refined dialogue and provisional curator evidence."""
from copy import deepcopy
import json
from pathlib import Path

from ldporto.core import file_hash, write_json
from ldporto.pipeline import _dialogue_evidence
from ldporto.second_curation_export import build_core_package, validate_core_package


def test_refined_dialogue_contract_prefers_canonical_rows_without_mutating_semantic():
    legacy = {'questions_answers': [{'question_id': 'Q1', 'answer_status': 'unresolved'}],
              'question_candidates': [{'question_id': 'Q1'}], 'question_answer_pairs': [],
              'qa_metrics': {'answered': 0}}
    refined = {'questions_answers': [{'question_id': 'Q1', 'answer_status': 'linked_candidate',
                                      'needs_review': True}],
               'question_candidates': [{'question_id': 'Q1'}],
               'question_answer_pairs': [{'question_id': 'Q1', 'answer_status': 'linked_candidate'}],
               'qa_metrics': {'answered': 0, 'linked_candidates': 1}}
    before = deepcopy(legacy)
    result = _dialogue_evidence(refined, legacy)
    assert result['questions_answers'] == refined['questions_answers']
    assert result['question_answer_pairs'] == refined['question_answer_pairs']
    assert result['qa_metrics']['answered'] == 0  # A candidate answer is not confirmed.
    assert legacy == before
    assert _dialogue_evidence({}, legacy)['questions_answers'] == legacy['questions_answers']


def test_gui_distinguishes_human_triage_from_zero_automatic_shortlist():
    import app
    report = {'shortlist_count': 0, 'human_review_summary': {'human_review_queue_count': 77,
        'provisional_human_review_count': 77, 'recorded_local_gate_counts': {
            'missing_required_score:hook': 3, 'duration_outside_target_without_exception': 2}}}
    text = app.editorial_triage_text(report)
    assert 'Triagem humana: 77' in text and 'Shortlist automatica: 0' in text
    assert 'hook nao medido: 3' in text and 'nao aprova' in text
    assert app.editorial_triage_text({'shortlist_count': 0}) is None
    report['human_review_summary']['human_review_queue_count'] = True
    assert 'Triagem humana: nao medido' in app.editorial_triage_text(report)


def test_new_package_has_one_actionable_queue_and_legacy_queue_still_validates(tmp_path):
    from test_stage06_report_coherence import fixture
    from ldporto.integrity_contracts import human_review_queue
    analysis = fixture()
    before = deepcopy(analysis)
    result = build_core_package(analysis, source=None, output_dir=tmp_path/'new',
        cfg={'second_curation_visual_candidate_limit': 0, 'include_candidate_previews': False},
        directory_only=True)
    folder = Path(result['path'])
    queue = json.loads((folder/'editorial/human_review_queue.json').read_text())
    assert queue['schema_version'] == '1.2' and queue['publication_ready'] is False
    assert validate_core_package(folder)['status'] == 'valid'
    assert analysis == before
    # Reproduce the old physical contract in this synthetic derived copy only.
    candidates = json.loads((folder/'editorial/candidate_catalog.json').read_text())['candidates']
    write_json(folder/'editorial/human_review_queue.json', human_review_queue(candidates, schema_version='1.0'))
    manifest_path = folder/'SECOND_CURATION_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    for row in manifest['files']:
        if row['path'] == 'editorial/human_review_queue.json':
            row.update(bytes=(folder/row['path']).stat().st_size, sha256=file_hash(folder/row['path']))
    manifest['uncompressed_bytes'] = sum(row['bytes'] for row in manifest['files'])
    write_json(manifest_path, manifest)
    assert validate_core_package(folder)['status'] == 'valid'


def test_unknown_queue_version_is_not_accepted_as_legacy(tmp_path):
    from test_stage06_report_coherence import fixture
    result = build_core_package(fixture(), source=None, output_dir=tmp_path/'unknown',
        cfg={'second_curation_visual_candidate_limit': 0}, directory_only=True)
    folder = Path(result['path'])
    queue_path = folder/'editorial/human_review_queue.json'
    queue = json.loads(queue_path.read_text()); queue['schema_version'] = '999'
    write_json(queue_path, queue)
    manifest_path = folder/'SECOND_CURATION_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    for row in manifest['files']:
        if row['path'] == 'editorial/human_review_queue.json':
            row.update(bytes=queue_path.stat().st_size, sha256=file_hash(queue_path))
    manifest['uncompressed_bytes'] = sum(row['bytes'] for row in manifest['files'])
    write_json(manifest_path, manifest)
    validation = validate_core_package(folder)
    assert validation['status'] != 'valid' and 'unsupported_human_review_queue_schema' in validation['errors']
