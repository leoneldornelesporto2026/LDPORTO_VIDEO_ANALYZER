"""Runtime must accept the same complete HF cache as its readiness gate."""
from contextlib import nullcontext
from types import SimpleNamespace
import sys

import numpy as np
import pytest

from ldporto.config import load_config
from ldporto.core import Unavailable
from ldporto import diarization, media_runtime


def runtime_fixture(tmp_path, monkeypatch, cached):
    import huggingface_hub
    cfg = load_config()
    cfg['device'] = 'cpu'
    cfg['offline'] = False
    cfg['diarization']['model'] = 'fixture/community-1'
    cfg['diarization']['import_file'] = None
    for name in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'config.yaml').write_text('pipeline: fixture', encoding='utf-8')
    if cached:
        (snapshot / 'pytorch_model.bin').write_bytes(b'fixture')
    def local_snapshot(model, **kwargs):
        assert model == cfg['diarization']['model']
        assert kwargs == {'local_files_only': True}
        return str(snapshot)
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', local_snapshot)
    monkeypatch.setattr(media_runtime, 'bootstrap_ffmpeg_shared', lambda *args: None)
    annotation = SimpleNamespace(itertracks=lambda **kwargs: iter([
        (SimpleNamespace(start=0.1, end=1.8), None, 'model_speaker')]))
    calls = []
    class FixturePipeline:
        @staticmethod
        def from_pretrained(model, token=None):
            calls.append((model, token))
            return FixturePipeline()
        def to(self, device):
            pass
        def __call__(self, audio, **kwargs):
            return annotation
    monkeypatch.setitem(sys.modules, 'pyannote.audio', SimpleNamespace(Pipeline=FixturePipeline))
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False), device=lambda value: value,
        inference_mode=nullcontext,
        from_numpy=lambda value: SimpleNamespace(unsqueeze=lambda axis: value)))
    monkeypatch.setattr(diarization.sf, 'read', lambda *args, **kwargs: (np.zeros(32000), 16000))
    monkeypatch.setattr(diarization, 'diarization_capabilities', lambda cfg: {})
    return SimpleNamespace(config=cfg), calls


def test_complete_hf_cache_runs_without_token(tmp_path, monkeypatch):
    ctx, calls = runtime_fixture(tmp_path, monkeypatch, cached=True)
    result = diarization.DiarizationEngine().run(ctx, {'mono': 'fixture.wav'}, {'duration': 2})
    assert calls == [('fixture/community-1', None)]
    assert result['data']['speaker_count'] == 1
    assert result['data']['turns'][0]['speaker'] == 'SPEAKER_00'
    assert result['data']['turns'][0]['confidence'] is None


def test_incomplete_hf_cache_is_not_claimed_as_available(tmp_path, monkeypatch):
    ctx, calls = runtime_fixture(tmp_path, monkeypatch, cached=False)
    with pytest.raises(Unavailable):
        diarization.DiarizationEngine().run(ctx, {'mono': 'fixture.wav'}, {'duration': 2})
    assert calls == []
