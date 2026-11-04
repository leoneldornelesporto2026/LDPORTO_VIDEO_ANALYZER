"""Headless local-media controls. No Tk window, pipeline, network or inference."""
import importlib.util
import json
from pathlib import Path
import queue
import threading
from unittest.mock import Mock

import pytest

from ldporto.core import file_hash
from test_r62_media_library import tiny_video


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('r62_media_gui', ROOT/'app.py')
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


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
    app.proc, app.media_busy, app.media_generation, app.media_check_result = None, False, 0, None
    app.source = Var('https://www.youtube.com/watch?v=9UCGZia2p1k')
    app.local_original, app.media_sha256, app.media_status = Var(), Var(), Var()
    app.allow_download = Var(False)
    app.start_button, app._start_checked = Mock(), Mock()
    app.messages = queue.Queue()
    return app


def test_cli_default_blocks_download_and_explicit_opt_in_keeps_source_identity():
    source = 'https://www.youtube.com/watch?v=9UCGZia2p1k'
    assert gui.media_cli_options(source) == []
    options = gui.media_cli_options(source, local_path='C:/synthetic/original.avi', expected_sha256='a'*64)
    assert options == ['--media-path', 'C:/synthetic/original.avi', '--media-sha256', 'a'*64]
    assert '--allow-download' in gui.media_cli_options(source, allow_download=True)
    assert '--allow-download' not in gui.media_cli_options('synthetic_local.avi', allow_download=True)


def test_integral_legacy_media_is_reused_independently_of_requested_download_height(tiny_video, tmp_path):
    vid = '9UCGZia2p1k'
    legacy = tmp_path/'input/youtube'/vid
    legacy.mkdir(parents=True)
    source = legacy/(vid+'.avi')
    source.write_bytes(tiny_video.read_bytes())
    sha = file_hash(source)
    (legacy/'download.json').write_text(json.dumps({'filename': source.name, 'max_height': 360, 'sha256': sha}), encoding='utf-8')
    result = gui.inspect_media_selection('https://youtu.be/'+vid, root=tmp_path,
        download_config={'max_height': 1080, 'media_library_root': str(tmp_path/'library')})
    assert result['status'] == 'FOUND_VERIFIED' and result['origin'] == 'legacy_input'
    assert result['source_sha256'] == sha and result['download_needed'] is False
    assert 'download desnecessário' in gui.media_selection_text(result)


def test_selected_original_is_sha_bound_and_retains_youtube_id(tiny_video, tmp_path):
    source = 'https://youtu.be/9UCGZia2p1k'
    result = gui.inspect_media_selection(source, root=tmp_path, local_path=str(tiny_video),
        expected_sha256=file_hash(tiny_video), download_config={'media_library_root': str(tmp_path/'library')})
    assert result['video_id'] == '9UCGZia2p1k' and result['origin'] == 'explicit_selection'
    with pytest.raises(ValueError, match='selected_media_hash_mismatch'):
        gui.inspect_media_selection(source, root=tmp_path, local_path=str(tiny_video),
            expected_sha256='0'*64, download_config={'media_library_root': str(tmp_path/'library')})


@pytest.mark.parametrize('status,allow,starts', [
    ('FOUND_VERIFIED', False, True), ('OPERATOR_SELECTION_REQUIRED', False, False),
    ('OPERATOR_SELECTION_REQUIRED', True, True), ('BLOCKED', True, False)])
def test_media_hash_worker_uses_main_thread_for_ui_and_honors_explicit_download_gate(monkeypatch, status, allow, starts):
    app = application()
    app.allow_download.set(allow)
    calls = []
    monkeypatch.setattr(gui, 'load_config', lambda *args: {'download': {}})
    def inspect(**kwargs):
        calls.append(threading.get_ident())
        return {'status': status, 'source_sha256': 'a'*64, 'error': 'SYNTHETIC_ERROR'}
    monkeypatch.setattr(gui, 'inspect_media_selection', inspect)
    app.verify_media(start_after=True)
    kind, value = app.messages.get(timeout=3)
    assert kind == 'media_result' and calls[0] != threading.get_ident()
    assert app.media_busy
    app.handle_media_result(value)
    assert not app.media_busy and bool(app._start_checked.call_count) is starts


def test_stale_selection_or_close_never_starts_processing():
    app = application()
    old = app.media_options()
    app.media_generation += 1
    app.handle_media_result((0, old, {'status': 'FOUND_VERIFIED'}, True))
    app._start_checked.assert_not_called()
    app.closing_requested = True
    app.handle_media_result((app.media_generation, old, {'status': 'FOUND_VERIFIED'}, True))
    app._start_checked.assert_not_called()


def test_changing_source_revokes_download_choice_and_previous_original_reference():
    app = application()
    app.allow_download.set(True)
    app.local_original.set('C:/synthetic/previous_original.avi')
    app.media_check_result = ({}, {'status': 'FOUND_VERIFIED'})
    app.change_media_selection(clear_original=True)
    assert app.allow_download.get() is False and app.local_original.get() == ''
    assert app.media_check_result is None


def test_hash_mismatch_stays_blocked_even_with_download_checkbox_enabled(monkeypatch):
    app = application()
    app.allow_download.set(True)
    app.launch = Mock()
    app.media_check_result = (app.media_options(), {'status': 'BLOCKED', 'error': 'selected_media_hash_mismatch'})
    monkeypatch.setattr(gui.messagebox, 'showinfo', Mock())
    gui.App._start_checked(app)
    app.launch.assert_not_called()
    assert not hasattr(app, 'output_folder')
