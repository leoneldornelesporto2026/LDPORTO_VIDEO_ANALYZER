"""Non-destructive Windows diagnosis for a blocked Analyzer -> Curator rename.

This is NOT a delivery or workaround. It only writes task-owned, unique
temporary directories beneath the already-existing Curator video inbox,
uses the SAME os.rename primitive as production, and removes its probes.
Never changes ACLs, Defender, originals, the final delivery, or Git refs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ldporto.local_curator_handoff import _facts, _not_linked  # noqa: E402
from ldporto.second_curation_export import validate_core_package  # noqa: E402

MAX_PROBE_ZIP_BYTES = 64 * 1024 * 1024


def digest(path):
    h = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rename_probe(parent, label, zip_source=None, expected_sha=None):
    """Try ONE real Python os.rename, never touching a pre-existing destination.

    A text-only probe separates basic rename permissions from blocking of
    ZIP-containing directories. Every created path is uniquely named and
    cleaned up best-effort; a failed cleanup is explicitly reported.
    """
    parent = Path(parent)
    _not_linked(parent)
    if not parent.is_dir():
        raise ValueError("curator_video_parent_missing")
    token = uuid4().hex
    stage = parent / (".analyzer-rename-diag-" + label + "-" + token)
    target = parent / (".analyzer-rename-diag-result-" + label + "-" + token)
    result = {"probe": label, "status": "NOT_RUN", "os_rename_called": False,
              "stage": str(stage), "target": str(target), "cleanup_errors": []}
    created_stage = False
    published = False
    try:
        if target.exists() or target.is_symlink():
            raise FileExistsError("diagnostic_target_preexists")
        stage.mkdir(exist_ok=False)
        created_stage = True
        (stage / "DIAGNOSTIC_ONLY.txt").write_text(
            "Diagnostic only. Never an Analyzer handoff or approval.\n", encoding="utf-8"
        )
        if zip_source is not None:
            source = Path(zip_source)
            if expected_sha is None or digest(source) != expected_sha:
                raise ValueError("diagnostic_original_zip_sha_mismatch")
            with source.open("rb") as incoming, (stage / source.name).open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=4 * 1024 * 1024)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if digest(stage / source.name) != expected_sha:
                raise ValueError("diagnostic_copied_zip_sha_mismatch")
            # Read and close the copied ZIP exactly as the real pipeline does.
            from zipfile import ZipFile
            with ZipFile(stage / source.name) as archive:
                archive.namelist()
            (stage / "DIAGNOSTIC_ONLY.json").write_text(
                json.dumps({"diagnostic_only": True, "source_zip_sha256": expected_sha}) + "\n",
                encoding="utf-8"
            )
        if target.exists() or target.is_symlink():
            raise FileExistsError("diagnostic_target_created_concurrently")
        result["os_rename_called"] = True
        os.rename(stage, target)
        published = True
        result["status"] = "PASS"
    except (OSError, ValueError) as exc:
        result.update({
            "status": "FAILED",
            "error_class": type(exc).__name__,
            "winerror": getattr(exc, "winerror", None),
            "errno": getattr(exc, "errno", None),
            "error": str(exc)[:500],
        })
    finally:
        # Only delete directories definitely created by this invocation.
        for path, owned in ((target, published), (stage, created_stage)):
            if owned and (path.exists() or path.is_symlink()):
                try:
                    _not_linked(path)
                    shutil.rmtree(path)
                except (OSError, ValueError) as exc:
                    result["cleanup_errors"].append({"path": str(path), "error": str(exc)[:300]})
    return result


def diagnose(analysis_dir, curator_root=None):
    analysis = Path(analysis_dir).expanduser()
    _not_linked(analysis)
    analysis = analysis.resolve(strict=True)
    receipt_path = analysis / "second_curation_export.json"
    record = json.loads(receipt_path.read_text(encoding="utf-8"))
    raw = record.get("path")
    expected = str(record.get("zip_sha256") or "").lower()
    if not isinstance(raw, str) or not raw or len(expected) != 64 or any(
        c not in "0123456789abcdef" for c in expected
    ):
        raise ValueError("original_export_receipt_missing_path_or_sha256")
    package = Path(raw).expanduser()
    if not package.is_absolute():
        package = ROOT / package
    _not_linked(package)
    package = package.resolve(strict=True)
    if not package.is_file() or package.suffix.lower() != ".zip":
        raise ValueError("original_zip_missing_or_invalid")
    if not 0 < package.stat().st_size <= MAX_PROBE_ZIP_BYTES:
        raise ValueError("diagnostic_zip_size_out_of_bounds")
    if digest(package) != expected:
        raise ValueError("original_zip_sha256_mismatch")
    if validate_core_package(package).get("status") != "valid":
        raise ValueError("original_zip_official_validation_failed")
    facts = _facts(package)
    curator = Path(curator_root).expanduser() if curator_root else ROOT.parent / "LDPORTO_VIDEO_CURATOR"
    _not_linked(curator)
    curator = curator.resolve(strict=True)
    if not (curator / "ldporto_studio" / "core.py").is_file():
        raise ValueError("curator_repository_marker_missing")
    parent = curator / "input" / "analyzer" / facts["video_id"]
    _not_linked(parent)
    if not parent.is_dir():
        raise ValueError("curator_video_parent_missing")
    final_path = parent / facts["run_id"]
    # A final delivery path is NEVER created, renamed, removed, or modified.
    result = {
        "schema_version": "ldporto-windows-curator-rename-diagnostic-1.0",
        "diagnostic_only": True,
        "created_final_delivery": False,
        "changed_security_settings": False,
        "source_zip": str(package),
        "source_zip_sha256": expected,
        "curator_video_dir": str(parent),
        "final_delivery_path": str(final_path),
        "final_delivery_preexists": final_path.exists() or final_path.is_symlink(),
        "probes": [],
    }
    result["probes"].append(rename_probe(parent, "text"))
    result["probes"].append(rename_probe(parent, "zip", package, expected))
    basic, zipped = result["probes"]
    if basic["status"] != "PASS":
        result["interpretation"] = "RENAME_DENIED_FOR_BASIC_DIRECTORY"
    elif zipped["status"] != "PASS":
        result["interpretation"] = "RENAME_DENIED_WITH_ZIP_PAYLOAD"
    else:
        result["interpretation"] = "TEMPORARY_PROBES_PASSED_REAL_HANDOFF_NOT_PROVEN"
    # Verify original bytes did not change during either diagnostic probe.
    result["source_zip_preserved"] = digest(package) == expected
    if not result["source_zip_preserved"]:
        raise ValueError("original_zip_changed_during_diagnostic")
    # Unique report name preserves evidence from earlier diagnostic attempts.
    report = analysis / ("CURATOR_RENAME_DIAGNOSTIC_" + uuid4().hex + ".json")
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["report_path"] = str(report)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only evidence plus task-owned rename probes")
    parser.add_argument("--analysis-dir", required=True)
    parser.add_argument("--curator-root", default=None)
    args = parser.parse_args(argv)
    result = diagnose(args.analysis_dir, args.curator_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(row["status"] == "PASS" and not row["cleanup_errors"]
                    for row in result["probes"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
