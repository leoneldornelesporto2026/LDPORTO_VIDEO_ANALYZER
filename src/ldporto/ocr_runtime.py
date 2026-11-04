"""One executable/language configuration, with serialized pytesseract calls."""
import importlib
import os
from pathlib import Path
import re
import shutil
import threading

_LOCK = threading.RLock()


def languages(cfg):
    parts = str(cfg.get('languages', 'por+eng')).split('+')
    if not parts or any(not re.fullmatch(r'[A-Za-z0-9_]+', part) for part in parts):
        raise ValueError('invalid_languages')
    return '+'.join(parts)


def resolve_executable(cfg):
    command = str(cfg.get('tesseract_cmd') or 'tesseract')
    resolved = shutil.which(command)
    executable = Path(resolved).resolve() if resolved else None
    if (not executable or not executable.is_file() or not os.access(executable, os.X_OK)
            or (os.name == 'nt' and executable.suffix.casefold() != '.exe')):
        raise FileNotFoundError('binary_missing')
    return executable


def call(cfg, method, *args, **kwargs):
    """Restore command and run_once caches even on errors; all app callers lock.

    TESSDATA_PREFIX is inherited identically by diagnostics and pytesseract.
    TESSDATA_DIR is not a Tesseract environment option; we never reinterpret it.
    """
    executable = resolve_executable(cfg)
    languages(cfg)
    with _LOCK:
        module = importlib.import_module('pytesseract')
        api = module.pytesseract
        previous = api.tesseract_cmd
        caches = [(fn, fn._result) for fn in
                  (getattr(module, 'get_tesseract_version', None),
                   getattr(module, 'get_languages', None)) if hasattr(fn, '_result')]
        try:
            api.tesseract_cmd = str(executable)
            # image_to_data consults get_tesseract_version(cached=True). A cached
            # version from another executable must not affect this invocation.
            for fn, _ in caches:
                fn._result = fn
            if method in ('image_to_data', 'image_to_string'):
                kwargs['lang'] = languages(cfg)
                kwargs.setdefault('timeout', 5)
            return getattr(module, method)(*args, **kwargs)
        finally:
            api.tesseract_cmd = previous
            for fn, value in caches:
                fn._result = value
