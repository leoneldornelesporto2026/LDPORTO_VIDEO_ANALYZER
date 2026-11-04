"""Offline privacy and artifact-only recovery adversarial regressions."""
import json
from pathlib import Path

import pytest

from ldporto.core import digest, file_hash, write_json
from ldporto.export_privacy import document_findings, privacy_findings, sanitize_export
from ldporto.curation_recovery import plan_recovery, recover, snapshot
from ldporto.second_curation_export import build_core_package, validate_core_package, PRIVATE_PATH
from test_stage43_capability_contract import disabled_analysis


@pytest.mark.parametrize('name', ['candidates/MOMENT_00004_0003.json',
    'candidates/MOMENT_00028_0004.json', 'editorial/candidate_catalog.json', 'visual/commercial_ocr_s8.json'])
def test_four_serialized_false_positives(name):
    data = json.dumps({'observations': [{'text': '\\', 'original_text': '\\'}]}).encode()
    # The old expression accepted a bare pair of escape characters as a UNC.
    import re
    legacy = re.compile(r'\\\\[^\s]+')
    assert legacy.search(data.decode())
    assert not document_findings(name, data)


@pytest.mark.parametrize('value', ['(11) 98765-4321', 'person@example.test',
    'hf_SYNTHETICONLY', '123.456.789-00', 'https://user:password@example.test/path',
    'https://example.test/?access_token=synthetic', 'C:\\Users\\synthetic\\file',
    '\\\\server\\share\\private.txt', 'Bearer synthetic'])
def test_true_privacy_nested_long_unicode(value):
    original = {'ocr': ['ação ' * 10000 + value], 'timestamp': 8245.014}
    assert privacy_findings(original)
    clean = sanitize_export(original)
    assert not privacy_findings(clean)
    assert sanitize_export(clean) == clean
    assert clean['timestamp'] == original['timestamp'] and original['ocr'][0].endswith(value)


def test_public_ads_null_and_sensitive_keys():
    public = {'brand': 'MARCA PÚBLICA', 'ocr': ['PROMOÇÃO 60% OFF', '12:34:56', '\\'],
              'price': 'R$ 199,90', 'standalone_clarity': None}
    assert sanitize_export(public) == public and not privacy_findings(public)
    assert sanitize_export({'nested': {'api_key': 'synthetic', 'private_prompt': 'private'}}) == {'nested': {}}


@pytest.fixture
def directory(tmp_path):
    result = build_core_package(disabled_analysis(), output_dir=tmp_path/'export',
                               cfg={'second_curation_visual_candidate_limit': 0}, directory_only=True)
    assert result['publication_ready'] is False
    assert result['validation']['status'] == 'valid'
    return Path(result['path'])


@pytest.mark.parametrize('name', ['SECOND_CURATION_MANIFEST.json', 'source/metadata.json',
                                'editorial/candidate_catalog.json', 'visual/commercial_ocr_s8.json'])
def test_leaks_block_even_with_updated_checksum(directory, name):
    path = directory/name
    value = json.loads(path.read_text(encoding='utf-8'))
    value['private_test'] = {'token': 'synthetic'}
    write_json(path, value)
    manifest_path = directory/'SECOND_CURATION_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest['files']:
        if entry['path'] == name:
            entry.update(sha256=file_hash(path), bytes=path.stat().st_size)
    write_json(manifest_path, manifest)
    assert 'private_data:'+name in validate_core_package(directory)['errors']


@pytest.mark.parametrize('kind', ['missing', 'checksum', 'disk'])
def test_validation_failure(directory, monkeypatch, kind):
    path = directory/'source/metadata.json'
    if kind == 'missing':
        path.unlink()
    elif kind == 'checksum':
        path.write_bytes(path.read_bytes()+b' ')
    else:
        original = Path.read_bytes
        def denied(item):
            if item == path:
                raise PermissionError('synthetic')
            return original(item)
        monkeypatch.setattr(Path, 'read_bytes', denied)
    assert validate_core_package(directory)['status'] == 'failed'


def fixture_cache(tmp_path):
    folder = tmp_path/'analysis'
    cache = folder/'cache'
    cache.mkdir(parents=True)
    data = disabled_analysis()
    from ldporto.run_status import DEPENDENCIES
    states = {stage: {'status': 'ok', 'key': 'fixture'} for stage in DEPENDENCIES}
    states['21_second_curation_handoff'] = {'status': 'failed'}
    data['run_manifest'] = {'stage_status': states}
    write_json(folder/'analysis.json', data)
    for stage in states:
        if stage.startswith('21_'):
            continue
        write_json(cache/(stage+'.json'), {'status': 'ok', 'key': 'fixture', 'data': {},
                   'input_hash': digest({}), 'config_hash': digest({}), 'output_version': digest({}),
                   'execution_receipt': {'module_hashes': {}, 'module_fingerprint': digest({}),
                                         'source_sha256': digest({}), 'producer': 'Context.step', 'execution_returncode': 0},
                   'artifact_checksums': {str(folder/'analysis.json'): file_hash(folder/'analysis.json')} if stage == '20_handoff' else {},
                   'data_checksum': digest({}), 'cache_manifest': {
                       **{field: digest({}) for field in ('input', 'params', 'code', 'versions', 'output_version')},
                       'dependencies': digest({d: states[d] for d in DEPENDENCIES[stage]})}})
    return folder, cache


def test_replay_dry_run_and_apply_never_processes_upstream(tmp_path, monkeypatch):
    folder, cache = fixture_cache(tmp_path)
    before = snapshot(folder)
    import ldporto.second_curation_export as exporter
    def forbidden(*args, **kwargs):
        pytest.fail('media processing is forbidden')
    monkeypatch.setattr(exporter, 'build_contact_sheet', forbidden)
    monkeypatch.setattr(exporter, 'render_preview', forbidden)
    plan = recover(folder, cache)
    assert plan['can_replay'] and plan['would_invalidate'] == ['21_second_curation_handoff']
    assert not (tmp_path/'out').exists()
    result = recover(folder, cache, tmp_path/'out', apply=True, expected_hashes=before)
    assert result['upstream_unchanged'] and snapshot(folder) == before
    assert result['package']['validation']['status'] == 'valid'
    assert not result['publication_ready']
    assert not list(tmp_path.rglob('*.zip'))


@pytest.mark.parametrize('kind', ['missing', 'corrupt', 'snapshot'])
def test_replay_fail_closed_preserves_original(tmp_path, kind):
    folder, cache = fixture_cache(tmp_path)
    if kind == 'missing':
        (cache/'20_handoff.json').unlink()
    elif kind == 'corrupt':
        record = json.loads((cache/'01_metadata.json').read_text())
        record['data'] = {'changed': True}
        write_json(cache/'01_metadata.json', record)
    before = snapshot(folder)
    with pytest.raises(ValueError):
        recover(folder, cache, tmp_path/'out', apply=True, expected_hashes={} if kind == 'snapshot' else before)
    assert snapshot(folder) == before and not (tmp_path/'out').exists()


def test_links_are_blocked(tmp_path, directory):
    link = directory/'linked.json'
    try:
        link.symlink_to(directory/'source/metadata.json')
    except OSError:
        pytest.skip('Windows symlink privilege unavailable')
    assert validate_core_package(directory)['status'] == 'failed'


@pytest.mark.parametrize('field', ['dependencies', 'params', 'input', 'code'])
def test_cache_dependency_contract_cannot_be_forged(tmp_path, field):
    folder, cache = fixture_cache(tmp_path)
    path = cache/'01_metadata.json'
    value = json.loads(path.read_text())
    value['cache_manifest'][field] = '0'*64
    write_json(path, value)
    assert not plan_recovery(folder, cache)['can_replay']


def test_windows_reparse_attribute_fail_closed(directory, monkeypatch):
    import ldporto.export_privacy as privacy
    original = Path.lstat
    def reparse(path):
        if path == directory:
            return type('Stat', (), {'st_file_attributes': 1024, 'st_mode': original(path).st_mode})()
        return original(path)
    monkeypatch.setattr(Path, 'lstat', reparse)
    with pytest.raises(ValueError, match='unsafe_link'):
        privacy.safe_path(directory)



@pytest.fixture
def historical_snapshot_fixture(tmp_path, monkeypatch):
    """Portable historical-contract fixture; never weakens production pins."""
    import hashlib
    import zipfile
    import ldporto.curation_recovery as recovery

    content = b'# Synthetic historical producer\n'
    archive = tmp_path / 'historical_contract_fixture.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('src/ldporto/historical_producer.py', content)
    data = archive.read_bytes()
    module_hashes = {'historical_producer.py': hashlib.sha256(content).hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(module_hashes, sort_keys=True).encode()).hexdigest()
    monkeypatch.setattr(recovery, 'HISTORICAL_SNAPSHOT', archive)
    monkeypatch.setattr(recovery, 'HISTORICAL_SNAPSHOT_SHA256', hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(recovery, 'HISTORICAL_FINGERPRINT', fingerprint)
    return fingerprint


def test_uncached_handoff_requires_producer_artifact_checksums(tmp_path, historical_snapshot_fixture):
    folder, cache = fixture_cache(tmp_path)
    (cache/'20_handoff.json').unlink()
    analysis = json.loads((folder/'analysis.json').read_text())
    from ldporto.curation_recovery import HISTORICAL_FINGERPRINT
    analysis['run_manifest']['stage_status']['20_handoff'] = {
        'status': 'ok', 'method': 'uncached_export', 'execution_provenance': {
            'origin': 'executed', 'analyzer_build': 'R4.9-S4-TRACKING-FACIAL',
            'code_fingerprint': HISTORICAL_FINGERPRINT}}
    write_json(folder/'analysis.json', analysis)
    manifest = {'stage_status': {'20_handoff': {'status': 'ok'}}, 'artifact_checksums': {}}
    write_json(folder/'manifest.json', manifest)
    assert not plan_recovery(folder, cache)['can_replay']
    for name in ('CHATGPT_ANALYSIS_HANDOFF.compact.json', 'second_curation_package.json'):
        value = {'schema_version': '3.1', 'candidates': []} if name == 'second_curation_package.json' else {
            'schema_version': '4.2', 'second_curation_package_ref': {'path': 'second_curation_package.json'}}
        write_json(folder/name, value)
        manifest['artifact_checksums'][name] = file_hash(folder/name)
    write_json(folder/'manifest.json', manifest)
    assert not plan_recovery(folder, cache)['can_replay']  # inline inputs still unsigned
    manifest['artifact_checksums']['analysis.json'] = file_hash(folder/'analysis.json')
    write_json(folder/'manifest.json', manifest)
    assert plan_recovery(folder, cache)['can_replay']
    # A manifest and all hashes can agree while the payload contract is invalid.
    write_json(folder/'second_curation_package.json', {'schema_version': 'false', 'candidates': []})
    manifest['artifact_checksums']['second_curation_package.json'] = file_hash(folder/'second_curation_package.json')
    write_json(folder/'manifest.json', manifest)
    assert any(s['reason'] == 'handoff_schema_mismatch' for s in plan_recovery(folder, cache)['stages'])
    (folder/'CHATGPT_ANALYSIS_HANDOFF.compact.json').write_text('{}')
    assert not plan_recovery(folder, cache)['can_replay']


def test_historical_contract_rejects_false_producer_and_tampered_snapshot(tmp_path, monkeypatch, historical_snapshot_fixture):
    import ldporto.curation_recovery as recovery
    expected = {'status': 'ok', 'method': 'uncached_export', 'execution_provenance': {
        'origin': 'executed', 'analyzer_build': 'R4.9-S4-TRACKING-FACIAL',
        'code_fingerprint': recovery.HISTORICAL_FINGERPRINT}}
    assert recovery.historical_contract(expected) is None
    expected['execution_provenance']['code_fingerprint'] = '0'*64
    assert recovery.historical_contract(expected) == 'historical_producer_mismatch'
    expected['execution_provenance']['code_fingerprint'] = recovery.HISTORICAL_FINGERPRINT
    archive = tmp_path/'tampered.zip'
    archive.write_bytes(b'not a historical producer')
    monkeypatch.setattr(recovery, 'HISTORICAL_SNAPSHOT', archive)
    assert recovery.historical_contract(expected) == 'historical_snapshot_checksum_mismatch'


def test_complementary_full_handoff_not_consumed_and_orphan_blocked(tmp_path):
    folder, cache = fixture_cache(tmp_path)
    (folder/'CHATGPT_ANALYSIS_HANDOFF.json').write_text('invalid JSON: never consumed')
    assert plan_recovery(folder, cache)['can_replay']
    data = json.loads((folder/'analysis.json').read_text())
    del data['run_manifest']['stage_status']['19_camera_director']
    write_json(folder/'analysis.json', data)
    plan = plan_recovery(folder, cache)
    assert not plan['can_replay']
    assert any(r['reason'] == 'missing_stage_dependency' for r in plan['stages'])


def test_file_change_during_validation_blocks(tmp_path, monkeypatch):
    import ldporto.curation_recovery as recovery
    folder, cache = fixture_cache(tmp_path)
    original = recovery.snapshot
    calls = []
    def changed(path):
        calls.append(path)
        if len(calls) == 2:
            (folder/'changed.json').write_text('{}')
        return original(path)
    monkeypatch.setattr(recovery, 'snapshot', changed)
    plan = recovery.plan_recovery(folder, cache)
    assert not plan['can_replay']
    assert 'upstream_changed_during_validation' in plan['blockers']


def test_consumption_change_leaves_no_confirmed_output(tmp_path, monkeypatch):
    import ldporto.curation_recovery as recovery
    folder, cache = fixture_cache(tmp_path)
    original = recovery.plan_recovery
    def changed(*args):
        plan = original(*args)
        (folder/'analysis.json').write_bytes(b'{}')
        return plan
    hashes = recovery.snapshot(folder)
    monkeypatch.setattr(recovery, 'plan_recovery', changed)
    with pytest.raises(ValueError, match='upstream_changed_before_consumption'):
        recovery.recover(folder, cache, tmp_path/'out', apply=True, expected_hashes=hashes)
    assert not (tmp_path/'out').exists()


def test_diagnostics_never_include_private_object_keys():
    value = {'person@example.test': {'secret': 'synthetic'}}
    findings = json.dumps(privacy_findings(value))
    assert 'person@example.test' not in findings and 'synthetic' not in findings
    assert 'key_sha256_' in findings
    assert not privacy_findings(sanitize_export(value))


def test_bytes_used_for_validation_must_match_inventory(tmp_path):
    from ldporto.curation_recovery import verified_json
    folder, cache = fixture_cache(tmp_path)
    before = snapshot(folder)
    (folder/'analysis.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='upstream_changed_before_validation_read'):
        verified_json(folder, folder/'analysis.json', before)


def test_uncached_receipt_cannot_omit_stage_dependencies(tmp_path, monkeypatch):
    import ldporto.curation_recovery as recovery
    folder, cache = fixture_cache(tmp_path)
    (cache/'20_handoff.json').unlink()
    monkeypatch.setattr(recovery, 'handoff_receipt', lambda *args: None)
    data = json.loads((folder/'analysis.json').read_text())
    del data['run_manifest']['stage_status']['18_analysis_quality']
    write_json(folder/'analysis.json', data)
    plan = recovery.plan_recovery(folder, cache)
    assert any(s['stage'] == '20_handoff' and s['reason'] == 'missing_stage_dependency' for s in plan['stages'])
