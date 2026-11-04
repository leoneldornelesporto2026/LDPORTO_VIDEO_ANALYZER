"""Local body-model paths and passive diagnostics; no model imports or downloads."""
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
import hashlib
import os
import sys
import tempfile

from .config import ROOT

_private_settings = None


def _linked_path(path):
    return any(p.is_symlink() or (p.exists() and getattr(p.lstat(), 'st_file_attributes', 0) & 1024)
               for p in (path, *path.parents))


def configure_local_yolo_privacy():
    """Only the explicit loader calls this; preserve the user's settings on disk."""
    global _private_settings
    if _private_settings is None:
        _private_settings = tempfile.TemporaryDirectory(prefix='ldporto_yolo_local_')
    os.environ['YOLO_CONFIG_DIR'] = _private_settings.name
    os.environ['YOLO_OFFLINE'] = 'true'
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    for name in ('ultralytics', 'ultralytics.utils'):
        module = sys.modules.get(name)
        if module is None:
            continue
        if hasattr(module, 'ONLINE'):
            module.ONLINE = False
        settings = getattr(module, 'SETTINGS', None)
        if isinstance(settings, dict):
            # SettingsManager.__setitem__/update persist to the user's file.
            # Alter only this process's dict, bypassing their disk-writing hooks.
            dict.__setitem__(settings, 'sync', False)
            dict.__setitem__(settings, 'hub', False)
    events_module = sys.modules.get('ultralytics.utils.events')
    events = getattr(events_module, 'events', None)
    if events is not None:
        events.enabled = False
    return {'telemetry_enabled': False, 'offline_model_policy': True,
            'settings_scope': 'temporary_process_private_directory',
            'user_settings_modified': False}


def select_body_model_path(value, root=None):
    root = Path(root or ROOT).resolve()
    configured = Path(value).expanduser()
    configured = configured if configured.is_absolute() else root / configured
    preferred = root / 'models' / 'body' / configured.name
    legacy = root / configured.name
    selected, reason = configured, 'configured_path'
    # Only the identical filename in the old root location is compatible. An
    # existing configured asset always wins, including invalid assets that must
    # be rejected by the loader instead of silently replaced with another file.
    if configured == preferred and not configured.exists() and not _linked_path(configured) and legacy.is_file():
        selected, reason = legacy, 'legacy_root_compatibility'
    return selected, {'configured_model': str(value), 'configured_model_path': str(configured),
                      'resolved_model_path': str(selected.resolve()),
                      'preferred_model_path': str(preferred),
                      'path_resolution': reason, 'legacy_compatibility_used': selected != configured}


def body_model_diagnostics(cfg, root=None):
    """Inspect configuration/file/dependency metadata without loading any weights."""
    path, selection = select_body_model_path(cfg['yolo_model'], root)
    try:
        dependency_version = version('ultralytics')
    except PackageNotFoundError:
        dependency_version = None
    reason = None
    if not path.is_file():
        reason = 'missing_file'
    elif path.suffix.lower() != '.pt':
        reason = 'unsupported_format'
    elif path.stat().st_size == 0:
        reason = 'empty_file'
    elif any(p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & 1024
             for p in (path, *path.parents)):
        reason = 'link_or_reparse_point'
    checksum = None
    if reason is None:
        try:
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1048576), b''):
                    digest.update(chunk)
            checksum = digest.hexdigest()
        except OSError:
            reason = 'file_read_error'
    return {**selection, 'schema_version': '1.0', 'diagnostic_scope': 'passive_local_metadata',
            'expected_model_format': '.pt', 'expected_model_task': 'detect',
            'expected_person_class': {'id': 0, 'name': 'person'},
            'model_validation_reason': reason, 'ultralytics_available': dependency_version is not None,
            'model_sha256': checksum,
            'ultralytics_version': dependency_version, 'device_requested': cfg.get('yolo_device', 'cpu'),
            'model_loaded': False, 'inference_executed': False, 'inference_successful': False,
            'readiness': 'NOT_READY', 'local_smoke_validated': None,
            'weights_provenance': 'not_verified_by_passive_diagnostic',
            'license_status': 'requires_weight_provenance_and_license_review',
            'allow_model_downloads': False, 'allow_dependency_install': False,
            'next_action': ('provide_trusted_local_pt_and_explicit_model_path' if reason else
                            'install_optional_dependency_only_with_explicit_consent' if dependency_version is None else
                            'explicit_model_load_then_bounded_local_inference')}
