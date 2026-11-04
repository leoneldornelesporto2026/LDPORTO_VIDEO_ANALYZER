"""Offline report must preserve missing proof and avoid runtime services."""
from ldporto import homologation_s11 as h


def test_offline_runtime_never_uses_service_or_gpu_diagnostics(monkeypatch):
    def forbidden():
        raise AssertionError('runtime services must not be inspected offline')
    monkeypatch.setattr(h, '_runtime_checks', forbidden)
    monkeypatch.setattr(h.shutil, 'which', lambda name: None)
    report = h.homologate(offline=True)
    assert report['runtime']['gpu']['available'] is None
    assert report['runtime']['ollama_local']['reachable'] is None
    assert report['runtime']['ffmpeg_encoder_libx264'] is False
    assert report['release_status'] == 'BLOCKED_OR_PENDING'
    assert report['editorial_human_approval'] is False
    assert report['ready_to_publish'] is False
    assert 'HUMAN_EDITORIAL_REVIEW_PENDING' in report['blockers']
    assert report['comparable_metric_deltas'] == {}


def test_offline_encoder_failure_does_not_imply_success(monkeypatch):
    monkeypatch.setattr(h.shutil, 'which', lambda name: 'fixture-' + name)
    class Result:
        returncode = 1
        stdout = 'libx264'
    monkeypatch.setattr(h.subprocess, 'run', lambda *a, **kw: Result())
    assert h._offline_runtime_checks()['ffmpeg_encoder_libx264'] is False
