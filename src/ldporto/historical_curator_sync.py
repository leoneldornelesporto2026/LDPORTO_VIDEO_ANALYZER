"""Explicit backfill of existing Analyzer R6 packages to the local Curator inbox.

Inventory mode is strictly read-only. Apply mode reuses the exact validated
atomic handoff, never runs models or builds a new R6 ZIP. A historical analysis
without an already exported official R6 ZIP is reported, not synthesized.
"""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import stat

from .core import file_hash
from .local_curator_handoff import _facts, auto_delivery, curator_directory
from .paths import ANALYSIS_DIR, PROJECT_ROOT
from .second_curation_export import validate_core_package

RECEIPT = "second_curation_export.json"
MAX_RECEIPT_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_RUNS = 250
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _reject_link(path):
    path = Path(path)
    if path.is_symlink() or (
        getattr(path.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
    ):
        raise ValueError("unsafe_symlink_or_windows_reparse_point")


def _directory(path):
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.is_dir():
        raise ValueError("analysis_directory_missing:" + str(path))
    _reject_link(path)
    return path.resolve(strict=True)


def discover_existing(analysis_root=None, analysis_dirs=(), max_runs=MAX_RUNS):
    """Top-level-only scan, plus optional explicitly named historical runs."""
    if isinstance(max_runs, bool) or not isinstance(max_runs, int) or not 1 <= max_runs <= MAX_RUNS:
        raise ValueError("max_runs_out_of_bounds")
    selected = {}
    if analysis_root is None and not analysis_dirs:
        analysis_root = ANALYSIS_DIR
    if analysis_root is not None:
        root = _directory(analysis_root)
        # No recursive traversal into original media, backups or caches.
        for child in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
            if not child.is_dir():
                continue
            if child.is_symlink() or (
                getattr(child.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
            ):
                continue
            selected[str(child.resolve(strict=True))] = child.resolve(strict=True)
            if len(selected) > max_runs:
                raise ValueError("analysis_scan_exceeds_max_runs_use_explicit_selection")
    for name in analysis_dirs:
        folder = _directory(name)
        selected[str(folder)] = folder
        if len(selected) > max_runs:
            raise ValueError("analysis_selection_exceeds_max_runs")
    return [selected[key] for key in sorted(selected, key=str.casefold)]


def _blocked(row, status, reason):
    row["status"] = status
    row["reason"] = str(reason)[:400]
    return row


def inventory_analysis(folder):
    """Read-only SHA+official contract preflight for one existing R6 export."""
    folder = _directory(folder)
    row = {
        "analysis_dir": str(folder), "status": "NOT_CHECKED",
        "source_zip": None, "zip_sha256": None, "video_id": None,
        "run_id": None, "analysis_state": None, "reason": None,
    }
    receipt = folder / RECEIPT
    if not receipt.exists() and not receipt.is_symlink():
        return _blocked(row, "NO_R6_EXPORT", "Existing analysis has no official second_curation_export.json")
    try:
        _reject_link(receipt)
        if not receipt.is_file() or receipt.stat().st_size > MAX_RECEIPT_BYTES:
            return _blocked(row, "BLOCKED_RECEIPT", "Missing, invalid or oversized R6 export receipt")
        record = json.loads(receipt.read_text(encoding="utf-8-sig"))
        if not isinstance(record, dict):
            return _blocked(row, "BLOCKED_RECEIPT", "R6 export receipt must be an object")
        raw = record.get("path")
        expected = record.get("zip_sha256")
        if not isinstance(raw, str) or not raw.strip() or (
            not isinstance(expected, str) or not SHA256.fullmatch(expected.lower())
        ):
            return _blocked(row, "BLOCKED_RECEIPT", "R6 receipt requires path and SHA256")
        package = Path(raw).expanduser()
        if not package.is_absolute():
            package = PROJECT_ROOT / package
        if not package.exists() and not package.is_symlink():
            return _blocked(row, "MISSING_SOURCE_ZIP", "Original R6 ZIP no longer exists")
        _reject_link(package)
        if not package.is_file() or package.suffix.lower() != ".zip":
            return _blocked(row, "BLOCKED_SOURCE_ZIP", "Source is not a regular ZIP")
        size = package.stat().st_size
        if not 0 < size <= MAX_ARCHIVE_BYTES:
            return _blocked(row, "BLOCKED_SOURCE_ZIP", "ZIP outside safe size limits")
        package = package.resolve(strict=True)
        row["source_zip"] = str(package)
        row["zip_sha256"] = expected.lower()
        if file_hash(package) != expected.lower():
            return _blocked(row, "BLOCKED_SHA256", "R6 ZIP differs from its export receipt")
        validated = validate_core_package(package)
        if validated.get("status") != "valid":
            return _blocked(
                row, "BLOCKED_INVALID_R6",
                "Official R6 validator rejected package: " +
                ",".join(str(x) for x in (validated.get("errors") or [])[:5]),
            )
        facts = _facts(package)
        row.update({
            "status": "READY_FOR_DELIVERY",
            "video_id": facts["video_id"],
            "run_id": facts["run_id"],
            "analysis_state": facts["analysis_state"],
        })
        return row
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return _blocked(row, "BLOCKED_VALIDATION", type(exc).__name__ + ":" + str(exc))


def sync_historical(analysis_root=None, analysis_dirs=(), *,
                    curator_root=None, apply=False, max_runs=MAX_RUNS):
    """Dry-run by default; explicit apply is limited to validated R6 ZIPs."""
    if not isinstance(apply, bool):
        raise ValueError("apply_must_be_boolean")
    folders = discover_existing(analysis_root, analysis_dirs, max_runs)
    if apply:
        root = curator_directory(override=curator_root)
        if not root.is_dir():
            raise ValueError("curator_repository_missing")
        _reject_link(root)
        if not (root / "ldporto_studio" / "core.py").is_file() or not (root / ".gitignore").is_file():
            raise ValueError("curator_repository_marker_missing")
    else:
        root = None
    rows = []
    for folder in folders:
        row = inventory_analysis(folder)
        if apply and row["status"] == "READY_FOR_DELIVERY":
            result = auto_delivery(
                {"path": row["source_zip"], "zip_sha256": row["zip_sha256"]},
                curator_root=root,
            )
            status = result.get("delivery_status")
            row["status"] = (
                status if status in ("DELIVERED", "ALREADY_DELIVERED")
                else "BLOCKED_DELIVERY"
            )
            row["delivery_status"] = status
            row["reason"] = result.get("reason")
            if status in ("DELIVERED", "ALREADY_DELIVERED"):
                row["destination"] = result.get("destination")
                row["sha256_verified"] = result.get("sha256_verified") is True
                row["curator_import_status"] = "CURATOR_IMPORT_PENDING"
                row["human_approved"] = False
                row["publication_ready"] = False
        rows.append(row)
    counts = dict(sorted(Counter(row["status"] for row in rows).items()))
    return {
        "schema_version": "ldporto-historical-curator-sync-1.0",
        "mode": "APPLY_VALIDATED_ONLY" if apply else "DRY_RUN_NO_WRITES",
        "runs_examined": len(rows),
        "counts": counts,
        "rows": rows,
        "reanalysis_executed": False,
        "youtube_download_executed": False,
        "r57_import_executed": False,
        "render_executed": False,
        "human_approval": False,
        "publication_ready": False,
    }
