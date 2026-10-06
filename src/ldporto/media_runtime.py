"""Shared FFmpeg CLI discovery and Windows decoder DLL bootstrap."""
from pathlib import Path
import importlib
import os
import shutil

from .paths import PROJECT_ROOT, project_path


_DLL_HANDLES = {}


def find_media_tool(name, explicit=None):
    if name not in {'ffmpeg', 'ffprobe'}:
        raise ValueError('Unsupported media executable: ' + str(name))
    configured = explicit or os.environ.get('LDPORTO_' + name.upper())
    if configured:
        path = project_path(configured)
        return str(path.resolve()) if path.is_file() else None
    found = shutil.which(name)
    if found:
        return found
    executable = name + ('.exe' if os.name == 'nt' else '')
    shared = os.environ.get('LDPORTO_FFMPEG_SHARED') or os.environ.get('FFMPEG_SHARED_DIR')
    directories = [project_path(shared)] if shared else []
    directories += [PROJECT_ROOT / '.cache', PROJECT_ROOT / 'tools' / 'ffmpeg' / 'bin',
                    PROJECT_ROOT / '.cache' / 'ffmpeg_shared' / 'bin']
    if name == 'ffprobe':
        directories.append(PROJECT_ROOT / '.cache' / 'test_tools' / 'node_modules' / '@ffprobe-installer' / 'win32-x64')
    return next((str((directory / executable).resolve()) for directory in directories if (directory / executable).is_file()), None)


def bootstrap_ffmpeg_shared(explicit=None):
    if os.name != 'nt' or not hasattr(os, 'add_dll_directory'):
        return {'state': 'not_required_on_platform', 'directories': [], 'handle_count': 0}
    configured = explicit or os.environ.get('LDPORTO_FFMPEG_SHARED') or os.environ.get('FFMPEG_SHARED_DIR')
    candidates = [project_path(configured)] if configured else []
    executable = find_media_tool('ffmpeg')
    if executable:
        candidates.append(Path(executable).parent)
    candidates.extend(Path(value) for value in os.environ.get('PATH', '').split(os.pathsep) if value)
    candidates += [PROJECT_ROOT / '.cache' / 'ffmpeg_shared' / 'bin', PROJECT_ROOT / 'tools' / 'ffmpeg' / 'bin']
    selected = []
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        directory = candidate.resolve()
        if not all(any(directory.glob(pattern)) for pattern in ('avcodec-*.dll', 'avformat-*.dll', 'avutil-*.dll')):
            continue
        key = str(directory)
        if key not in _DLL_HANDLES:
            _DLL_HANDLES[key] = os.add_dll_directory(key)
        if key not in selected:
            selected.append(key)
    return {'state': 'shared_dll_directories_registered' if selected else 'shared_dlls_not_found',
            'directories': selected, 'handle_count': len(_DLL_HANDLES), 'handles_retained': True,
            'dll_version_compatibility': 'requires_actual_decoder_import'}


def torchcodec_decoder_status(required=False, probe=None):
    try:
        check = probe() if probe else {'ok': importlib.import_module('torchcodec.decoders') is not None}
    except Exception as exc:
        check = {'ok': False, 'error': type(exc).__name__}
    return {**check, 'required': required,
            'state': 'decoder_available' if check.get('ok') else 'decoder_required_and_unavailable' if required else 'decoder_unavailable_but_not_required',
            'input_contract': 'file_decoder' if required else 'in_memory_waveform_and_sample_rate',
            'decoder_needed_by_current_pipeline': required}