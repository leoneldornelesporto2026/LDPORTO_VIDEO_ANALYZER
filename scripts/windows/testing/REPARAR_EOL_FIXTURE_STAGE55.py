"""Verify or safely repair CRLF checkout of the immutable stage55 JSON fixture.

This is NOT a hash updater. The only accepted repair is CRLF -> LF producing
the exact historical SHA256. No network, dependencies, or other files touched.

Usage (repository root, Windows):
    .\.venv\Scripts\python.exe scripts/windows/testing/REPARAR_EOL_FIXTURE_STAGE55.py --repair
"""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "src/tests/fixtures/stage55_commercial_synthetic.json"
EXPECTED = "81298196b4006f83e1cf3bc9c25dd82b243fbcf877e294f0c0122c4dfba9b164"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def assess(payload: bytes, expected_sha: str = EXPECTED):
    """Return ('valid'|'crlf_only'|'invalid', canonical_bytes|None)."""
    if digest(payload) == expected_sha:
        return "valid", payload
    normalized = payload.replace(b"\r\n", b"\n")
    if normalized != payload and digest(normalized) == expected_sha:
        return "crlf_only", normalized
    return "invalid", None


def repair_fixture(path: Path = FIXTURE, *, apply: bool = False, expected_sha: str = EXPECTED) -> str:
    """Never changes a file unless normalization exactly matches expected hash."""
    raw = path.read_bytes()
    status, canonical = assess(raw, expected_sha)
    if status == "valid":
        return "OK: fixture original ja esta com o SHA256 correto"
    if status == "invalid":
        raise ValueError(
            "BLOQUEADO: bytes nao correspondem ao original nem por CRLF -> LF; "
            "arquivo preservado. SHA256 atual=" + digest(raw)
        )
    if not apply:
        raise ValueError(
            "CRLF detectado; conteudo original verificavel. "
            "Execute com --repair para normalizar apenas esta fixture."
        )

    assert canonical is not None and digest(canonical) == expected_sha
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".stage55-lf-", suffix=".tmp", delete=False
        ) as staged:
            temporary = Path(staged.name)
            staged.write(canonical)
        if digest(temporary.read_bytes()) != expected_sha:
            raise ValueError("Falha verificando o arquivo temporario")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if digest(path.read_bytes()) != expected_sha:
        raise ValueError("SHA256 divergente apos gravacao")
    return "REPARADO: somente CRLF -> LF; SHA256 original confirmado"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true", help="Apply safe, verified CRLF -> LF repair")
    args = parser.parse_args()
    try:
        print(repair_fixture(apply=args.repair))
    except (OSError, ValueError) as exc:
        print(exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
