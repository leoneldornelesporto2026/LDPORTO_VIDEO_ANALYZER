"""Historical R6 backfill: dry-run, hash validation, safe atomic sync, no inference."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ldporto import historical_curator_sync as sync
from ldporto import local_curator_handoff as delivery
from test_local_curator_handoff import fake_curator, fake_zip


def export_record(run_dir, source, *, digest=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    sha = digest if digest is not None else delivery.file_hash(source)
    (run_dir / "second_curation_export.json").write_text(
        json.dumps({"path": str(source), "zip_sha256": sha}) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def valid_contract(monkeypatch):
    monkeypatch.setattr(sync, "validate_core_package",
                        lambda package: {"status": "valid", "errors": []})
    monkeypatch.setattr(delivery, "validate_core_package",
                        lambda package: {"status": "valid", "errors": []})


def test_01_default_inventory_does_not_write_or_deliver(tmp_path, monkeypatch, valid_contract):
    root = tmp_path / "analysis"
    package = fake_zip(tmp_path / "packages", video_id="VIDEO123", run_id="RUN_1")
    export_record(root / "run_one", package)
    monkeypatch.setattr(sync, "ANALYSIS_DIR", root)
    monkeypatch.setattr(sync, "auto_delivery",
                        lambda *args, **kwargs: pytest.fail("dry run delivered a package"))
    result = sync.sync_historical()
    assert result["mode"] == "DRY_RUN_NO_WRITES"
    assert result["counts"] == {"READY_FOR_DELIVERY": 1}
    assert result["rows"][0]["run_id"] == "RUN_1"
    assert result["rows"][0]["source_zip"] == str(package)
    assert not (tmp_path / "LDPORTO_VIDEO_CURATOR").exists()
    assert result["reanalysis_executed"] is False


def test_02_only_preexisting_validated_r6_is_delivered_atomically(tmp_path, valid_contract):
    root = tmp_path / "analysis"
    curator = fake_curator(tmp_path)
    package = fake_zip(tmp_path / "packages", video_id="VIDEO123", run_id="RUN_1")
    sha = delivery.file_hash(package)
    export_record(root / "one", package)
    before = package.read_bytes()
    first = sync.sync_historical(analysis_root=root, curator_root=curator, apply=True)
    assert first["counts"] == {"DELIVERED": 1}
    destination = Path(first["rows"][0]["destination"])
    assert destination.is_dir()
    assert delivery.file_hash(destination / package.name) == sha
    assert (destination / "VIDEO_EVIDENCE_INDEX.json").is_file()
    assert package.read_bytes() == before
    second = sync.sync_historical(analysis_root=root, curator_root=curator, apply=True)
    assert second["counts"] == {"ALREADY_DELIVERED": 1}
    assert package.read_bytes() == before
    assert not list(destination.parent.glob(".analyzer-pending-*"))


def test_03_runs_without_export_are_visible_not_made_up(tmp_path, valid_contract):
    root = tmp_path / "analysis"
    (root / "old_run").mkdir(parents=True)
    result = sync.sync_historical(analysis_root=root)
    assert result["counts"] == {"NO_R6_EXPORT": 1}
    assert result["rows"][0]["source_zip"] is None
    assert result["render_executed"] is False


def test_04_wrong_sha_blocks_without_touching_curator(tmp_path, valid_contract):
    root = tmp_path / "analysis"
    curator = fake_curator(tmp_path)
    package = fake_zip(tmp_path / "packages")
    export_record(root / "bad_run", package, digest="0" * 64)
    original = package.read_bytes()
    result = sync.sync_historical(analysis_root=root, apply=True, curator_root=curator)
    assert result["counts"] == {"BLOCKED_SHA256": 1}
    assert not (curator / "input").exists()
    assert package.read_bytes() == original


def test_05_invalid_official_zip_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "analysis"
    package = fake_zip(tmp_path / "packages")
    export_record(root / "run_one", package)
    monkeypatch.setattr(sync, "validate_core_package",
                        lambda package: {"status": "failed", "errors": ["synthetic_contract_error"]})
    result = sync.sync_historical(analysis_root=root)
    assert result["counts"] == {"BLOCKED_INVALID_R6": 1}
    assert "synthetic_contract_error" in result["rows"][0]["reason"]


def test_06_scan_is_not_recursive_and_explicit_nested_runs_are_supported(tmp_path, valid_contract):
    root = tmp_path / "analysis"
    package = fake_zip(tmp_path / "packages")
    nested = root / "group" / "nested"
    export_record(nested, package)
    by_root = sync.sync_historical(analysis_root=root)
    assert by_root["counts"] == {"NO_R6_EXPORT": 1}
    targeted = sync.sync_historical(analysis_dirs=[nested])
    assert targeted["counts"] == {"READY_FOR_DELIVERY": 1}


def test_07_scan_fails_closed_at_bound(tmp_path):
    root = tmp_path / "analysis"
    (root / "run_one").mkdir(parents=True)
    (root / "run_two").mkdir(parents=True)
    with pytest.raises(ValueError, match="exceeds_max_runs"):
        sync.sync_historical(analysis_root=root, max_runs=1)


def test_08_malformed_receipt_cannot_trigger_delivery(tmp_path):
    root = tmp_path / "analysis"
    folder = root / "run_one"
    folder.mkdir(parents=True)
    (folder / "second_curation_export.json").write_text(
        json.dumps({"path": "../somewhere.zip", "zip_sha256": "bad"}), encoding="utf-8"
    )
    result = sync.sync_historical(analysis_root=root)
    assert result["counts"] == {"BLOCKED_RECEIPT": 1}


def test_09_does_not_follow_linked_analysis_directory(tmp_path):
    root = tmp_path / "analysis"
    real = tmp_path / "real"
    real.mkdir()
    root.mkdir()
    link = root / "alias"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Windows developer mode or symlink privilege is required")
    result = sync.sync_historical(analysis_root=root)
    assert result["runs_examined"] == 0
    with pytest.raises(ValueError, match="unsafe_symlink"):
        sync.sync_historical(analysis_dirs=[link])


def test_10_bounded_apply_requires_curator_marker(tmp_path, valid_contract):
    root = tmp_path / "analysis"
    package = fake_zip(tmp_path / "packages")
    export_record(root / "run_one", package)
    not_curator = tmp_path / "not-curator"
    not_curator.mkdir()
    with pytest.raises(ValueError, match="curator_repository_marker_missing"):
        sync.sync_historical(analysis_root=root, curator_root=not_curator, apply=True)
    assert not (not_curator / "input").exists()


def test_11_windows_operator_requires_explicit_apply():
    script = (Path(__file__).resolve().parents[2] /
              "scripts/windows/testing/SINCRONIZAR_ANALISES_CURATOR.ps1").read_text(encoding="utf-8")
    assert "[switch]$Aplicar" in script
    assert 'if ($Aplicar)' in script
    assert 'args' not in script or '--apply' in script
    assert "git.exe -C $analyzer branch --show-current" in script
    assert "git.exe -C $curator branch --show-current" in script
    assert "git push" not in script and "git merge" not in script
    assert "AllowDownload" not in script and "ffmpeg" not in script.lower()
