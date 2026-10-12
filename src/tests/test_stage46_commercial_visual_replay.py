"""Stage 46: synthetic media, real targeted_ocr loop, mocked decode/Tesseract only."""
import copy
import hashlib
import sys
import types

import numpy as np
import pytest

from ldporto import replay, commercial_gate
from ldporto.config import load_config
from ldporto.core import read_json, write_json, file_hash, digest
from test_v43_runtime import replay_fixture


@pytest.fixture
def visual_case(tmp_path, monkeypatch):
    from ocr_test_support import mock_ocr_runtime
    mock_ocr_runtime(monkeypatch)
    folder = replay_fixture(tmp_path)
    media = tmp_path / 'synthetic.media'
    media.write_bytes(b'LDPORTO stage46 synthetic media fixture\x00')
    summary = read_json(folder / 'analysis_summary.json')
    summary['metadata']['sha256'] = hashlib.sha256(media.read_bytes()).hexdigest()
    write_json(folder / 'analysis_summary.json', summary)
    candidates = read_json(folder / 'editorial_moments.json')
    candidates[0]['commercial_classification'] = {'eligibility': 'eligible'}
    candidates[0]['default_shortlist_eligible'] = True
    write_json(folder / 'main_moments.json', candidates)
    # A valid, explicitly synthetic source-frame timeline makes the cheap planner
    # cacheable; unavailable planner runs otherwise rewrite elapsed_seconds.
    write_json(folder / 'camera_timeline.json', [{'start': 0., 'end': 60.,
        'shot_id': 'synthetic', 'shot_type': 'wide', 'active_person': None}])
    manifest = read_json(folder / 'manifest.json')
    manifest['artifact_checksums']['main_moments.json'] = file_hash(folder / 'main_moments.json')
    manifest['artifact_checksums']['camera_timeline.json'] = file_hash(folder / 'camera_timeline.json')
    write_json(folder / 'manifest.json', manifest)
    cfg = load_config()
    cfg['camera_director']['enabled'] = False
    cfg['preview']['enabled'] = False
    cfg['ocr']['enabled'] = True
    cfg['export']['second_curation_output_dir'] = str(tmp_path / 'packages')
    runtime = {'available': True, 'enabled': True, 'executable': 'synthetic_tesseract',
               'executable_sha256': 'b' * 64, 'version': 'mock-46',
               'available_languages': ['eng', 'por'], 'requested_languages': 'por+eng'}
    monkeypatch.setattr(commercial_gate, 'ocr_runtime_fingerprint', lambda _: copy.deepcopy(runtime))
    report_run = replay.ReportEngine.run
    monkeypatch.setattr(replay.ReportEngine, 'run', lambda *args: None)
    def forbidden(*args, **kwargs):
        raise AssertionError('expensive stage called in commercial visual replay')
    monkeypatch.setattr(replay, 'run_understanding', forbidden)
    monkeypatch.setattr(replay.SemanticEngine, 'run', forbidden)
    from ldporto.transcription import TranscriptionEngine
    from ldporto.diarization import DiarizationEngine
    from ldporto.vision import VisionEngine
    monkeypatch.setattr(TranscriptionEngine, 'run', forbidden)
    monkeypatch.setattr(DiarizationEngine, 'run', forbidden)
    monkeypatch.setattr(VisionEngine, 'run', forbidden)
    import cv2
    class Capture:
        def __init__(self, path):
            assert path == str(media)
        def isOpened(self): return True
        def set(self, *_): pass
        def read(self): return True, np.zeros((100, 200, 3), dtype=np.uint8)
        def release(self): pass
    monkeypatch.setattr(cv2, 'VideoCapture', Capture)
    calls = []
    def recognize(*args, **kwargs):
        calls.append(kwargs['lang'])
        return {'text': ['50% OFF'], 'conf': ['90'], 'block_num': [1], 'par_num': [1],
                'line_num': [1], 'left': [20], 'top': [65], 'width': [70], 'height': [18]}
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(
        Output=types.SimpleNamespace(DICT='dict'), TesseractError=RuntimeError,
        get_tesseract_version=lambda: 'mock-46', image_to_data=recognize))
    output = tmp_path / 'replayed'
    def run(stage='commercial_visual', source=media):
        return replay.replay_analysis(folder, cfg, stage, output, source)[1]
    return types.SimpleNamespace(folder=folder, media=media, output=output, cfg=cfg,
                                 runtime=runtime, calls=calls, run=run, monkeypatch=monkeypatch, report_run=report_run)


@pytest.mark.parametrize('stage', replay.COMMERCIAL_STAGES)
def test_real_17c_loop_aliases_and_grounded_classification(visual_case, stage):
    case = visual_case
    first = case.run(stage)
    assert len(case.calls) == 3
    assert first['stage_status']['17c_commercial_visual']['status'] == 'ok'
    assert first['main_moments'][0]['commercial_classification']['eligibility'] == 'review'
    assert first['editorial_shortlist'] == []
    assert first['ocr_text'][0]['source_sha256'] == file_hash(case.media)
    assert len(first['ocr_text'][0]['decoded_frame_sha256']) == 64
    assert len(first['commercial_visual_s8']['frame_resources']) == 3
    assert first['commercial_visual_s8']['ocr_runtime'] == case.runtime
    assert first['semantic_metrics']['semantic_inference_call_count'] == 0
    assert all(first['replay_provenance'][k] is False for k in ('asr_rerun', 'vision_rerun', 'llm_rerun'))
    plan = first['replay_provenance']['replay_plan']
    assert '16_understanding' not in plan['stages_to_check']
    assert plan['stage_dispositions']['16_understanding'] == 'snapshot_reused'
    assert plan['stage_dispositions']['04_transcription'] == 'snapshot_reused'
    assert plan['stage_dispositions']['08_person_reid'] == 'not_available'
    assert first['stage_status']['08_person_reid']['status'] == 'partial'
    assert first['stage_status']['17d_targeted_asr']['status'] == 'skipped'
    assert not first.get('publish_ready')
    second = case.run(stage)
    assert len(case.calls) == 3
    assert second['stage_runtime']['17c_commercial_visual']['cache_hit']
    assert second['stage_runtime']['17e_subtitle_review_s7']['cache_hit']
    assert second['stage_runtime']['19_camera_director']['cache_hit']


@pytest.mark.parametrize('change', ['config', 'runtime', 'upstream', 'cache_checksum', 'algorithm'])
def test_cache_miss_only_reprocesses_descendants(visual_case, change):
    case = visual_case
    first = case.run()
    if change == 'config':
        case.cfg['ocr']['languages'] = 'eng'
    elif change == 'runtime':
        case.runtime['version'] = 'mock-47'
    elif change == 'upstream':
        rows = read_json(case.folder / 'main_moments.json')
        rows[0]['ideal_end'] = 45
        write_json(case.folder / 'main_moments.json', rows)
        manifest = read_json(case.folder / 'manifest.json')
        manifest['artifact_checksums']['main_moments.json'] = file_hash(case.folder / 'main_moments.json')
        write_json(case.folder / 'manifest.json', manifest)
    elif change == 'algorithm':
        from ldporto import core
        original = core.file_hash
        case.monkeypatch.setattr(core, 'file_hash', lambda path: 'changed-code' if str(path).endswith('ocr.py') else original(path))
    else:
        cache = next(case.output.glob('cache/*/17c_commercial_visual.json'))
        data = read_json(cache)
        data['data']['texts'][0]['text'] = 'tampered'
        write_json(cache, data)  # Keep old data_checksum: real corruption.
    second = case.run()
    assert len(case.calls) == 6
    assert not second['stage_runtime']['17c_commercial_visual']['cache_hit']
    assert not second['stage_runtime']['17e_subtitle_review_s7']['cache_hit'] or change == 'cache_checksum'
    for stage in ('04_transcription', '15_semantic', '16_understanding'):
        assert second['stage_status'][stage] == first['stage_status'][stage]
    assert not list(case.output.glob('cache/*/04_transcription.json'))
    assert not list(case.output.glob('cache/*/15_semantic.json'))
    assert not list(case.output.glob('cache/*/16_understanding.json'))


@pytest.mark.parametrize('reason', ['missing', 'mismatch', 'disabled', 'binary', 'languages', 'traversal'])
def test_support_absent_returns_blocked_before_ocr(visual_case, reason):
    case = visual_case
    source = case.media
    if reason == 'missing': source = None
    elif reason == 'mismatch': case.media.write_bytes(b'different synthetic media')
    elif reason == 'traversal': source = case.media.parent / 'missing' / '..' / case.media.name
    else:
        case.runtime.update(available=False, reason={'disabled': 'ocr_disabled', 'binary': 'tesseract_binary_missing',
                                                    'languages': 'tesseract_languages_missing'}[reason])
    result = case.run(source=source)
    assert result['analysis_status'] == 'blocked'
    assert result['stage_status']['17c_commercial_visual']['status'] == 'blocked'
    assert result['commercial_present'] is None
    assert case.calls == []
    assert (case.output / 'replay_blocked.json').is_file()
    assert 'SHA-256' in result['instruction']
    assert not (case.output / 'analysis.json').exists()


def test_cross_source_cached_ocr_is_blocked_even_with_consistent_data_checksum(visual_case):
    case = visual_case
    case.run()
    cache = next(case.output.glob('cache/*/17c_commercial_visual.json'))
    data = read_json(cache)
    data['data']['source_sha256'] = 'f' * 64
    data['data_checksum'] = digest(data['data'])
    write_json(cache, data)
    result = case.run()
    assert result['analysis_status'] == 'blocked'
    assert result['commercial_visual_s8']['reason'] == 'cached_ocr_source_hash_mismatch'
    assert len(case.calls) == 3


def test_artifact_corruption_and_traversal_are_rejected(visual_case):
    case = visual_case
    manifest = read_json(case.folder / 'manifest.json')
    manifest['artifact_checksums']['review_evidence/../main_moments.json'] = 'f' * 64
    write_json(case.folder / 'manifest.json', manifest)
    with pytest.raises(ValueError, match='traversal'):
        case.run()
    del manifest['artifact_checksums']['review_evidence/../main_moments.json']
    write_json(case.folder / 'manifest.json', manifest)
    write_json(case.folder / 'main_moments.json', [])
    with pytest.raises(ValueError, match='checksum mismatch'):
        case.run()
    assert case.calls == []


def test_symlink_media_and_parent_artifacts_rejected(visual_case, tmp_path):
    case = visual_case
    link = tmp_path / 'media_link'
    try:
        link.symlink_to(case.media)
    except OSError:
        pytest.skip('Windows symlink privilege unavailable; reparse check needs local homologation')
    assert case.run(source=link)['analysis_status'] == 'blocked'
    directory = tmp_path / 'snapshot_link'
    directory.symlink_to(case.folder, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        replay.ReplayArtifacts(directory)
    assert case.calls == []


def test_missing_candidates_blocks_and_decode_failure_never_reports_ok(visual_case):
    case = visual_case
    (case.folder / 'main_moments.json').unlink()
    assert case.run()['analysis_status'] == 'blocked'
    assert case.calls == []


def test_runtime_probe_reports_binary_hash_and_missing_languages(tmp_path, monkeypatch):
    binary = tmp_path / 'fake_tesseract.exe'
    binary.write_bytes(b'synthetic-executable-not-run')
    monkeypatch.setattr(commercial_gate.shutil, 'which', lambda _: str(binary))
    api = types.SimpleNamespace(tesseract_cmd=None)
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(pytesseract=api,
        get_tesseract_version=lambda: 'mock-46', get_languages=lambda config: ['eng']))
    result = commercial_gate.ocr_runtime_fingerprint({'enabled': True, 'languages': 'por+eng'})
    assert not result['available'] and result['missing_languages'] == ['por']
    assert result['executable_sha256'] == file_hash(binary)
    assert result['version'] == 'mock-46'
    assert commercial_gate.ocr_runtime_fingerprint({'enabled': True, 'languages': 'eng'})['available']
    assert commercial_gate.ocr_runtime_fingerprint({'enabled': False})['reason'] == 'ocr_disabled'


def test_report_export_preserves_receipts_and_original_snapshot(visual_case):
    case = visual_case
    originals = {p.name: file_hash(p) for p in case.folder.iterdir() if p.is_file()}
    case.cfg['export']['second_curation_auto'] = False  # JSON reexport, no delivery ZIP.
    case.monkeypatch.setattr(replay.ReportEngine, 'run', case.report_run)
    result = case.run()
    assert {p.name: file_hash(p) for p in case.folder.iterdir() if p.is_file()} == originals
    receipt = read_json(case.output / 'commercial_visual_s8.json')
    assert receipt['source_sha256'] == file_hash(case.media)
    document = read_json(case.output / 'analysis.json')
    reference = document['collection_refs']['commercial_visual_s8']
    assert reference['sha256'] == file_hash(case.output / reference['path'])
    summary = read_json(case.output / 'analysis_summary.json')
    assert summary['stage_status']['17c_commercial_visual']['status'] == 'ok'
    assert not result.get('publish_ready')


def test_decoder_failure_blocks_without_simulating_ocr(visual_case):
    case = visual_case
    import cv2
    class Capture:
        def __init__(self, *_): pass
        def isOpened(self): return False
        def release(self): pass
    case.monkeypatch.setattr(cv2, 'VideoCapture', Capture)
    result = case.run()
    assert result['analysis_status'] == 'blocked'
    assert result['commercial_visual_s8']['reason'] == 'video_decode_unavailable'
    assert case.calls == []


@pytest.mark.parametrize('link_kind', ['symlink_component', 'windows_reparse'])
def test_link_components_rejected_without_windows_privileges(tmp_path, monkeypatch, link_kind):
    from pathlib import Path
    directory = tmp_path / 'synthetic_link'
    directory.mkdir()
    if link_kind == 'symlink_component':
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda self: self == directory or original(self))
    else:
        original = Path.stat
        class ReparseStat:
            st_file_attributes = 0x400
            def __init__(self, actual): self.actual = actual
            def __getattr__(self, key): return getattr(self.actual, key)
        monkeypatch.setattr(Path, 'stat', lambda self, *a, **kw:
            ReparseStat(original(self, *a, **kw)) if self == directory else original(self, *a, **kw))
    with pytest.raises(ValueError, match='symlink/reparse'):
        replay.safe_replay_path(directory / 'image.json')


@pytest.mark.parametrize('blocked', [False, True])
def test_cli_reports_blocked_or_json_export_without_delivery_zip(visual_case, monkeypatch, capsys, blocked):
    import importlib.util
    from pathlib import Path
    case = visual_case
    spec = importlib.util.spec_from_file_location('stage46_cli', Path(__file__).resolve().parents[2] / 'analyze.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'configure_path', lambda: None)
    case.cfg['export']['second_curation_auto'] = False
    from ldporto import config
    monkeypatch.setattr(config, 'load_config', lambda path: copy.deepcopy(case.cfg))
    if blocked:
        case.runtime.update(available=False, reason='tesseract_binary_missing')
    else:
        monkeypatch.setattr(replay.ReportEngine, 'run', case.report_run)
    monkeypatch.setattr(sys, 'argv', ['analyze.py', str(case.media), '--replay-analysis', str(case.folder),
        '--from-stage', '17c_commercial_visual', '--output', str(case.output), '--offline'])
    assert cli.main() == (1 if blocked else 0)
    text = capsys.readouterr().out
    assert ('Replay bloqueado: tesseract_binary_missing' if blocked else 'Relatorios JSON reexportados') in text
    assert not list(case.output.glob('*.zip'))
    assert not list(case.output.parent.glob('packages/*.zip'))


def test_conflicting_checksums_and_metadata_checksum_rejected(visual_case):
    case = visual_case
    # A reference cannot override a different manifest checksum.
    write_json(case.folder / 'analysis.json', {'metadata': read_json(case.folder / 'analysis_summary.json')['metadata'],
        'collection_refs': {'main_moments': {'path': 'main_moments.json', 'sha256': 'f' * 64}}})
    with pytest.raises(ValueError, match='Conflicting'):
        case.run()
    (case.folder / 'analysis.json').unlink()
    manifest = read_json(case.folder / 'manifest.json')
    manifest['artifact_checksums']['analysis_summary.json'] = file_hash(case.folder / 'analysis_summary.json')
    write_json(case.folder / 'manifest.json', manifest)
    summary = read_json(case.folder / 'analysis_summary.json')
    summary['metadata']['duration'] = 61
    write_json(case.folder / 'analysis_summary.json', summary)
    with pytest.raises(ValueError, match='checksum mismatch'):
        case.run()
