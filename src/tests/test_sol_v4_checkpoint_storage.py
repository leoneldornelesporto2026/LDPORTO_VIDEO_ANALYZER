"""Offline storage compatibility, provenance and mutation canaries; no inference."""
from copy import deepcopy
import importlib.util
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from ldporto.checkpoint_storage import decode_checkpoint, encode_checkpoint
from ldporto.core import digest, file_hash, ok, read_json, write_json
from ldporto.execution_receipts import snapshot_json, verify_receipt


def test_sources_export_excludes_raw_report_checkpoints_but_preserves_summaries_and_fixtures(tmp_path):
    from scripts.export import exportar_ldporto as exporter
    root, output = tmp_path / 'project', tmp_path / 'packages'
    fixtures = {
        'src/ldporto/pipeline.py': '# synthetic source package fixture\n',
        'exportar_ldporto.py': '# synthetic wrapper\n',
        'config/config.yaml': 'fixture: true\n',
        'analyze.py': '# synthetic CLI\n', 'app.py': '# synthetic app\n',
        'docs/reports/fixture/storage/10_active_speaker.json': '{"raw_fixture":true}',
        'docs/reports/fixture/storage/18b_global_camera_planner.json': '{"raw_fixture":true}',
        'docs/reports/fixture/storage/result.json': '{"benchmark_summary":true}',
        'docs/reports/fixture/RELATORIO.md': 'Synthetic report.\n',
        'src/tests/fixtures/10_active_speaker.json': '{"contract_fixture":true}',
    }
    for name, contents in fixtures.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8')
    selected = {p.relative_to(root).as_posix() for p in exporter.collect_project_files(root, output)}
    raw = {name for name in fixtures if '/storage/' in name and name != 'docs/reports/fixture/storage/result.json'}
    assert not selected & raw
    assert set(fixtures) - raw <= selected
    package, manifest = exporter.build_project_package(root, output, 'fixture', 32, 180)
    assert manifest['export_state'] == 'READY' and manifest['skipped'] == []
    assert manifest['report_checkpoint_snapshots'] == 'retained_locally_excluded_from_sources_package'
    assert exporter.inspect_package(package)['status'] == 'PASS'
    with ZipFile(package) as archive:
        assert not set(archive.namelist()) & raw
        assert 'src/tests/fixtures/10_active_speaker.json' in archive.namelist()
    for name in raw:
        assert (root / name).read_text(encoding='utf-8') == fixtures[name]


def record_fixture():
    mappings = [{'start': -0.0, 'end': 1.25, 'speaker_id': 'SYNTHETIC_A',
        'speaker': 'SYNTHETIC_A', 'person_id': None, 'visible_person': None,
        'confidence': None, 'association_confidence': None, 'active_person': None,
        'overlap': False, 'evidence': ['fixture_only'],
        'audio_video_sync': {'status': 'not_measured', 'median_lag_seconds': None},
        'person_roles': [{'person_id': 'SYNTHETIC_P', 'role': 'UNRESOLVED'}]}]
    intervals = [{key: deepcopy(value) for key, value in row.items()
                  if key not in ('speaker', 'visible_person', 'association_confidence')}
                 for row in mappings]
    data = {'mappings': mappings, 'intervals': intervals, 'active_speaker_evidence': [],
            'metrics': {'accuracy': None}}
    return {'status': 'partial', 'data': data, 'data_checksum': digest(data)}


def test_codec_roundtrip_preserves_semantic_hash_and_nested_isolation():
    original = record_fixture()
    before = digest(original)
    physical = encode_checkpoint(original)
    assert physical['data']['intervals']['record_count'] == 1
    assert isinstance(original['data']['intervals'], list)
    logical = decode_checkpoint(physical)
    assert digest(logical) == before and 'checkpoint_storage' not in logical
    logical['data']['intervals'][0]['person_roles'][0]['role'] = 'changed_fixture'
    assert logical['data']['mappings'][0]['person_roles'][0]['role'] == 'UNRESOLVED'
    assert digest(original) == before


@pytest.mark.parametrize('field,value', [
    ('overlap', 0), ('end', 1), ('start', 0.0), ('person_id', 'SYNTHETIC_OTHER'),
    ('confidence', 0.0), ('extra_evidence', ['preserve_me']),
])
def test_any_projection_difference_keeps_all_evidence(field, value):
    original = record_fixture()
    original['data']['intervals'][0][field] = value
    assert encode_checkpoint(original) is original


@pytest.mark.parametrize('change', ['shorter', 'missing', 'not_list', 'row_not_dict', 'other_stage'])
def test_unsupported_producer_payload_keeps_complete_legacy(change):
    original = record_fixture()
    if change == 'shorter':
        original['data']['intervals'] = []
    elif change == 'missing':
        original['data'].pop('intervals')
    elif change == 'not_list':
        original['data']['mappings'] = {}
    elif change == 'row_not_dict':
        original['data']['mappings'][0] = None
    assert encode_checkpoint(original, stage='other' if change == 'other_stage' else '10_active_speaker') is original


@pytest.mark.parametrize('change', ['version', 'codec', 'stage', 'extra_marker', 'count',
                                  'bool_count', 'reference', 'extra_reference', 'full_intervals', 'rows'])
def test_unknown_or_corrupt_physical_storage_fails_closed(change):
    physical = deepcopy(encode_checkpoint(record_fixture()))
    marker, view = physical['checkpoint_storage'], physical['data']['intervals']
    if change in ('version', 'codec', 'stage'):
        marker[{'version': 'schema_version', 'codec': 'codec', 'stage': 'stage_id'}[change]] = 'unknown'
    elif change == 'extra_marker':
        marker['external_path'] = '../forbidden'
    elif change == 'count':
        view['record_count'] = 2
    elif change == 'bool_count':
        view['record_count'] = True
    elif change == 'reference':
        view['$derived'] = '../another_file'
    elif change == 'extra_reference':
        view['path'] = '../another_file'
    elif change == 'full_intervals':
        physical['data']['intervals'] = []
    elif change == 'rows':
        physical['data']['mappings'][0] = None
    with pytest.raises(ValueError):
        decode_checkpoint(physical)


def test_legacy_read_is_unchanged_and_physical_hash_is_verified(tmp_path):
    legacy = record_fixture()
    assert decode_checkpoint(legacy) is legacy
    path = tmp_path / 'checkpoint.json'
    write_json(path, encode_checkpoint(legacy))
    expected = file_hash(path)
    logical, actual = snapshot_json(path, expected)
    assert actual == expected and digest(logical) == digest(legacy)
    assert read_json(path) == logical
    physical = json.loads(path.read_text('utf-8'))
    physical['data']['mappings'][0]['end'] = 9.0
    write_json(path, physical)
    with pytest.raises(ValueError, match='checksum_mismatch'):
        snapshot_json(path, expected)
    assert verify_receipt('10_active_speaker', read_json(path)) == 'corrupted'


def test_new_stage_checkpoint_is_compact_and_resume_preserves_its_bytes(tmp_path, monkeypatch):
    from ldporto.build_provenance import ProvenanceContext
    monkeypatch.setattr('ldporto.core.versions', lambda: {})
    monkeypatch.setattr('ldporto.runtime_metrics.resource_snapshot', lambda: {})
    ctx = ProvenanceContext(tmp_path / 'synthetic.bin', tmp_path / 'run', {'strict': False},
                            'fixture', logging.getLogger('storage-v4'))
    ctx.progress = lambda *args, **kwargs: None
    data = record_fixture()['data']
    selected = ['__init__.py', 'checkpoint_storage.py']
    assert ctx.step('10_active_speaker', {}, lambda: ok(data, 'partial'), code_files=selected) == data
    path = ctx.cache / '10_active_speaker.json'
    raw = json.loads(path.read_text('utf-8'))
    assert raw['checkpoint_storage']['schema_version'] == '1.0'
    logical = read_json(path)
    assert verify_receipt('10_active_speaker', logical) == 'verified_partial'
    before = file_hash(path)
    assert ctx.step('10_active_speaker', {}, lambda: pytest.fail('cache must avoid producer'), code_files=selected) == data
    assert ctx.stage_metrics['10_active_speaker']['cache_hit'] and file_hash(path) == before


def test_verifier_hashes_payload_once_and_keeps_second_artifact_barrier(tmp_path, monkeypatch):
    import ldporto.execution_receipts as receipts
    data = record_fixture()['data']
    modules = {'__init__.py': '1' * 64}
    artifact = str(tmp_path / 'external.json')
    record = {'status': 'partial', 'data': data, 'data_checksum': digest(data),
              'key': 'key', 'input_hash': 'source', 'config_hash': 'config',
              'artifact_checksums': {artifact: 'a' * 64}}
    record['execution_receipt'] = receipts.create_receipt('10_active_speaker', record, modules, {}, input_fingerprint='config')
    original_digest = receipts.digest
    hashed = []
    def counted(value):
        if value is data:
            hashed.append(True)
        return original_digest(value)
    monkeypatch.setattr(receipts, 'digest', counted)
    reads = []
    def changing_artifact(path):
        reads.append(path)
        return 'a' * 64 if len(reads) == 1 else 'b' * 64
    monkeypatch.setattr(receipts, 'file_hash', changing_artifact)
    assert verify_receipt('10_active_speaker', record) == 'corrupted'
    assert len(hashed) == 1 and len(reads) == 2


def test_buffered_writer_matches_legacy_bytes_above_buffer_boundary(tmp_path):
    value = {'unicode': ('ação — 🐢 " \\ ' * 35000), 'numbers': [-0.0, 1, True, None],
             'nested': [{'text': 'literal', 'time': .125}] * 4000}
    expected = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'), default=str).encode('utf-8')
    path = tmp_path / 'large.json'
    write_json(path, value)
    assert path.read_bytes() == expected and read_json(path) == value


@pytest.mark.parametrize('script', ['audit_camera_s6.py', 'audit_speaker_s5.py'])
@pytest.mark.parametrize('zipped', [False, True])
def test_audit_loaders_hydrate_directory_and_zip(script, zipped, tmp_path):
    location = Path(__file__).resolve().parents[2] / 'scripts' / 'dev' / script
    spec = importlib.util.spec_from_file_location('storage_audit_' + script, location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = record_fixture()
    path = tmp_path / '10_active_speaker.json'
    write_json(path, encode_checkpoint(original))
    source = tmp_path
    if zipped:
        source = tmp_path / 'evidence.zip'
        with ZipFile(source, 'w') as archive:
            archive.write(path, 'cache/fixture/10_active_speaker.json')
    assert digest(module.load(source, '10_active_speaker.json')) == digest(original)


def test_sidecar_references_preserve_absent_inline_data_and_detect_tampering(tmp_path):
    from ldporto.compact_artifacts import COLLECTION_FILES, compact_analysis_document, load_analysis_artifacts
    keys = ('active_speaker_evidence', 'speaker_person_diagnostics', 'speaker_person_affinity',
            'semantic_chunk_profile', 'ollama_editorial_review', 'broadcast_graphics')
    original = {key: [{'fixture_id': key, 'value': None}] for key in keys}
    for key in keys[:-1]:
        write_json(tmp_path / COLLECTION_FILES[key], original[key])
    document = compact_analysis_document(original, tmp_path)
    assert document['broadcast_graphics'] == original['broadcast_graphics']
    assert all(key in document['collection_refs'] for key in keys[:-1])
    write_json(tmp_path / 'analysis.json', document)
    hydrated = load_analysis_artifacts(tmp_path)
    assert all(hydrated[key] == original[key] for key in keys)
    write_json(tmp_path / COLLECTION_FILES[keys[0]], [])
    with pytest.raises(ValueError, match='Checksum'):
        load_analysis_artifacts(tmp_path)


def test_camera_replay_hydrates_protected_graphics_from_verified_compact_sidecar(tmp_path, monkeypatch):
    """Synthetic protected region must survive reference storage and S6 replay."""
    from ldporto.compact_artifacts import COLLECTION_FILES, compact_analysis_document
    script = Path(__file__).resolve().parents[2] / 'scripts/dev/audit_camera_s6.py'
    spec = importlib.util.spec_from_file_location('s6_compact_graphics_canary', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    graphics = {'intervals': [{'start': 0., 'end': 1.,
        'protected_regions': [{'x': .05, 'y': .8, 'width': .9, 'height': .15}],
        'scope': 'synthetic_graphic_fixture'}]}
    analysis = {'metadata': {'duration': 1., 'width': 1920, 'height': 1080},
        'video_analysis': {'frame_samples': [{'time': .25, 'scene_id': 'SH1', 'visible_people': []}]},
        'people_observations': [{'time': .25, 'person_id': 'SYNTHETIC', 'scene_id': 'SH1'}],
        'shots': [{'start': 0., 'end': 1., 'scene_id': 'SH1'}],
        'active_speaker': [], 'person_motion': [], 'broadcast_graphics': graphics}
    for key, value in analysis.items():
        if key in COLLECTION_FILES:
            write_json(tmp_path / COLLECTION_FILES[key], value)
    compact = compact_analysis_document(analysis, tmp_path)
    assert 'broadcast_graphics' not in compact and 'broadcast_graphics' in compact['collection_refs']
    write_json(tmp_path / 'analysis.json', compact)
    received = []
    def director(metadata, vision, *args, **kwargs):
        received.append(vision['broadcast_graphics'])
        return {'data': {'protected_graphics': vision['broadcast_graphics']}}
    monkeypatch.setattr(module, 'build_camera_director', director)
    assert module.replay(tmp_path)['protected_graphics'] == graphics
    assert received == [graphics]
    write_json(tmp_path / 'broadcast_graphics.json', {'intervals': []})
    with pytest.raises(ValueError, match='Checksum'):
        module.replay(tmp_path)
    assert received == [graphics]  # Tampered evidence never reaches the director.


def test_report_snapshot_stays_isolated_and_finalization_diagnostics_are_real(tmp_path):
    from test_stage06_report_coherence import fixture
    from ldporto.reports import ReportEngine
    from ldporto.execution_receipts import verify_report_receipt
    analysis = fixture()
    ctx = SimpleNamespace(output=tmp_path / 'reports', signature=analysis['metadata']['sha256'],
        config={'strict': False, 'export': {'second_curation_auto': False}})
    ReportEngine().run(ctx, analysis, [])
    checkpoint = read_json(ctx.output / 'cache' / ctx.signature[:16] / '20_handoff.json')
    snapshot_path, expected = next(iter(checkpoint['artifact_checksums'].items()))
    captured, physical_sha = snapshot_json(snapshot_path, expected)
    assert physical_sha == expected and digest(captured) == checkpoint['execution_receipt']['input_fingerprint']
    assert captured['stage_status']['20_handoff'].get('key') != analysis['stage_status']['20_handoff']['key']
    assert verify_report_receipt(ctx.output)[0]['status'] == 'ok'
    storage = read_json(ctx.output / 'artifact_metrics.json')
    assert storage['report_wall_seconds_until_metrics_write'] >= storage['serialization_seconds']
    assert storage['post_handoff_finalization_seconds'] >= storage['final_receipt_seconds'] >= 0
    assert analysis['run_manifest']['publication_ready'] is False


@pytest.mark.parametrize('metadata_state', ['current', 'legacy', 'tampered'])
def test_semantic_cache_keeps_original_costs_separate_from_current_calls(tmp_path, monkeypatch, metadata_state):
    from ldporto import semantic
    from test_v42_editorial import semantic_context, model_fixture
    ctx, transcript = semantic_context(tmp_path, monkeypatch)
    calls = []
    observed = {'eval_count': 12, 'eval_duration_ns': 2_000_000_000,
                'prompt_eval_count': 20, 'prompt_eval_duration_ns': 1_000_000_000}
    monkeypatch.setattr(semantic, 'call_ollama', lambda *args: (calls.append(True) or model_fixture(), deepcopy(observed)))
    first = semantic.SemanticEngine().run(ctx, transcript)['data']
    assert first['semantic_metrics']['semantic_generated_tokens'] == 12
    path = next((ctx.cache / 'semantic_chunks').glob('*.json'))
    cached = read_json(path)
    history = cached['original_execution_metadata']
    assert history['call'] == observed and history['validation_success']
    if metadata_state == 'legacy':
        cached.pop('original_execution_metadata')
        cached.pop('original_execution_metadata_checksum')
        write_json(path, cached)
    elif metadata_state == 'tampered':
        cached['original_execution_metadata']['call']['eval_count'] = 999
        write_json(path, cached)
    before = file_hash(path)
    second = semantic.SemanticEngine().run(ctx, transcript)['data']
    assert len(calls) == 1 and second['semantic_metrics']['total_inference_call_count'] == 0
    assert second['semantic_metrics']['semantic_generated_tokens'] is None
    assert file_hash(path) == before
    entry = second['semantic_chunk_profile'][0]
    if metadata_state == 'current':
        assert entry['cached_original_execution_metadata']['call']['eval_count'] == 12
        assert 'historical_only' in entry['cached_original_cost_scope']
    else:
        assert 'cached_original_execution_metadata' not in entry
