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
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ldporto.local_curator_handoff import _facts, _not_linked  # noqa: E402
from ldporto import local_curator_handoff as handoff  # noqa: E402
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



def full_stage_probe(parent, zip_source, expected_sha, facts):
    """Prepare the same four handoff artifacts, then ONE isolated directory rename.

    Unlike a delivery, the temporary target starts with a diagnostic prefix,
    marks itself DIAGNOSTIC_ONLY, and is never an accepted Curator run slot.
    Stage creation uses the production tempfile.TemporaryDirectory pattern.
    """
    parent = Path(parent)
    _not_linked(parent)
    if not parent.is_dir():
        raise ValueError("curator_video_parent_missing")
    source = Path(zip_source)
    token = uuid4().hex
    target = parent / (".analyzer-rename-diag-result-full-" + token)
    result = {"probe": "full", "status": "NOT_RUN", "os_rename_called": False,
              "stage": None, "target": str(target), "cleanup_errors": [],
              "reproduces_production_stage_files": True,
              "destination_is_diagnostic_only": True, "stage_file_names": []}
    moved = False
    try:
        if target.exists() or target.is_symlink():
            raise FileExistsError("diagnostic_full_target_preexists")
        if digest(source) != expected_sha:
            raise ValueError("diagnostic_original_zip_sha_mismatch")
        with tempfile.TemporaryDirectory(prefix=".analyzer-pending-", dir=parent) as temp:
            stage = Path(temp)
            result["stage"] = str(stage)
            copied_sha, copied_validation = handoff._write_atomic_stage(
                stage, source, expected_sha, facts
            )
            if copied_sha != expected_sha or copied_validation.get("status") != "valid":
                raise ValueError("diagnostic_full_copied_zip_validation_failed")
            evidence = handoff._evidence_index(stage / source.name, facts, copied_sha)
            index_file = stage / handoff.EVIDENCE_INDEX_NAME
            index_file.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8"
            )
            receipt = {
                "diagnostic_only": True,
                "delivery_status": "DIAGNOSTIC_ONLY_NOT_AN_ACTUAL_HANDOFF",
                "analysis_state": facts["analysis_state"],
                "source_video": facts["source_video"],
                "zip": {"name": source.name, "sha256": copied_sha},
                "evidence_index": {
                    "name": handoff.EVIDENCE_INDEX_NAME, "sha256": digest(index_file)
                },
                "human_approval": False, "publication_ready": False,
            }
            (stage / handoff.HANDOFF_NAME).write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8"
            )
            (stage / handoff.GUIDE_NAME).write_text(
                handoff._readme(receipt), encoding="utf-8"
            )
            result["stage_file_names"] = sorted(row.name for row in stage.iterdir())
            if target.exists() or target.is_symlink():
                raise FileExistsError("diagnostic_full_target_created_concurrently")
            result["os_rename_called"] = True
            os.rename(stage, target)
            moved = True
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
        # Never delete a preexisting destination: cleanup only after OUR rename.
        if moved and (target.exists() or target.is_symlink()):
            try:
                _not_linked(target)
                shutil.rmtree(target)
            except (OSError, ValueError) as exc:
                result["cleanup_errors"].append(
                    {"path": str(target), "error": str(exc)[:300]}
                )
        # TemporaryDirectory owns its stage and cleans it on exit; if it
        # could not, record the exact path without touching unrelated items.
        if result["stage"] is not None:
            stage = Path(result["stage"])
            if stage.exists() or stage.is_symlink():
                result["cleanup_errors"].append({
                    "path": str(stage), "error": "temporary_stage_cleanup_incomplete"
                })
    return result



STAGE_MATRIX_PHASES = (
    "pending_empty",
    "pending_text",
    "pending_zip_copy",
    "pending_zip_validate",
    "pending_zip_index",
    "pending_zip_receipt",
    "pending_zip_readme",
)


def stage_matrix_probe(parent, zip_source, expected_sha, facts, phase):
    """Locate the first denied stage using disposable folders, not real delivery.

    All variants use the exact production stage prefix and Windows os.rename.
    Each variant adds one feature relative to the previous stage. No security
    changes, delivery to a canonical path, inference, or non-atomic fallback.
    """
    if phase not in STAGE_MATRIX_PHASES:
        raise ValueError("unknown_diagnostic_matrix_phase")
    step = STAGE_MATRIX_PHASES.index(phase)
    parent = Path(parent)
    _not_linked(parent)
    if not parent.is_dir():
        raise ValueError("curator_video_parent_missing")
    source = Path(zip_source)
    target = parent / (".analyzer-rename-diag-result-matrix-" + phase + "-" + uuid4().hex)
    result = {
        "phase": phase, "status": "NOT_RUN", "os_rename_called": False,
        "target": str(target), "stage": None, "stage_file_names": [],
        "cleanup_errors": [], "diagnostic_only": True,
    }
    moved = False
    try:
        if target.exists() or target.is_symlink():
            raise FileExistsError("diagnostic_matrix_target_preexists")
        with tempfile.TemporaryDirectory(prefix=".analyzer-pending-", dir=parent) as temp:
            stage = Path(temp)
            result["stage"] = str(stage)
            if step >= 1:
                (stage / "DIAGNOSTIC_ONLY.txt").write_text(
                    "Temporary rename test, not a delivery.\n", encoding="utf-8"
                )
            if step >= 2:
                if digest(source) != expected_sha:
                    raise ValueError("diagnostic_original_zip_sha_mismatch")
                with source.open("rb") as incoming, (stage / source.name).open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=4 * 1024 * 1024)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                if digest(stage / source.name) != expected_sha:
                    raise ValueError("diagnostic_matrix_copy_sha_mismatch")
            if step >= 3:
                checked = handoff.validate_core_package(stage / source.name)
                if checked.get("status") != "valid":
                    raise ValueError("diagnostic_matrix_zip_validation_failed")
            if step >= 4:
                index = handoff._evidence_index(stage / source.name, facts, expected_sha)
                (stage / handoff.EVIDENCE_INDEX_NAME).write_text(
                    json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8",
                )
            receipt = {
                "diagnostic_only": True,
                "delivery_status": "DIAGNOSTIC_ONLY_NOT_AN_ACTUAL_HANDOFF",
                "analysis_state": facts["analysis_state"],
                "source_video": facts["source_video"],
                "zip": {"name": source.name, "sha256": expected_sha},
                "human_approval": False, "publication_ready": False,
            }
            if step >= 5:
                (stage / handoff.HANDOFF_NAME).write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            if step >= 6:
                (stage / handoff.GUIDE_NAME).write_text(
                    handoff._readme(receipt), encoding="utf-8"
                )
            result["stage_file_names"] = sorted(p.name for p in stage.iterdir())
            if target.exists() or target.is_symlink():
                raise FileExistsError("diagnostic_matrix_target_created_concurrently")
            result["os_rename_called"] = True
            os.rename(stage, target)
            moved = True
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
        if moved and (target.exists() or target.is_symlink()):
            try:
                _not_linked(target)
                shutil.rmtree(target)
            except (OSError, ValueError) as exc:
                result["cleanup_errors"].append(
                    {"path": str(target), "error": str(exc)[:300]}
                )
        if result["stage"] is not None:
            stage = Path(result["stage"])
            if stage.exists() or stage.is_symlink():
                result["cleanup_errors"].append({
                    "path": str(stage), "error": "temporary_stage_cleanup_incomplete"
                })
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
        "schema_version": "ldporto-windows-curator-rename-diagnostic-1.2",
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
    result["probes"].append(full_stage_probe(parent, package, expected, facts))
    basic, zipped, full = result["probes"]
    if basic["status"] != "PASS":
        result["interpretation"] = "RENAME_DENIED_FOR_BASIC_DIRECTORY"
    elif zipped["status"] != "PASS":
        result["interpretation"] = "RENAME_DENIED_WITH_ZIP_PAYLOAD"
    elif full["status"] != "PASS" and full["os_rename_called"]:
        result["interpretation"] = "RENAME_DENIED_WITH_FULL_HANDOFF_STAGE"
    elif full["status"] != "PASS":
        result["interpretation"] = "FULL_HANDOFF_STAGE_PREPARATION_FAILED"
    else:
        result["interpretation"] = "ALL_DIAGNOSTIC_PROBES_PASSED_REAL_HANDOFF_NOT_PROVEN"
    # The full stage failed, so isolate stage naming, ZIP reads and each
    # additional artifact. The matrix never publishes a real run slot.
    if full["status"] != "PASS":
        result["stage_matrix"] = [
            stage_matrix_probe(parent, package, expected, facts, phase)
            for phase in STAGE_MATRIX_PHASES
        ]
        result["matrix_first_failure"] = next(
            (row["phase"] for row in result["stage_matrix"] if row["status"] != "PASS"),
            None
        )
        if result["matrix_first_failure"] is None:
            result["matrix_interpretation"] = "MATRIX_PASSED_FULL_FAILURE_MAY_BE_INTERMITTENT"
        else:
            result["matrix_interpretation"] = "FIRST_FAILING_STAGE_IS_DIAGNOSTIC_NOT_CAUSAL_PROOF"
    # Verify original bytes did not change during all diagnostic probes.
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
