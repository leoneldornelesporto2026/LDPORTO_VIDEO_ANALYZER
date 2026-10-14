"""Headless GUI dispatch/status checks; subprocess/model execution is mocked."""
import builtins
import importlib.util
import json
from pathlib import Path
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('sol_v3_gui', ROOT/'app.py')
gui = importlib.util.module_from_spec(spec); spec.loader.exec_module(gui)


class Var:
    def __init__(self, value=''):
        self.value, self.owner = value, threading.get_ident()
    def get(self):
        assert threading.get_ident() == self.owner
        return self.value
    def set(self, value):
        assert threading.get_ident() == self.owner
        self.value = value


def application():
    app = gui.App.__new__(gui.App)
    app.proc, app.ocr_busy, app.smoke_busy, app.in_execution = None, False, False, False
    app.body_status, app.status = Var(), Var()
    app.start_button, app.stage_bar = Mock(), Mock()
    app.messages, app.window = queue.Queue(), SimpleNamespace(destroy=Mock())
    app.closing_requested, app.output_folder = False, None
    app.execution_frame, app.configuration_frame, app.final_frame = Mock(), Mock(), Mock()
    app.final_heading, app.final_summary, app.final_readiness, app.final_package = Var(), Var(), Var(), Var()
    app.progress_model = gui.WeightedProgress(clock=lambda: 0.)
    return app


def diagnostic_fixture():
    return {'configured_model': 'models/body/trusted.pt', 'resolved_model_path': 'C:/local/trusted.pt',
            'ultralytics_version': 'fixture-version', 'ultralytics_available': True,
            'model_validation_reason': None, 'model_loaded': False, 'inference_executed': False}


def configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(gui, 'ROOT', tmp_path)
    monkeypatch.setattr('ldporto.config.load_config', lambda *a: {'vision': {
        'body_backend': 'auto', 'yolo_model': 'models/body/trusted.pt', 'yolo_device': 'cpu'}})
    monkeypatch.setattr('ldporto.body_model_paths.body_model_diagnostics', lambda *a, **kw: diagnostic_fixture())


def test_body_dialog_is_passive_without_importing_or_executing_models(monkeypatch, tmp_path):
    configuration(monkeypatch, tmp_path)
    buttons, texts = {}, []
    class Widget:
        def __init__(self, *a, **kw):
            if 'text' in kw:
                texts.append(kw['text'])
            if 'command' in kw:
                buttons[kw['text']] = kw['command']
        def pack(self, **kw): pass
        def title(self, value): pass
        def destroy(self): pass
        def configure(self, **kw): texts.append(kw.get('text'))
    monkeypatch.setattr(gui.tk, 'Toplevel', Widget)
    monkeypatch.setattr(gui.tk, 'StringVar', lambda value: Var(value))
    for name in ('Label', 'Entry', 'Combobox', 'Button'):
        monkeypatch.setattr(gui.ttk, name, Widget)
    launch = Mock(); monkeypatch.setattr(gui.subprocess, 'Popen', launch)
    original_import = builtins.__import__
    def no_models(name, *a, **kw):
        if name.split('.')[0] in {'torch', 'ultralytics', 'cv2', 'faster_whisper'}:
            pytest.fail('passive dialog imported a model/inference dependency')
        return original_import(name, *a, **kw)
    monkeypatch.setattr(builtins, '__import__', no_models)
    app = application(); app.body_settings()
    assert any('Solicitado: models/body/trusted.pt' in text and 'Resolvido:' in text and 'fixture-version' in text and 'NOT_READY' in text for text in texts)
    assert 'Testar 4 quadros de video local' in buttons
    launch.assert_not_called()


@pytest.mark.parametrize('busy', ['process', 'smoke', 'ocr'])
def test_body_smoke_is_blocked_by_active_work(monkeypatch, busy):
    app = application()
    if busy == 'process': app.proc = SimpleNamespace(poll=lambda: None)
    elif busy == 'smoke': app.smoke_busy = True
    else: app.ocr_busy = True
    choose, launch = Mock(), Mock()
    monkeypatch.setattr(gui.filedialog, 'askopenfilename', choose)
    monkeypatch.setattr(gui.subprocess, 'Popen', launch)
    monkeypatch.setattr(gui.messagebox, 'showinfo', Mock())
    app.run_body_smoke()
    choose.assert_not_called(); launch.assert_not_called()


def test_cancel_body_video_selection_does_not_start_or_create_output(monkeypatch, tmp_path):
    configuration(monkeypatch, tmp_path)
    app = application(); launch = Mock()
    monkeypatch.setattr(gui.filedialog, 'askopenfilename', lambda **kw: '')
    monkeypatch.setattr(gui.subprocess, 'Popen', launch)
    app.run_body_smoke()
    launch.assert_not_called()
    assert not app.smoke_busy and not (tmp_path/'.cache').exists()


def test_explicit_body_worker_uses_script_unique_output_and_main_thread_status(monkeypatch, tmp_path):
    configuration(monkeypatch, tmp_path)
    video = tmp_path/'local video with spaces.mp4'; video.write_bytes(b'local fixture reference, not decoded')
    monkeypatch.setattr(gui.filedialog, 'askopenfilename', lambda **kw: str(video))
    threads, calls = [], []
    original_thread = threading.Thread
    def thread_factory(*a, **kw):
        thread = original_thread(*a, **kw); threads.append(thread); return thread
    monkeypatch.setattr(gui.threading, 'Thread', thread_factory)
    main_thread = threading.get_ident()
    class Process:
        def __init__(self, command, **kwargs):
            assert threading.get_ident() != main_thread
            calls.append((command, kwargs)); self.returncode = None
            output = Path(command[command.index('--output') + 1]); output.mkdir(parents=True, exist_ok=False)
            (output/'result.json').write_text(json.dumps({'backend': {'model_loaded': True,
                'inference_executed': True, 'inference_successful': True, 'local_smoke_validated': True}, 'frames': [{}, {}, {}, {}]}))
        def communicate(self, timeout=None): self.returncode = 0; return ('fixture subprocess only', None)
        def poll(self): return self.returncode
    monkeypatch.setattr(gui.subprocess, 'Popen', Process)
    app = application()
    for _ in range(2):
        app.run_body_smoke(); threads[-1].join(timeout=2)
        assert not threads[-1].is_alive()
        kind, result = app.messages.get_nowait()
        assert kind == 'body_smoke_result' and app.smoke_busy
        app.handle_body_smoke_result(result)
        assert not app.smoke_busy and 'INFERENCE_EXECUTED' in app.body_status.get()
        assert 'qualidade nao homologada' in app.body_status.get()
    outputs = [command[command.index('--output') + 1] for command, _ in calls]
    assert outputs[0] != outputs[1] and all(str(tmp_path/'.cache'/'body_smoke') in output for output in outputs)
    for command, kwargs in calls:
        assert str(tmp_path/'scripts/dev/smoke_body_detector.py') in command
        assert command[command.index('--video') + 1] == str(video.resolve())
        assert 'analyze.py' not in ' '.join(command) and not kwargs.get('shell', False)
        assert kwargs['env']['YOLO_OFFLINE'] == 'true' and kwargs['env']['YOLO_AUTOINSTALL'] == 'false'


@pytest.mark.parametrize('report', [{'backend': {'model_loaded': True}, 'frames': []},
                                  {'backend': {'model_loaded': False, 'inference_executed': False}, 'frames': [{}, {}, {}, {}]},
                                  {'backend': [], 'frames': 'malformed'}])
def test_loaded_file_or_malformed_report_cannot_become_smoke_ready(report):
    app = application(); app.smoke_busy = True
    app.handle_body_smoke_result({'output': 'new_output', 'exit_code': 0, 'report': report})
    assert 'NOT_READY' in app.body_status.get() and not app.smoke_busy


def test_stop_body_smoke_terminates_its_process_without_analysis_cancel_file(tmp_path):
    app = application(); app.output_folder = tmp_path
    app.body_smoke_busy, app.body_smoke_cancel = True, threading.Event()
    app.body_smoke_proc = SimpleNamespace(poll=lambda: None, terminate=Mock())
    app.stop()
    assert app.body_smoke_cancel.is_set()
    app.body_smoke_proc.terminate.assert_called_once()
    assert not (tmp_path/'CANCEL_REQUESTED').exists()


@pytest.mark.parametrize('backend_location', ['video_quality', 'analysis_performance'])
def test_completion_shows_real_backend_typed_causes_and_separate_review_states(tmp_path, backend_location):
    documents = {
        'second_curation_export.json': {'state': 'READY', 'candidate_count': 4, 'shortlist_count': 0,
            'readiness': {'editorial_ready': True, 'transcript_ready': True, 'camera_ready': False, 'preview_ready': None}},
        'quality_gate.json': {'status': 'P1_DEGRADED', 'preview_approved': False, 'publication_ready': False,
            'root_causes': [{'stage': '10_active_speaker', 'category': 'insufficient_evidence', 'reason_code': 'no_independent_evidence'}]},
        'source_audio_review.json': {'status': 'pending_human_audio_review', 'audio_verification_performed': False,
                                   'acoustic_multipass': {'asr_calls': 2}},
        'transcription_provenance.json': {'task': 'transcribe', 'text_kind': 'original_asr_hypothesis'},
        'translations.json': [{'segment_id': 'S1', 'target_language': 'pt', 'text': 'Traducao separada.'}],
    }
    backend = {'actually_executed_backend': 'hog', 'quality': 'degraded', 'inference_calls': {'hog': 50, 'yolo': 0},
               'model_loaded': False, 'inference_executed': False, 'readiness': 'NOT_READY', 'fallback_reason': 'yolo_local_model_missing'}
    if backend_location == 'video_quality': documents['video_analysis.json'] = {'quality': {'body_detection': backend}}
    else: documents['analysis.json'] = {'vision_performance': {'body_backend_execution': backend}}
    for name, document in documents.items(): (tmp_path/name).write_text(json.dumps(document), encoding='utf-8')
    app = application(); app.output_folder = tmp_path; app.show_completion()
    text = app.final_summary.get()
    assert 'P1_DEGRADED' in text and '10_active_speaker' in text and 'evidencia insuficiente' in text and 'no_independent_evidence' in text
    assert 'fala original (transcribe)' in text and 'traducoes separadas: 1' in text
    assert 'revisao humana do audio: pendente' in text and 'multipass ASR: 2 chamadas' in text
    assert 'backend real=hog' in text and 'YOLO carregado=nao' in text and '50' in app.body_status.get()
    readiness = app.final_readiness.get()
    assert 'Editorial: pronta para revisao' in readiness
    assert 'Preview aprovado: nao' in readiness and 'Publicacao pronta: nao' in readiness


def test_ready_legacy_package_does_not_imply_publication_or_audio_verification(tmp_path):
    (tmp_path/'second_curation_export.json').write_text(json.dumps({'state': 'READY', 'readiness': {'editorial_ready': True}}))
    app = application(); app.output_folder = tmp_path; app.show_completion()
    assert 'Publicacao pronta: nao registrada' in app.final_readiness.get()
    assert 'Preview aprovado: nao registrado' in app.final_readiness.get()
    assert 'origem nao registrada' in app.final_summary.get()
