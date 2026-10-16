"""Project-owned paths; user-provided media paths retain their own semantics."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
SCHEMA_DIR = PROJECT_ROOT / "schemas"
DOCS_DIR = PROJECT_ROOT / "docs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
REQUIREMENTS_DIR = PROJECT_ROOT / "requirements"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
PACKAGE_OUTPUT_DIR = PROJECT_ROOT / "pacotes_para_enviar"
MODELS_DIR = PROJECT_ROOT / "models"
OPTIONAL_GROUPS = frozenset({"dev", "diarization", "vision", "gpu-windows", "yolo", "ocr", "demucs", "audio-events"})


def project_path(value, root=None):
    path = Path(value).expanduser()
    return path if path.is_absolute() else (Path(root) if root is not None else PROJECT_ROOT) / path


def optional_requirement(group, root=None):
    if group not in OPTIONAL_GROUPS:
        raise ValueError("Unknown optional dependency group: " + str(group))
    return project_path(Path("requirements") / (group + ".txt"), root)


def videos_directory():
    """Resolve the redirected Windows Videos Known Folder, with portable fallback."""
    import os
    if os.name == 'nt':
        import ctypes
        import uuid
        guid = (ctypes.c_ubyte * 16).from_buffer_copy(
            uuid.UUID('18989b1d-99b5-455b-841c-ab7c74e4ddfc').bytes_le)
        value = ctypes.c_wchar_p()
        shell = ctypes.windll.shell32
        shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                               ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        shell.SHGetKnownFolderPath.restype = ctypes.c_long
        if shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(value)) == 0:
            try:
                return Path(value.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(value, ctypes.c_void_p))
    return Path.home() / 'Videos'


def windows_component(value, fallback='PROJETO', max_length=110):
    import re
    import unicodedata
    text = unicodedata.normalize('NFC', str(value or ''))
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = re.sub(r'\s+', '_', text).strip(' ._')[:max_length].rstrip(' .') or fallback
    if text.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *('COM%d'%n for n in range(1,10)), *('LPT%d'%n for n in range(1,10))}:
        text = '_'+text
    return text
