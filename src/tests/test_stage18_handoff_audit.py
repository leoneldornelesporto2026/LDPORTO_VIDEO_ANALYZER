"""Offline synthetic contract tests plus read-only historical package audit."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from ldporto.editorial_handoff_audit import AUDIT_PATH, audit_handoff
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_v43_handoff import analysis_fixture


def test_self_contained_report_context_and_versions(tmp_path):
    analysis = analysis_fixture()
    before = deepcopy(analysis)
    result = build_core_package(analysis, output_dir=tmp_path)
    validation = validate_core_package(result['path'])
    assert validation['status'] == 'valid', validation
    with zipfile.ZipFile(result['path']) as archive:
        report = json.loads(archive.read(AUDIT_PATH))
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        candidate = json.loads(archive.read('candidates/M1.json'))
        assert report == validation['audit_report']
        assert report['coverage_score'] == 1 and report['references_ready']
        assert manifest['audit_report_ref'] == AUDIT_PATH
        assert 'build_provenance' in manifest and 'second_curation_schema_version' in manifest
        assert candidate['context_before'][0]['segment_id'] == 'S0'
        assert candidate['context_after'][0]['segment_id'] == 'S2'
        assert candidate['person_id'] is None and report['publication_ready'] is False
        assert not any(Path(n).suffix in {'.wav', '.mp4'} for n in archive.namelist())
    assert analysis == before


@pytest.mark.parametrize('field,value', [('primary_topic_id', 'T_UNKNOWN'),
                                        ('alternate_ref', 'M_UNKNOWN'),
                                        ('alternate_of', 'M_UNKNOWN')])
def test_unresolved_links_are_exported_and_block_editorial_ready(tmp_path, field, value):
    analysis = analysis_fixture()
    package = build_second_curation_package(analysis)
    package['candidates'][0][field] = value
    result = build_core_package(analysis, package=package, output_dir=tmp_path)
    validation = validate_core_package(result['path'])
    assert validation['status'] == 'valid', validation
    assert result['state'] == 'PARTIAL'
    assert not validation['readiness']['editorial_ready']
    report = validation['audit_report']
    assert not report['references_ready'] and report['coverage_score'] < 1
    assert any(r['id'] == value for r in report['unresolved'])
    with zipfile.ZipFile(result['path']) as archive:
        assert json.loads(archive.read('editorial/default_shortlist.json'))['candidate_ids'] == []


def test_missing_and_boundary_context_distinguished():
    analysis = analysis_fixture()
    package = build_second_curation_package(analysis)
    candidate = package['candidates'][0]
    candidate['context_before'] = []
    candidate['segment_ids'] = []
    report = audit_handoff([candidate], {**analysis, 'qa_pairs': package['question_reference_table']})
    assert not report['references_ready']
    assert {r['field'] for r in report['missing']} == {'context_before', 'segment_ids'}
    candidate['start'] = 0
    report = audit_handoff([candidate], {**analysis, 'qa_pairs': []})
    assert next(r for r in report['candidates'][0]['checks'] if r['field'] == 'context_before')['status'] == 'not_applicable'


@pytest.mark.parametrize('mutation', ['topic', 'context', 'audit', 'entrypoint', 'missing_visual'])
def test_rehashed_tampering_is_rejected(tmp_path, mutation):
    result = build_core_package(analysis_fixture(), output_dir=tmp_path / 'packages')
    with zipfile.ZipFile(result['path']) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    if mutation in {'topic', 'context', 'missing_visual'}:
        catalog = json.loads(members['editorial/candidate_catalog.json'])
        row = catalog['candidates'][0]
        if mutation == 'topic':
            row['primary_topic_id'] = 'ABSENT'
        elif mutation == 'context':
            row['context_before'][0]['text'] = 'synthetic tamper'
        else:
            row['visual_refs'] = ['visuals/M1/contact_sheet.jpg']
        members['editorial/candidate_catalog.json'] = json.dumps(catalog).encode()
        members['candidates/M1.json'] = json.dumps(row).encode()
    elif mutation == 'audit':
        report = json.loads(members[AUDIT_PATH])
        report['coverage_score'] = .125
        members[AUDIT_PATH] = json.dumps(report).encode()
    else:
        index = json.loads(members['CURATION_INDEX.json'])
        index['candidate_catalog_ref'] = 'editorial/ABSENT.json'
        members['CURATION_INDEX.json'] = json.dumps(index).encode()
    manifest = json.loads(members['SECOND_CURATION_MANIFEST.json'])
    for entry in manifest['files']:
        data = members[entry['path']]
        entry.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    members['SECOND_CURATION_MANIFEST.json'] = json.dumps(manifest).encode()
    corrupted = tmp_path / 'rehash.zip'
    with zipfile.ZipFile(corrupted, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    validation = validate_core_package(corrupted)
    assert validation['checksums_valid']
    assert validation['status'] == 'failed'
    expected = ('file_ref:' if mutation in {'entrypoint', 'missing_visual'} else 'handoff_audit:report_disagreement')
    assert any(e.startswith(expected) for e in validation['errors'])


def test_real_historical_fixture_hashes_links_and_contact_sheets():
    import cv2
    import numpy as np
    path = Path(__file__).resolve().parents[2] / 'automacao/evidencias/SECOND_CURATION_READY.zip'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '8339e90f41cce13f93bc61cc6417cecc1058ad37df272d194d7f62060d860349'
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        assert manifest['analyzer_build'] == 'R4.9-S4-TRACKING-FACIAL'
        assert archive.testzip() is None
        assert {r['path'] for r in manifest['files']} == set(archive.namelist()) - {'SECOND_CURATION_MANIFEST.json'}
        for entry in manifest['files']:
            data = archive.read(entry['path'])
            assert len(data) == entry['bytes']
            assert hashlib.sha256(data).hexdigest() == entry['sha256']
        candidates = json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
        visuals = set()
        for candidate in candidates:
            for ref in candidate.get('file_refs', []) + candidate.get('visual_refs', []):
                assert ref in archive.namelist()
            for ref in candidate.get('visual_refs', []):
                image = cv2.imdecode(np.frombuffer(archive.read(ref), np.uint8), cv2.IMREAD_COLOR)
                assert image is not None and image.size > 0
                visuals.add(ref)
        assert len(visuals) == 12
    validation = validate_core_package(path)
    # Historical READY is not accepted as current-contract certification.
    assert validation['checksums_valid'] and validation['status'] == 'failed'
    assert validation['audit_report']['candidate_count'] == 55
    assert validation['audit_report']['unresolved']
    assert any(e.startswith('qa_ref:missing:') for e in validation['errors'])
