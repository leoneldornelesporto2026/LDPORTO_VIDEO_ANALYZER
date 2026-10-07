from pathlib import Path, PureWindowsPath
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", [
    "CONFIGURAR_OLLAMA_MAXIMO_WINDOWS", "CORRIGIR_GPU_WINDOWS",
    "DIAGNOSTICO_GPU_WINDOWS", "DIAGNOSTICO_WINDOWS",
    "INSTALAR_AVANCADO_WINDOWS", "INSTALAR_WINDOWS", "TESTAR_WINDOWS",
])
def test_relocated_windows_entrypoints_preserve_root_and_arguments(name):
    wrapper = (ROOT / (name + ".bat")).read_text(encoding="utf-8-sig")
    match = re.search(r'call "%~dp0([^"\r\n]+)" %\*', wrapper, re.IGNORECASE)
    assert match is not None
    target = ROOT.joinpath(*PureWindowsPath(match.group(1)).parts)
    assert target.is_file()
    assert 'exit /b %errorlevel%' in wrapper.casefold()
    implementation = target.read_text(encoding="utf-8-sig")
    assert 'cd /d "%~dp0..\\..\\.."' in implementation
    assert "ollama stop" not in implementation.casefold()


def test_windows_root_resolution_does_not_depend_on_cwd(tmp_path):
    project = tmp_path / "Projeto com espacos"
    target = project / "scripts" / "windows" / "diagnostics"
    assert (target / ".." / ".." / "..").resolve() == project.resolve()


@pytest.mark.parametrize("group", ["dev", "diarization", "vision", "gpu-windows", "yolo", "ocr", "demucs", "audio-events"])
def test_optional_requirements_resolve_canonical_group_files(group):
    from ldporto.paths import optional_requirement
    assert optional_requirement(group).is_file()
    assert optional_requirement(group).parent == ROOT / "requirements"


def test_project_owned_paths_preserve_spaces_without_cwd_dependency(tmp_path):
    from ldporto.paths import project_path, optional_requirement
    project = tmp_path / "Fake Path" / "LDPORTO_VIDEO_ANALYZER"
    assert project_path("schemas", project) == project / "schemas"
    assert optional_requirement("vision", project) == project / "requirements" / "vision.txt"
    with pytest.raises(ValueError):
        optional_requirement("../credentials")


def test_visual_sampling_fingerprint_depends_only_on_consumed_speaker_times():
    from copy import deepcopy
    from ldporto.visual_sampling import speaker_sampling_fingerprint
    transcript = {"segments": [{"start": 0, "end": 2, "speaker": "S1", "text": "Literal."}]}
    first = speaker_sampling_fingerprint(transcript)
    changed = deepcopy(transcript)
    changed["segments"][0]["text"] = "Another literal."
    changed["quality_metrics"] = {"unrelated": True}
    assert speaker_sampling_fingerprint(changed) == first
    changed["segments"][0]["speaker"] = "S2"
    assert speaker_sampling_fingerprint(changed) != first


def test_structured_progress_is_weighted_and_not_stage_count():
    from ldporto.progress import WeightedProgress
    clock = [0.]
    model = WeightedProgress({'small': 1., 'semantic': 99.}, clock=lambda: clock[0])
    model.update({'stage': 'small', 'status': 'ok'})
    assert model.snapshot()['overall_fraction'] == .01
    model.update({'stage': 'semantic', 'status': 'running', 'current': 22, 'total': 46, 'elapsed_seconds': 0})
    assert model.snapshot()['stage_fraction'] == 22 / 46
    assert model.snapshot()['overall_fraction'] > .47


def test_eta_starts_calculating_then_uses_robust_samples():
    from ldporto.progress import WeightedProgress
    model = WeightedProgress({'semantic': 100.}, clock=lambda: 0.)
    model.update({'stage': 'semantic', 'status': 'running', 'current': 0, 'total': 10, 'elapsed_seconds': 0})
    assert model.snapshot()['eta_basis'] == 'calculating'
    for current in range(1, 5):
        model.update({'stage': 'semantic', 'status': 'running', 'current': current, 'total': 10, 'elapsed_seconds': current * 10})
    assert model.snapshot()['stage_eta_seconds'] == 60


def test_eta_reports_empirical_range_on_variable_unit_costs():
    from ldporto.progress import WeightedProgress
    model = WeightedProgress({'semantic': 100.}, clock=lambda: 0.)
    elapsed = 0
    model.update({'stage': 'semantic', 'status': 'running', 'current': 0, 'total': 20, 'elapsed_seconds': 0})
    for current, duration in enumerate([5, 50, 5, 50, 5, 50], 1):
        elapsed += duration
        model.update({'stage': 'semantic', 'status': 'running', 'current': current, 'total': 20, 'elapsed_seconds': elapsed})
    assert model.snapshot()['stage_eta_range_seconds'][1] > model.snapshot()['stage_eta_range_seconds'][0]


def test_run_completion_event_carries_package_path_and_finishes_progress():
    from ldporto.progress import WeightedProgress
    model = WeightedProgress()
    model.update({'event': 'run_completed', 'package_path': 'pacotes_para_enviar/SECOND_CURATION_READY_fixture.zip'})
    assert model.snapshot()['finished'] and model.snapshot()['overall_fraction'] == 1
    assert model.snapshot()['completion']['package_path'].endswith('.zip')


def test_context_emits_structured_stage_events_without_log_parsing(tmp_path):
    import logging
    from ldporto.core import Context, ok
    events = []
    ctx = Context(tmp_path / 'video.mp4', tmp_path, {'strict': False}, 'fixture', logging.getLogger('progress'), progress_callback=events.append)
    assert ctx.step('fixture', {}, lambda: ok({'value': 1}), code_files=['core.py'])['value'] == 1
    assert [event['status'] for event in events] == ['running', 'ok']
    assert (tmp_path / 'progress.jsonl').is_file()


def test_safe_cancel_preserves_saved_stage_checkpoint(tmp_path):
    import logging
    from ldporto.core import Context, RunCancelled, read_json, ok
    events = []
    ctx = Context(tmp_path / 'video.mp4', tmp_path, {'strict': False}, 'fixture', logging.getLogger('cancel'), progress_callback=events.append)
    def complete_unit():
        (tmp_path / 'CANCEL_REQUESTED').write_text('requested', encoding='ascii')
        return ok({'completed_unit': True})
    with pytest.raises(RunCancelled):
        ctx.step('fixture', {}, complete_unit, code_files=['core.py'])
    checkpoint = next(ctx.cache.glob('fixture.json'))
    assert read_json(checkpoint)['data']['completed_unit']
    assert events[-1]['status'] == 'cancelled'


def test_partial_tracking_is_a_causal_root_and_camera_source_fallback_is_explicit():
    from ldporto.run_status import build_run_manifest
    states = {'05_diarization': {'status': 'ok'}, '07_people_tracking': {'status': 'partial'},
              '08_person_reid': {'status': 'ok'}, '10_active_speaker': {'status': 'partial'},
              '12_camera_timeline': {'status': 'ok'}, '18b_global_camera_planner': {'status': 'ok'},
              '19_camera_director': {'status': 'partial'}}
    report = build_run_manifest({'sha256': 'fixture'}, states, [],
                                {'micro_track_ratio': .7, 'active_speaker_coverage': 0, 'source_preservation_fraction': 1})
    assert report['root_cause_stage'] == '07_people_tracking'
    assert '10_active_speaker' in report['degraded_descendants']
    assert report['stage_status']['19_camera_director']['fallback_used']
    assert report['stage_status']['19_camera_director']['status_model'] == 'DEGRADED'
    assert '05_diarization' in report['modules_still_valid']
    assert report['recommended_action'] != 'Nenhuma falha causal registrada.'


def test_ffmpeg_explicit_path_with_spaces_is_resolved_without_cwd(tmp_path):
    from ldporto.media_runtime import find_media_tool
    executable = tmp_path / 'Shared FFmpeg' / 'ffmpeg.exe'
    executable.parent.mkdir()
    executable.write_bytes(b'synthetic executable reference')
    assert Path(find_media_tool('ffmpeg', str(executable))) == executable


def test_torchcodec_unavailable_is_not_required_for_waveform_input():
    from ldporto.media_runtime import torchcodec_decoder_status
    probe = lambda: {'ok': False, 'error': 'synthetic missing decoder'}
    optional = torchcodec_decoder_status(False, probe)
    assert optional['state'] == 'decoder_unavailable_but_not_required'
    assert not optional['required']
    assert torchcodec_decoder_status(True, probe)['state'] == 'decoder_required_and_unavailable'


def test_windows_shared_dll_bootstrap_retains_handles(tmp_path, monkeypatch):
    from ldporto import media_runtime
    directory = tmp_path / 'Shared FFmpeg 7' / 'bin'
    directory.mkdir(parents=True)
    for filename in ('avcodec-61.dll', 'avformat-61.dll', 'avutil-59.dll'):
        (directory / filename).write_bytes(b'synthetic DLL reference')
    handle = object()
    monkeypatch.setattr(media_runtime.os, 'add_dll_directory', lambda path: handle, raising=False)
    monkeypatch.setattr(media_runtime, '_DLL_HANDLES', {})
    result = media_runtime.bootstrap_ffmpeg_shared(str(directory))
    if media_runtime.os.name == 'nt':
        assert result['handles_retained'] and result['handle_count'] >= 1
        assert media_runtime._DLL_HANDLES[str(directory.resolve())] is handle


def test_peak_process_memory_is_measured_not_a_fabricated_zero():
    from ldporto.runtime_metrics import resource_snapshot
    resources = resource_snapshot()
    assert resources['process_cpu_seconds'] >= 0
    assert resources['peak_process_memory_bytes'] is None or resources['peak_process_memory_bytes'] > 0
    if __import__('os').name == 'nt':
        assert resources['memory_measurement'] == 'windows_process_peak_working_set_not_gpu_vram'


def test_local_runtime_history_is_bounded_and_hardware_config_scoped(tmp_path):
    from ldporto.runtime_metrics import record_runtime_history
    from ldporto.core import read_json
    path = tmp_path / 'runtime_history.json'
    for index in range(55):
        record_runtime_history({'duration': 60, 'width': 1920, 'height': 1080}, {}, {'stage': {'elapsed_seconds': index}}, path)
    history = read_json(path)
    assert len(history['records']) == 50
    assert all(not record['telemetry_external'] for record in history['records'])


def test_native_execution_screen_receives_structured_stage_events_and_final_package(tmp_path, monkeypatch):
    import importlib.util
    import json
    import tkinter as tk
    spec = importlib.util.spec_from_file_location('v43_native_app', ROOT / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.App, 'refresh_ollama', lambda self: None)
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip('Tk display unavailable in headless test environment')
    window.withdraw()
    try:
        application = module.App(window)
        application.source.set('Synthetic episode')
        application.show_execution()
        application.handle_stage_event({'stage':'15_semantic', 'status':'running', 'current':22, 'total':46, 'elapsed_seconds':100})
        assert '22 / 46' in application.stage_text.get()
        assert application.overall_bar['value'] > 0
        application.output_folder = tmp_path
        package = tmp_path / 'SECOND_CURATION_READY_fixture.zip'
        package.write_bytes(b'synthetic package reference')
        (tmp_path / 'second_curation_export.json').write_text(json.dumps({'path':str(package), 'state':'READY', 'bytes':100,
            'candidate_count':3, 'shortlist_count':1, 'readiness':{'editorial_ready':True, 'visual_ready':True}}), encoding='utf-8')
        application.show_completion()
        assert str(package) in application.final_package.get()
        assert 'Editorial: pronta' in application.final_readiness.get()
    finally:
        window.destroy()


def replay_fixture(tmp_path, version='4.3.0'):
    from ldporto.core import write_json, file_hash
    folder = tmp_path / 'source'
    folder.mkdir()
    metadata = {'sha256': 'a' * 64, 'duration': 60, 'width': 1920, 'height': 1080, 'fps': 30,
                'analyzer_version': version, 'schema_version': '2.0', 'filename': 'fixture.mp4'}
    segments = [{'segment_id':'S1', 'start':0, 'end':60, 'speaker':None, 'text':'Nunca contei o segredo da gravacao musical.'}]
    words = [{'word_id':'W1', 'segment_id':'S1', 'start':0, 'end':1, 'word':'Nunca', 'confidence':.9}]
    files = {'words.json':words, 'transcript_segments.json':segments,
             'topics.json':[{'topic_id':'T1', 'start':0, 'end':60, 'topic':'Gravacao musical', 'method':'ollama', 'evidence_segment_ids':['S1']}],
             'editorial_moments.json':[{'moment_id':'M1', 'start':0, 'end':60, 'text':segments[0]['text'], 'categories':['hook'],
                                      'editorial':{'hook_strength':.8, 'clarity':.8}, 'standalone_class':'good', 'context_requirement':'none',
                                      'evidence_segment_ids':['S1'], 'complete_sentence':True}],
             'analysis_quality.json':{}, 'speakers.json':[], 'speaker_turns.json':[]}
    for name, data in files.items():
        write_json(folder / name, data)
    write_json(folder / 'analysis_summary.json', {'metadata':metadata, 'producer_version':version, 'stage_status':{}})
    write_json(folder / 'manifest.json', {'artifact_checksums':{name:file_hash(folder / name) for name in files}})
    return folder


def test_replay_compatibility_rejects_hash_and_corrupted_artifact(tmp_path):
    from ldporto.replay import ReplayArtifacts
    from ldporto.core import write_json
    folder = replay_fixture(tmp_path)
    with pytest.raises(ValueError, match='hash'):
        ReplayArtifacts(folder, expected_source_hash='wrong')
    reader = ReplayArtifacts(folder, expected_source_hash='a' * 64)
    assert reader.read('words.json')
    write_json(folder / 'words.json', [])
    with pytest.raises(ValueError, match='checksum'):
        reader.read('words.json')


def test_legacy_replay_requires_explicit_snapshot_permission(tmp_path):
    from ldporto.replay import ReplayArtifacts
    folder = replay_fixture(tmp_path, '4.2.0')
    with pytest.raises(ValueError, match='Legacy'):
        ReplayArtifacts(folder)
    assert ReplayArtifacts(folder, allow_legacy_snapshot=True).source_hash == 'a' * 64


def test_downstream_replay_does_not_run_asr_vision_or_llm(tmp_path):
    from ldporto.replay import replay_analysis
    from ldporto.config import load_config
    folder = replay_fixture(tmp_path)
    cfg = load_config()
    cfg['camera_director']['enabled'] = False
    cfg['preview']['enabled'] = False
    cfg['diarization']['enabled'] = False
    cfg['vision']['enabled'] = False
    cfg['export']['second_curation_output_dir'] = str(tmp_path / 'packages')
    output, analysis = replay_analysis(folder, cfg, 'understanding', tmp_path / 'output')
    assert not analysis['replay_provenance']['asr_rerun']
    assert not analysis['replay_provenance']['vision_rerun']
    assert not analysis['replay_provenance']['llm_rerun']
    assert analysis['second_curation_export']['path']


ROOT_ALLOWLIST = {
    '.gitignore', 'ABRIR_ANALYZER.bat', 'analyze.py', 'app.py', 'install.py',
    'README.md', 'requirements.txt', 'pytest.ini', 'CHANGELOG_V43.md',
    'compare_runs.py', 'exportar_ldporto.py', 'CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat',
    'CORRIGIR_GPU_WINDOWS.bat', 'DIAGNOSTICO_GPU_WINDOWS.bat', 'DIAGNOSTICO_WINDOWS.bat',
    'INSTALAR_AVANCADO_WINDOWS.bat', 'INSTALAR_WINDOWS.bat', 'TESTAR_WINDOWS.bat',
}


def test_repository_root_allowlist_excludes_generated_and_internal_files():
    root_files = {path.name for path in ROOT.iterdir() if path.is_file()}
    assert root_files <= ROOT_ALLOWLIST
    assert not any(name.startswith(('PROJECT_EXPORT_', 'WORK_PACKAGE_', 'CHATGPT_REVIEW_')) for name in root_files)


def test_legacy_python_entrypoints_are_thin_compatibility_wrappers():
    for name in ('compare_runs.py', 'exportar_ldporto.py'):
        source = (ROOT / name).read_text(encoding='utf-8-sig')
        assert 'Compatibility wrapper.' in source and 'Canonical implementation:' in source
        assert len(source.splitlines()) <= 15


def test_generated_runtime_media_and_secrets_are_not_present_as_tracked_source():
    import subprocess
    if not (ROOT / '.git').exists():
        pytest.skip('Git metadata intentionally absent from exported project package')
    files = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT,
                           check=True, capture_output=True, text=True).stdout.splitlines()
    forbidden = {'.mp4', '.wav', '.onnx', '.pt', '.pth', '.safetensors', '.zip'}
    actual = [name for name in files if (ROOT / name).exists()]
    assert not any(Path(name).suffix.lower() in forbidden for name in actual)
    assert not any(name.startswith(('analysis/', 'pacotes_para_enviar/', '.cache/', '.venv/', 'PROJECT_EXPORT_', 'WORK_PACKAGE_')) for name in actual)
    assert not any(Path(name).name in {'.env', 'HF_TOKEN', 'credentials.json'} for name in actual)


def test_compare_runs_does_not_claim_full_runtime_gain_from_downstream_replay(tmp_path):
    import compare_runs
    from ldporto.core import write_json
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir()
    new.mkdir()
    for path, scope, seconds in ((old, 'full_pipeline', 16000), (new, 'downstream_replay', 2)):
        write_json(path / 'analysis_summary.json', {'metadata':{'duration':60, 'sha256':'same', 'execution_scope':scope},
                   'stage_runtime':{'stage':{'elapsed_seconds':seconds}}, 'execution_scope':scope})
    report = compare_runs.compare_runs(old, new)
    assert report['same_source_confirmed']
    assert report['changes']['total_measured_stage_runtime_seconds']['delta'] is None
    assert report['changes']['total_measured_stage_runtime_seconds']['comparison_status'] == 'not_comparable_execution_scope'

def test_compare_runs_surfaces_v43_readiness_smart_zoom_and_handoff_metrics(tmp_path):
    import compare_runs
    from ldporto.core import write_json
    old, new = tmp_path / 'old_v42', tmp_path / 'new_v43'
    old.mkdir(); new.mkdir()
    write_json(old / 'analysis_summary.json', {'metadata': {'duration': 60, 'sha256': 'same'}, 'execution_scope': 'full_pipeline'})
    write_json(new / 'analysis_summary.json', {
        'metadata': {'duration': 60, 'sha256': 'same'}, 'execution_scope': 'full_pipeline',
        'analysis_quality': {'smart_zoom_enabled': True, 'zoom_event_count': 4, 'zoom_events_per_minute': 4.0,
                             'safe_zoom_fraction': .75, 'preview_zoom_validation_fraction': .5,
                             'candidate_topic_coverage': 1.0, 'candidate_audio_quality_coverage': .8,
                             'candidate_technical_quality_coverage': .9}})
    write_json(new / 'second_curation_export.json', {
        'bytes': 12345, 'file_count': 42, 'visual_count': 12, 'candidate_count': 108, 'state': 'READY',
        'validation': {'dangling_references': 0},
        'readiness': {'editorial_ready': True, 'transcript_ready': True, 'visual_ready': True,
                      'speaker_person_ready': False, 'camera_ready': False, 'preview_ready': True}})
    metrics = compare_runs.collect_run_metrics(new)['metrics']
    assert metrics['smart_zoom_enabled'] is True and metrics['zoom_event_count'] == 4
    assert metrics['safe_zoom_fraction'] == .75 and metrics['preview_zoom_validation_fraction'] == .5
    assert metrics['second_curation_package_bytes'] == 12345
    assert metrics['second_curation_dangling_refs'] == 0
    assert metrics['second_curation_editorial_ready'] is True
    assert metrics['second_curation_camera_ready'] is False
    report = compare_runs.compare_runs(old, new)
    assert report['changes']['zoom_event_count']['new'] == 4
    assert report['changes']['second_curation_package_bytes']['new'] == 12345


def test_native_execution_screen_handles_run_failed_without_stage(monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location('v43_native_app_run_failed', ROOT / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Var:
        def __init__(self):
            self.value = ''
        def set(self, value):
            self.value = value
        def get(self):
            return self.value

    application = object.__new__(module.App)
    application.progress_model = module.WeightedProgress()
    application.execution_diagnostic = Var()
    application.refresh_execution = lambda: None
    application.handle_stage_event({'event':'run_failed', 'status':'failed', 'cause':'falha sintetica'})
    assert application.execution_diagnostic.get() == 'Execucao: failed. falha sintetica'
