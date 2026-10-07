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
