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