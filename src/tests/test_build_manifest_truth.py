import json
import logging
import zipfile
from copy import deepcopy

import pytest

from ldporto.build_provenance import analysis_provenance, exporter_identity
from ldporto.core import Context, file_hash, ok, read_json, write_json
from ldporto.reports import _run_manifest
from ldporto.run_status import build_run_manifest
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_v43_handoff import analysis_fixture


@pytest.mark.parametrize('legacy', [False, True])
def test_export_does_not_relabel_old_analysis(tmp_path, legacy):
    analysis = analysis_fixture()
    analysis['analysis_status'] = 'complete'
    analysis['metadata']['analyzer_version'] = '4.3.0'
    analysis['run_manifest'] = {'run_id': 'historical-id', 'analyzer_build': 'OLD-S4',
                                'code_fingerprint': 'historical-source-hash'} if not legacy else {}
    before = deepcopy(analysis)
    result = build_core_package(analysis, output_dir=tmp_path)
    assert analysis == before
    assert validate_core_package(result['path'])['status'] == 'valid'
    with zipfile.ZipFile(result['path']) as archive:
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        brief = json.loads(archive.read('SECOND_CURATOR_BRIEF.json'))
        summary = json.loads(archive.read('summary/analysis_summary.json'))
        gate = json.loads(archive.read('summary/final_quality_gate.json'))
        assert manifest['analyzer_version'] == brief['analyzer_version'] == summary['analyzer_version'] == '4.3.0'
        identity = manifest['build_provenance']
        assert identity['execution_complete'] is not True
        assert manifest['analysis_status'] == summary['analysis_status'] == 'partial'
        assert gate['publication_ready'] is False and gate['preview_approved'] is False
        assert manifest['second_curation_schema_version'] == '3.1'
        if legacy:
            assert manifest['analyzer_build'] is None
            assert manifest['code_fingerprint'] is None
            assert identity['build_mismatch'] is None
        else:
            assert manifest['run_id'] == 'historical-id'
            assert manifest['analyzer_build'] == brief['analyzer_build'] == 'OLD-S4'
            assert manifest['code_fingerprint'] == 'historical-source-hash'
            assert identity['build_mismatch'] is True
            assert manifest['analysis_status'] == summary['analysis_status'] == 'partial'


def test_same_label_different_sources_and_mixed_replay_are_detectable():
    current = exporter_identity()
    stages = {'04_transcription': {'status': 'ok', 'key': 'old-key', 'artifact_snapshot_reused': True},
              '16_understanding': {'status': 'ok', 'execution_provenance': {
                  'origin': 'executed', 'analyzer_build': current['analyzer_build'],
                  'code_fingerprint': current['code_fingerprint']}}}
    manifest = build_run_manifest({'sha256': 'original-source', 'analyzer_build': current['analyzer_build'],
                                   'code_fingerprint': 'older-code'}, stages, [], previous={'run_id': 'retained'})
    assert manifest['run_id'] == 'retained'
    assert manifest['code_fingerprint'] == 'older-code'
    assert manifest['analysis_status'] == 'partial'
    identity = manifest['build_provenance']
    assert identity['execution_complete'] is False
    assert 'analysis_code_differs_from_exporter' in identity['mismatch_reasons']
    assert identity['stages']['04_transcription']['origin'] == 'snapshot'
    assert identity['stages']['04_transcription']['code_fingerprint'] is None
    assert identity['stages']['16_understanding']['origin'] == 'executed'


def test_report_reads_matching_checkpoint_without_mutation_or_cache_invalidation(tmp_path):
    ctx = Context(tmp_path / 'unused.mp4', tmp_path, {'strict': False}, 'source', logging.getLogger(__name__))
    calls = []
    def run():
        calls.append(1)
        return ok({'synthetic': True})
    ctx.step('01_metadata', {}, run, code_files=['__init__.py'])
    checkpoint = ctx.cache / '01_metadata.json'
    checksum = file_hash(checkpoint)
    analysis = {'metadata': {'sha256': 'source'}, 'stage_status': deepcopy(ctx.states),
                'run_manifest': {'run_id': 'keep', 'analyzer_build': 'OLD-S4', 'code_fingerprint': 'original'}}
    first = _run_manifest(analysis, ctx)
    identity = first['build_provenance']['stages']['01_metadata']
    assert identity['checkpoint_sha256'] == checksum
    assert identity['origin'] == 'executed'
    assert identity['code_fingerprint'] is None
    assert first['run_id'] == 'keep' and first['code_fingerprint'] == 'original'
    ctx.step('01_metadata', {}, run, code_files=['__init__.py'])
    assert len(calls) == 1 and file_hash(checkpoint) == checksum
    cached = _run_manifest(analysis, ctx)
    assert cached['build_provenance']['stages']['01_metadata']['origin'] == 'cache'
    write_json(checkpoint, {**read_json(checkpoint), 'key': 'unrelated'})
    assert _run_manifest(analysis, ctx)['build_provenance']['stages']['01_metadata']['checkpoint_sha256'] is None


def test_report_schema_or_ok_status_is_not_execution_proof():
    manifest = build_run_manifest({}, {'16_understanding': {'status': 'ok'}}, [])
    assert manifest['build_provenance']['execution_complete'] is None
    assert manifest['build_provenance']['completion_scope'] == 'stage_status_only'
    assert manifest['code_fingerprint'] is None
    assert manifest['analysis_status'] == 'partial'
    assert manifest['stage_status_summary'] == 'complete'
    identity = analysis_provenance({'run_manifest': manifest})
    assert identity['stages']['16_understanding']['checkpoint_key'] is None


def test_s4_label_with_new_contracts_is_not_full_execution_evidence():
    from ldporto import __build__
    manifest = build_run_manifest({'analyzer_build': __build__, 'schema_version': '2.0'},
                                  {'16_understanding': {'status': 'ok', 'output_version': '3.1'}}, [])
    assert manifest['analyzer_build'] == 'R4.9-S4-TRACKING-FACIAL'
    assert manifest['analysis_status'] == 'partial'
    assert manifest['build_provenance']['build_mismatch'] is None
    assert manifest['build_provenance']['execution_complete'] is None


def test_export_pre_migration_package_without_schema_or_optional_fields(tmp_path):
    from ldporto.second_curation import build_second_curation_package
    analysis = analysis_fixture()
    analysis['metadata'].pop('analyzer_version', None)
    analysis['metadata']['run_id'] = 'metadata-run-id'
    package = build_second_curation_package(analysis)
    package.pop('schema_version')
    result = build_core_package(analysis, output_dir=tmp_path, package=package)
    assert validate_core_package(result['path'])['status'] == 'valid'
    with zipfile.ZipFile(result['path']) as archive:
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        assert manifest['second_curation_schema_version'] is None
        assert manifest['analyzer_version'] is None
        assert manifest['code_fingerprint'] is None
        assert manifest['run_id'] == 'metadata-run-id'


def test_real_offline_replay_preserves_original_identity_and_reports_mixed_origin(tmp_path):
    from ldporto.config import load_config
    from ldporto.replay import replay_analysis
    from test_v43_runtime import replay_fixture
    folder = replay_fixture(tmp_path)
    summary = read_json(folder / 'analysis_summary.json')
    summary['stage_status']['04_transcription'] = {'status': 'ok', 'key': 'upstream-checkpoint'}
    summary['run_manifest'] = {'run_id': 'original-run', 'analyzer_build': 'OLD-S4',
                              'code_fingerprint': 'old-source-fingerprint'}
    write_json(folder / 'analysis_summary.json', summary)
    cfg = load_config()
    cfg['camera_director']['enabled'] = False
    cfg['preview']['enabled'] = False
    cfg['vision']['enabled'] = False
    cfg['diarization']['enabled'] = False
    cfg['export']['second_curation_output_dir'] = str(tmp_path / 'packages')
    output, analysis = replay_analysis(folder, cfg, 'commercial', tmp_path / 'output')
    manifest = read_json(output / 'manifest.json')
    run = read_json(output / 'run_manifest.json')
    assert run['run_id'] == manifest['run_id'] == 'original-run'
    assert run['code_fingerprint'] == manifest['code_fingerprint'] == 'old-source-fingerprint'
    assert run['analyzer_build'] == manifest['analyzer_build'] == 'OLD-S4'
    assert run['build_provenance']['build_mismatch'] is True
    assert run['analysis_status'] == manifest['analysis_status'] == 'partial'
    origins = run['build_provenance']['stages']
    assert any(row['origin'] == 'snapshot' for row in origins.values())
    assert origins['20_handoff']['origin'] == 'executed'
    assert origins['20_handoff']['code_fingerprint']
    assert not analysis['replay_provenance']['asr_rerun']
    assert not analysis['replay_provenance']['vision_rerun']
