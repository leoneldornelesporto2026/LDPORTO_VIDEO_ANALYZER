"""Offline producer/consumer receipts and interruption fixtures; no inference."""
from copy import deepcopy
import logging
from pathlib import Path

import pytest

from ldporto.build_provenance import ProvenanceContext
from ldporto.core import Context, digest, file_hash, ok, read_json, write_json
from ldporto.execution_receipts import (snapshot_json, verify_receipt, receipt_digest,
    finalize_report_receipt, verify_report_receipt, dependency_snapshots)
from test_build_manifest_truth import full_execution


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    source = tmp_path / 'synthetic.bin'
    source.write_bytes(b'fixture, no raw media')
    monkeypatch.setattr('ldporto.core.versions', lambda: {})
    monkeypatch.setattr('ldporto.runtime_metrics.resource_snapshot', lambda: {})
    result = ProvenanceContext(source, tmp_path / 'run', {'strict': False}, file_hash(source), logging.getLogger('receipt65'))
    result.progress = lambda *a, **k: None
    return result


@pytest.mark.parametrize('status', ['ok', 'partial', 'skipped', 'failed', 'unavailable'])
def test_real_return_status_and_cache_mode(ctx, status):
    ctx.step('synthetic', {}, lambda: ok({'score': None}, status), code_files=['__init__.py'])
    path = ctx.cache / 'synthetic.json'
    record = read_json(path)
    receipt = record['execution_receipt']
    assert receipt['status'] == status == ctx.states['synthetic']['status']
    assert receipt['stage_id'] == 'synthetic' and receipt['schema_version'] == '2.0'
    assert record['data']['score'] is None
    assert verify_receipt('synthetic', record) == ('verified' if status == 'ok' else 'verified_' + status)
    assert verify_receipt('different_id', record) == 'corrupted'
    if status in {'ok', 'partial', 'skipped'}:
        before = file_hash(path)
        ctx.step('synthetic', {}, lambda: pytest.fail('cache must not call producer'), code_files=['__init__.py'])
        assert ctx.stage_metrics['synthetic']['execution_mode'] == 'cached'
        assert file_hash(path) == before
    assert receipt['trust_scope'] == 'local_producer_consistency_not_independent_signature'


@pytest.mark.parametrize('failure', [OSError, KeyboardInterrupt])
def test_disk_error_or_power_loss_does_not_expose_completion(ctx, monkeypatch, failure):
    import ldporto.core as core
    original = core.write_json
    def failed_write(path, value):
        if Path(path).name == 'synthetic.json':
            raise failure('synthetic write interruption')
        return original(path, value)
    monkeypatch.setattr(core, 'write_json', failed_write)
    with pytest.raises(failure):
        ctx.step('synthetic', {}, lambda: ok({'complete': True}), code_files=['__init__.py'])
    assert 'synthetic' not in ctx.states
    assert not (ctx.cache / 'synthetic.json').exists()


def test_atomic_replace_failure_preserves_previous_bytes(tmp_path, monkeypatch):
    path = tmp_path / 'checkpoint.json'
    write_json(path, {'old': True})
    before = path.read_bytes()
    def denied(*args):
        raise OSError('synthetic disk error')
    monkeypatch.setattr(Path, 'replace', denied)
    with pytest.raises(OSError):
        write_json(path, {'new': True})
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('field', ['data', 'stage_id', 'status', 'config_fingerprint', 'module_fingerprint', 'cache_manifest'])
def test_tampered_record_is_not_authenticated(ctx, field):
    ctx.step('synthetic', {}, lambda: ok({'value': 1}), code_files=['__init__.py'])
    record = read_json(ctx.cache / 'synthetic.json')
    if field == 'data':
        record['data']['value'] = 999
    elif field == 'cache_manifest':
        record['cache_manifest']['input'] = 'other_source'
    else:
        record['execution_receipt'][field] = 'tampered'
    assert verify_receipt('synthetic', record) == 'corrupted'


@pytest.mark.parametrize('value', [[], 'invalid', 42])
def test_malformed_receipt_is_corrupted_without_consumer_crash(ctx, value):
    ctx.step('synthetic', {}, lambda: ok({}), code_files=['__init__.py'])
    record = read_json(ctx.cache / 'synthetic.json')
    record['execution_receipt'] = value
    assert verify_receipt('synthetic', record) == 'corrupted'


def test_self_rehashed_manifest_still_must_match_module_fingerprint(ctx):
    ctx.step('synthetic', {}, lambda: ok({}), code_files=['__init__.py'])
    record = read_json(ctx.cache / 'synthetic.json')
    record['cache_manifest']['code'] = '0' * 64
    receipt = record['execution_receipt']
    receipt['cache_manifest_fingerprint'] = digest(record['cache_manifest'])
    receipt['receipt_sha256'] = receipt_digest(receipt)
    assert verify_receipt('synthetic', record) == 'corrupted'


def test_missing_receipt_remains_legacy_without_backfill(ctx):
    old = Context(ctx.video, ctx.output, ctx.config, ctx.signature, ctx.logger)
    old.progress = ctx.progress
    old.step('synthetic', {}, lambda: ok({'old': True}), code_files=['__init__.py'])
    path = old.cache / 'synthetic.json'
    before = file_hash(path)
    assert ctx.step('synthetic', {}, lambda: pytest.fail('must read compatible legacy'), code_files=['__init__.py']) == {'old': True}
    assert ctx.stage_metrics['synthetic']['receipt_evidence'] == 'legacy_unattested'
    assert file_hash(path) == before and 'execution_receipt' not in read_json(path)
    broken = read_json(path)
    broken['data']['old'] = False
    assert verify_receipt('synthetic', broken) == 'corrupted'


def test_dependency_swapped_during_producer_prevents_commit(ctx):
    ctx.step('parent', {}, lambda: ok({'value': 1}), code_files=['__init__.py'])
    def swap():
        path = ctx.cache / 'parent.json'
        record = read_json(path)
        record['notes'].append('synthetic changed bytes')
        write_json(path, record)
        return ok({'value': 2})
    with pytest.raises(ValueError, match='inputs_changed'):
        ctx.step('child', {}, swap, requires=['parent'], code_files=['__init__.py'])
    assert 'child' not in ctx.states and not (ctx.cache / 'child.json').exists()


def test_changed_dependency_bytes_reject_cached_hit(ctx):
    ctx.step('parent', {}, lambda: ok({}), code_files=['__init__.py'])
    ctx.step('child', {}, lambda: ok({'generation': 1}), requires=['parent'], code_files=['__init__.py'])
    path = ctx.cache / 'parent.json'
    record = read_json(path)
    record['notes'].append('different byte content, same key/status')
    write_json(path, record)
    result = ctx.step('child', {}, lambda: ok({'generation': 2}), requires=['parent'], code_files=['__init__.py'])
    assert result['generation'] == 2 and ctx.stage_metrics['child']['cache_hit'] is False


def test_snapshot_consumes_original_verified_bytes(tmp_path, monkeypatch):
    path = tmp_path / 'input.json'
    write_json(path, {'version': 1})
    expected = file_hash(path)
    original = Path.read_bytes
    def swap(item):
        raw = original(item)
        if item == path:
            write_json(path, {'version': 2})
        return raw
    monkeypatch.setattr(Path, 'read_bytes', swap)
    assert snapshot_json(path, expected)[0] == {'version': 1}
    with pytest.raises(ValueError, match='checksum_mismatch'):
        snapshot_json(path, expected)


@pytest.mark.parametrize('target', ['analysis.json', 'run_manifest.json', 'manifest.json'])
def test_external_receipt_rejects_tampered_final_bytes(ctx, target):
    for name in ('analysis.json', 'run_manifest.json', 'manifest.json'):
        write_json(ctx.output / name, {'synthetic': name, 'source_sha256': ctx.signature})
    receipt = finalize_report_receipt(ctx, [ctx.output / name for name in ('analysis.json', 'run_manifest.json', 'manifest.json')])
    assert 'report_execution_receipt.json' not in receipt['artifact_checksums']
    assert verify_report_receipt(ctx.output)[0] == receipt
    write_json(ctx.output / target, {'changed': True})
    with pytest.raises(ValueError, match='checksum_mismatch'):
        verify_report_receipt(ctx.output)


@pytest.mark.parametrize('auto', [False, True])
def test_report_20_21_final_receipts_and_refs(tmp_path, auto):
    from types import SimpleNamespace
    from test_stage06_report_coherence import fixture
    from ldporto.reports import ReportEngine
    analysis = fixture()
    context = SimpleNamespace(output=tmp_path / 'reports', signature=analysis['metadata']['sha256'],
        config={'strict': False, 'export': {'second_curation_auto': auto,
                'second_curation_output_dir': str(tmp_path / 'packages')}})
    ReportEngine().run(context, analysis, [])
    record, copies = verify_report_receipt(context.output)
    import json
    final = json.loads(copies['analysis.json'])
    manifest = json.loads(copies['manifest.json'])
    assert manifest['artifact_checksums']['analysis.json'] == file_hash(context.output / 'analysis.json')
    assert final['run_manifest']['export_receipt_ref']['hash_location'] == 'external_only'
    compact_summary = json.loads(copies['analysis_summary.json'])
    assert compact_summary['stage_status']['20_handoff']['key'] == final['run_manifest']['stage_status']['20_handoff']['key']
    for ref in final.get('collection_refs', {}).values():
        assert file_hash(context.output / ref['path']) == ref['sha256']
    cache = context.output / 'cache' / context.signature[:16]
    assert verify_receipt('20_handoff', read_json(cache / '20_handoff.json')) == 'verified'
    if auto:
        producer = read_json(cache / '21_second_curation_handoff.json')
        assert verify_receipt('21_second_curation_handoff', producer) in {'verified', 'verified_partial'}
        assert producer['execution_receipt']['dependency_fingerprints']['20_handoff']['checkpoint_sha256'] == file_hash(cache / '20_handoff.json')
    assert final['run_manifest']['publication_ready'] is False


def test_camera_producers_generate_future_receipts_with_isolated_arguments(ctx, monkeypatch):
    from ldporto.config import load_config
    from ldporto.director_integration import run_planner_stage, run_director_stage
    ctx.config = load_config()
    metadata = {'duration': 1, 'width': 320, 'height': 240}
    semantic, understanding = {'topics': []}, {'main_moments': []}
    def planner(m, *args):
        m['duration'] = 999
        return ok({'selected_global_path': []})
    monkeypatch.setattr('ldporto.director_integration.build_global_camera_plan', planner)
    monkeypatch.setattr('ldporto.director_integration.build_camera_director', lambda *a: ok({'timeline': [], 'metrics': {}}, 'partial'))
    plan = run_planner_stage(ctx, metadata, {}, [], [], [], semantic, understanding)
    run_director_stage(ctx, metadata, {}, [], [], [], semantic, understanding, plan)
    assert metadata['duration'] == 1
    for stage, evidence in [('18b_global_camera_planner', 'verified'), ('19_camera_director', 'verified_partial')]:
        assert verify_receipt(stage, read_json(ctx.cache / (stage + '.json'))) == evidence
    assert ctx.states['19_camera_director']['status'] == 'partial'


def test_new_full_synthetic_chain_can_be_reviewed_without_historical_backfill(full_execution, monkeypatch):
    from test_stage06_report_coherence import fixture
    from ldporto.run_status import build_run_manifest
    from ldporto.reports import ReportEngine
    from ldporto.curation_recovery import plan_recovery
    ctx, proof = full_execution
    monkeypatch.setattr('ldporto.runtime_metrics.resource_snapshot', lambda: {'peak_process_memory_bytes': None})
    analysis = fixture()
    analysis['metadata']['sha256'] = ctx.signature
    analysis['stage_status'] = deepcopy(ctx.states)
    analysis['run_manifest'] = build_run_manifest(analysis['metadata'], ctx.states, [], previous={'execution_attestation': proof})
    ctx.config['export']['second_curation_auto'] = False
    ReportEngine().run(ctx, analysis, [])
    plan = plan_recovery(ctx.output, ctx.cache)
    assert plan['can_replay'] is True, (plan['blockers'], [s for s in plan['stages'] if s['reason']])
    assert plan['publication_ready'] is False
    # Removing a new camera receipt becomes explicitly legacy_unattested.
    path = ctx.cache / '18b_global_camera_planner.json'
    record = read_json(path)
    record.pop('execution_receipt')
    write_json(path, record)
    blocked = plan_recovery(ctx.output, ctx.cache)
    assert blocked['can_replay'] is False
    stage = next(s for s in blocked['stages'] if s['stage'] == '18b_global_camera_planner')
    assert stage['reason'] == 'legacy_unattested'


def test_partial_camera_output_hash_does_not_validate_full_execution(full_execution):
    from ldporto.build_provenance import attest_execution
    from ldporto.reports import _run_manifest
    ctx, _ = full_execution
    ctx.force = True
    ctx.step('19_camera_director', {}, lambda: ok({'timeline': []}, 'partial'), code_files=['__init__.py'])
    assert attest_execution(ctx) is None
    manifest = _run_manifest({'metadata': {'sha256': ctx.signature}, 'stage_status': deepcopy(ctx.states)}, ctx)
    assert manifest['analysis_status'] == 'partial'
    assert manifest['build_provenance']['execution_complete'] is not True
    assert '19_camera_director' in manifest['build_provenance']['unverified_stages']

@pytest.mark.parametrize('member', [
    '../outside.json', 'sub/../outside.json', './analysis.json',
    'C:/secret.json', r'C:\secret.json', r'..\outside.json',
    '//server/share/file.json', 'sub//analysis.json', '',
])
def test_report_receipt_rejects_noncanonical_or_external_paths(ctx, member):
    from ldporto.execution_receipts import _report_member_path
    write_json(ctx.output / 'analysis.json', {'synthetic': True})
    with pytest.raises(ValueError, match='unsafe_report_reference'):
        _report_member_path(ctx.output, member)


def test_report_receipt_rejects_external_file_on_creation(ctx, tmp_path):
    write_json(ctx.output / 'analysis.json', {'synthetic': True})
    outside = tmp_path / 'elsewhere.json'
    write_json(outside, {'synthetic': True})
    with pytest.raises(ValueError, match='unsafe_report_reference'):
        finalize_report_receipt(ctx, [ctx.output / 'analysis.json', outside])


def test_report_receipt_rejects_missing_member_on_creation(ctx):
    with pytest.raises(ValueError, match='report_reference_missing'):
        finalize_report_receipt(ctx, [ctx.output / 'missing.json'])
