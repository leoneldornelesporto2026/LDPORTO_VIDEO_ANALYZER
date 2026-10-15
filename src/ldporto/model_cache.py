"""Resolve existing pipeline assets without a network request or model inference."""
from pathlib import Path

from .config import asset_path


def cached_pipeline_snapshot(model):
    local = asset_path(model)
    if local.is_dir():
        snapshot = local
    else:
        try:
            from huggingface_hub import snapshot_download
            snapshot = Path(snapshot_download(model, local_files_only=True))
        except Exception:
            return None
    configs = (snapshot / 'config.yaml').is_file()
    weights = any(path.is_file() and path.stat().st_size > 0
                  for pattern in ('*.bin', '*.safetensors')
                  for path in snapshot.rglob(pattern))
    return snapshot if configs and weights else None


# The GUI canary, preflight and actual ASR must use the same local CTranslate2 assets.
def cached_whisper_snapshot(model):
    """Resolve *complete* local faster-whisper assets without accessing the network.

    The canonical Hugging Face snapshot cache is preferred for named models.
    An incomplete legacy models/whisper download is never considered READY.
    """
    required = ('model.bin', 'config.json', 'tokenizer.json')

    def complete(path):
        return (path.is_dir() and all(
            (path / name).is_file() and (path / name).stat().st_size > 0
            for name in required
        ))

    explicit = asset_path(model)
    if complete(explicit):
        return explicit

    try:
        from faster_whisper.utils import download_model
        # local_files_only guarantees there is NO network request or new download.
        # Do not provide output_dir: that previously redirected the lookup to the
        # incomplete models/whisper folder, ignoring the valid HF snapshot cache.
        snapshot = Path(download_model(model, local_files_only=True, use_auth_token=False))
    except Exception:
        # No cache must be reported as unavailable; never auto-download.
        return None
    return snapshot if complete(snapshot) else None
