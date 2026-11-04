"""Offline reference regressions; no media/inference or invented transcript."""
from copy import deepcopy
import json
from pathlib import Path
import zipfile

import pytest

from ldporto.integrity_contracts import build_question_reference_table, audit_question_references
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_v43_handoff import analysis_fixture


def fixture():
    analysis = analysis_fixture()
    analysis.update(json.loads((Path(__file__).parent / 'fixtures' /
                               'joao_gordo_qa_references.json').read_text(encoding='utf-8')))
    return analysis


def test_export_retains_non_answer_questions_and_stable_ids(tmp_path):
    analysis = fixture()
    before = deepcopy(analysis)
    package = build_second_curation_package(analysis)
    assert package['candidates'][0]['question_answer_linkage'] == ['Q_0007', 'Q_0114', 'Q_0115']
    result = build_core_package(analysis, output_dir=tmp_path)
    validation = validate_core_package(result['path'])
    assert validation['status'] == 'valid', validation
    assert validation['question_reference_validation']['status'] == 'resolved'
    with zipfile.ZipFile(result['path']) as archive:
        rows = json.loads(archive.read('editorial/qa_pairs.json'))
        by_id = {r['question_id']: r for r in rows}
        for qid in ('Q_0114', 'Q_0115'):
            assert by_id[qid]['answer_status'] == 'not_expected'
            assert by_id[qid]['question'] is None and by_id[qid]['answer'] is None
            assert by_id[qid]['reference_evidence'][0]['source_collection'] == 'questions_answers'
        assert json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))['workflow']['publication_ready'] is False
    analysis['questions_answers'].reverse()
    reordered = build_second_curation_package(analysis)
    assert set(reordered['candidates'][0]['question_answer_linkage']) == set(package['candidates'][0]['question_answer_linkage'])
    analysis['questions_answers'].reverse()
    assert analysis == before


def test_semantic_filter_keeps_ids_and_diagnostics_can_resolve_references():
    from ldporto.semantic import qa_contract
    analysis = fixture()
    contract = qa_contract(analysis['questions_answers'])
    assert [r['question_id'] for r in contract['question_candidates']] == ['Q_0007']
    assert [r['question_id'] for r in contract['question_diagnostics']] == ['Q_0114', 'Q_0115']
    candidates = [{'candidate_id': 'M1', 'question_answer_linkage': ['Q_0114', 'Q_0115', 'Q_0114']}]
    rows = build_question_reference_table(contract, candidates)
    assert audit_question_references(candidates, rows)['status'] == 'resolved'
    assert candidates[0]['question_answer_linkage'] == ['Q_0114', 'Q_0115', 'Q_0114']


@pytest.mark.parametrize('legacy_package', [False, True])
def test_missing_record_preserves_each_link_with_reason_and_evidence(tmp_path, legacy_package):
    analysis = fixture()
    analysis['main_moments'][0]['question_answer_linkage'] = ['Q_UNKNOWN']
    package = build_second_curation_package(analysis)
    if legacy_package:
        package.pop('question_reference_table')
        package['candidates'][0].pop('question_answer_resolution')
        package['candidates'][0]['question_answer_linkage'] += ['Q_UNKNOWN']
    result = build_core_package(analysis, package=package, output_dir=tmp_path)
    validation = validate_core_package(result['path'])
    assert validation['status'] == 'valid', validation
    assert validation['question_reference_validation']['status'] == 'unresolved'
    assert result['state'] == 'PARTIAL'
    with zipfile.ZipFile(result['path']) as archive:
        rows = json.loads(archive.read('editorial/qa_pairs.json'))
        candidate = json.loads(archive.read('candidates/M1.json'))
        missing = next(r for r in rows if r['question_id'] == 'Q_UNKNOWN')
        assert missing['question'] is None and missing['answer'] is None
        assert missing['reference_reason'] == 'question_record_missing_in_supplied_analysis'
        assert candidate['question_answer_linkage'].count('Q_UNKNOWN') == (2 if legacy_package else 1)
        assert len(missing['reference_evidence']) == (2 if legacy_package else 1)


@pytest.mark.parametrize('mutation', ['missing', 'pointer', 'reason', 'evidence', 'duplicate'])
def test_cross_validator_rejects_orphans_and_invalid_paths(mutation):
    candidates = [{'candidate_id': 'M1', 'question_answer_linkage': ['Q_ABSENT']}]
    rows = build_question_reference_table({}, candidates)
    if mutation == 'missing':
        rows.clear()
    elif mutation == 'pointer':
        candidates[0]['question_answer_resolution'][0]['json_pointer'] = '/42'
    elif mutation == 'reason':
        rows[0]['reference_reason'] = None
    elif mutation == 'evidence':
        rows[0]['reference_evidence'][0]['json_pointer'] = '/question_answer_linkage/42'
    else:
        rows.append(deepcopy(rows[0]))
    assert audit_question_references(candidates, rows)['status'] == 'failed'


def test_archive_validator_rejects_catalog_individual_link_disagreement(tmp_path):
    result = build_core_package(fixture(), output_dir=tmp_path / 'packages')
    staging = tmp_path / 'staging'
    with zipfile.ZipFile(result['path']) as archive:
        # Only our own synthetic, validated package is expanded in this fixture.
        archive.extractall(staging)
    path = staging / 'candidates/M1.json'
    row = json.loads(path.read_text(encoding='utf-8'))
    row['question_answer_linkage'] = ['Q_TAMPERED']
    path.write_text(json.dumps(row), encoding='utf-8')
    errors = validate_core_package(staging)['errors']
    assert 'candidate_file_mismatch:M1' in errors


def test_archive_validator_detects_missing_table_id_with_valid_checksums(tmp_path):
    import hashlib
    result = build_core_package(fixture(), output_dir=tmp_path / 'packages')
    staging = tmp_path / 'staging'
    with zipfile.ZipFile(result['path']) as archive:
        archive.extractall(staging)
    path = staging / 'editorial/qa_pairs.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    path.write_text(json.dumps([r for r in rows if r['question_id'] != 'Q_0115']), encoding='utf-8')
    manifest_path = staging / 'SECOND_CURATION_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entry = next(r for r in manifest['files'] if r['path'] == 'editorial/qa_pairs.json')
    entry.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    validation = validate_core_package(staging)
    assert validation['checksums_valid']
    assert 'qa_ref:missing:M1:Q_0115' in validation['errors']
    assert validation['dangling_references'] > 0
