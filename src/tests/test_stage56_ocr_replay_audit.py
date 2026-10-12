"""Offline synthetic evidence only; no real media or Tesseract inference."""
import importlib.util
import copy
import sys
import json
from pathlib import Path

import pytest

from test_stage46_commercial_visual_replay import visual_case
from ldporto import replay, commercial_gate
from ldporto.core import file_hash, read_json, write_json


def snapshot_hashes(folder):
    return {str(p.relative_to(folder)): file_hash(p) for p in folder.rglob('*') if p.is_file()}


def test_enable_after_old_disabled_snapshot_is_bounded_and_audited(visual_case):
    case = visual_case
    summary = read_json(case.folder / 'analysis_summary.json')
    summary.setdefault('stage_status', {})['13_ocr'] = {'status': 'skipped', 'reason': 'ocr_disabled'}
    write_json(case.folder / 'analysis_summary.json', summary)
    historical = case.folder / 'cache' / 'historical'
    historical.mkdir(parents=True)
    write_json(historical / '13_ocr.json', {'status': 'skipped', 'data': {}, 'historical': True})
    before = snapshot_hashes(case.folder)
    case.cfg['export']['second_curation_visual_candidate_limit'] = 1
    first = case.run('commercial')
    receipt = read_json(case.output / 'reprocess_manifest.json')
    assert len(case.calls) == 3
    assert first['commercial_visual_s8']['max_frames'] == 3
    assert receipt['stages']['17c_commercial_visual']['stage_origin'] == 'actually_executed'
    assert receipt['stages']['04_transcription']['stage_origin'] == 'snapshot'
    assert receipt['stages']['15_semantic']['stage_origin'] == 'snapshot'
    assert receipt['measurement_state'] == 'measured'
    assert receipt['replay_checkpoint_before'] == {}
    assert receipt['upstream_checkpoint_sha256']['cache/historical/13_ocr.json'] == before['cache\\historical\\13_ocr.json' if sys.platform == 'win32' else 'cache/historical/13_ocr.json']
    second = case.run('commercial')
    cached = second['reprocess_manifest']
    assert len(case.calls) == 3
    assert cached['stages']['17c_commercial_visual']['stage_origin'] == 'cache'
    assert receipt['ocr_evidence_sha256'] == cached['ocr_evidence_sha256']
    assert cached['replay_checkpoint_before'] == cached['replay_checkpoint_after']
    assert snapshot_hashes(case.folder) == before
    assert not cached['publication_ready']
    assert cached['upstream_checkpoints_unchanged']
    print(json.dumps({'fixture_kind': 'synthetic_only', 'ocr_calls_first': 3, 'ocr_calls_cached': 0,
                      'evidence_sha256_before': receipt['ocr_evidence_sha256'],
                      'evidence_sha256_after': cached['ocr_evidence_sha256'],
                      'historical_checkpoint_sha256': receipt['upstream_checkpoint_sha256']}))


def test_dry_run_no_frames_or_output_and_missing_dependencies(visual_case):
    case = visual_case
    before = snapshot_hashes(case.folder)
    plan = replay.commercial_dry_run(case.folder, case.cfg, case.media)
    assert plan['dry_run'] and plan['source_validated']
    assert plan['cost_estimate']['max_ocr_frames'] == 3
    assert plan['cost_estimate']['seconds'] is None
    assert plan['reused_stages']['04_transcription'] == 'snapshot'
    assert '13_ocr' in plan['reasons']
    assert case.calls == [] and not case.output.exists()
    assert snapshot_hashes(case.folder) == before
    case.media.write_bytes(b'mismatch')
    blocked = replay.commercial_dry_run(case.folder, case.cfg, case.media)
    assert blocked['status'] == 'BLOCKED' and not blocked['source_validated']
    assert 'SHA256' in blocked['dependencies_unavailable'][0]


@pytest.mark.parametrize('reason', ['disabled', 'failure'])
def test_disabled_and_failed_ocr_are_never_fake_execution(visual_case, reason, monkeypatch):
    case = visual_case
    before = snapshot_hashes(case.folder)
    if reason == 'disabled':
        case.runtime.update(available=False, reason='ocr_disabled')
    else:
        def fail(*a, **kw):
            case.calls.append('failed_attempt')
            raise RuntimeError('synthetic Tesseract failure')
        monkeypatch.setattr(sys.modules['pytesseract'], 'image_to_data', fail)
    result = case.run()
    assert result['analysis_status'] == 'blocked'
    receipt = read_json(case.output / 'reprocess_manifest.json')
    assert receipt['measurement_state'] == 'not_measured'
    assert receipt['ocr_evidence_sha256'] is None
    assert receipt['stages']['17c_commercial_visual']['stage_origin'] == ('not_executed' if reason == 'disabled' else 'actually_executed')
    assert len(case.calls) == (0 if reason == 'disabled' else 3)
    assert snapshot_hashes(case.folder) == before


def test_model_hash_invalidates_only_ocr_descendants(visual_case):
    case = visual_case
    case.runtime['language_model_sha256'] = {'por': 'a' * 64}
    first = case.run()
    case.runtime['language_model_sha256']['por'] = 'b' * 64
    second = case.run()
    assert len(case.calls) == 6
    assert 'params' in second['reprocess_manifest']['stages']['17c_commercial_visual']['invalidators']
    for name in ('04_transcription', '05_diarization', '15_semantic'):
        assert first['stage_status'][name] == second['stage_status'][name]


def test_runtime_recovers_local_traineddata_hash(tmp_path, monkeypatch):
    import types
    binary = tmp_path / 'tesseract.exe'
    binary.write_bytes(b'not executable; mock probe')
    data = tmp_path / 'tessdata'
    data.mkdir()
    model = data / 'eng.traineddata'
    model.write_bytes(b'synthetic language model')
    monkeypatch.delenv('TESSDATA_PREFIX', raising=False)
    monkeypatch.setattr(commercial_gate.shutil, 'which', lambda _: str(binary))
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(
        pytesseract=types.SimpleNamespace(tesseract_cmd=None),
        get_tesseract_version=lambda: 'mock', get_languages=lambda config: ['eng']))
    fingerprint = commercial_gate.ocr_runtime_fingerprint({'enabled': True, 'languages': 'eng'})
    assert fingerprint['language_model_sha256'] == {'eng': file_hash(model)}


def test_cli_dry_run_cannot_fall_into_full_pipeline(visual_case, monkeypatch, capsys):
    case = visual_case
    spec = importlib.util.spec_from_file_location('stage56_cli', Path(__file__).resolve().parents[2] / 'analyze.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'configure_path', lambda: None)
    from ldporto import config
    monkeypatch.setattr(config, 'load_config', lambda _: copy.deepcopy(case.cfg))
    monkeypatch.setattr(replay, 'replay_analysis', lambda *a: pytest.fail('dry-run executed replay'))
    monkeypatch.setattr(sys, 'argv', ['analyze.py', str(case.media), '--replay-analysis', str(case.folder),
                                     '--from-stage', 'commercial', '--dry-run', '--offline'])
    assert cli.main() in (0, 1)  # optional snapshot dependencies can be absent
    assert '"dry_run": true' in capsys.readouterr().out
    assert case.calls == [] and not case.output.exists()


def test_report_exports_audit_receipt_by_checksum(visual_case):
    case = visual_case
    case.cfg['export']['second_curation_auto'] = False
    case.monkeypatch.setattr(replay.ReportEngine, 'run', case.report_run)
    case.run()
    manifest = read_json(case.output / 'manifest.json')
    receipt = read_json(case.output / 'reprocess_manifest.json')
    assert manifest['artifact_checksums']['reprocess_manifest.json'] == file_hash(case.output / 'reprocess_manifest.json')
    assert receipt['report_analysis_status'] is not None
    assert receipt['stages']['17c_commercial_visual']['stage_origin'] == 'actually_executed'
