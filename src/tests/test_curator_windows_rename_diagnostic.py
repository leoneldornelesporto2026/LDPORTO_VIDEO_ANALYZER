"""Synthetic safe-fs probes for the Windows-only Analyzer handoff diagnosis.

These tests do not claim real Windows behavior: the pilot must still run there.
"""
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import importlib.util
import zipfile


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/dev/diagnose_curator_rename.py"
spec = importlib.util.spec_from_file_location("diagnose_curator_rename", SCRIPT)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def make_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("evidence.txt", "Test only. No real video.")
    return sha256(path.read_bytes()).hexdigest()


def test_text_only_rename_passes_and_cleans_up(tmp_path):
    result = diag.rename_probe(tmp_path, "text")
    assert result["status"] == "PASS"
    assert result["os_rename_called"]
    assert not result["cleanup_errors"]
    assert list(tmp_path.iterdir()) == []


def test_zip_rename_verifies_sha_and_never_modifies_source(tmp_path):
    source = tmp_path / "ORIGINAL.zip"
    digest = make_zip(source)
    inbox = tmp_path / "curator" / "input" / "analyzer" / "video123"
    inbox.mkdir(parents=True)
    result = diag.rename_probe(inbox, "zip", source, digest)
    assert result["status"] == "PASS"
    assert sha256(source.read_bytes()).hexdigest() == digest
    assert not result["cleanup_errors"]
    assert list(inbox.iterdir()) == []


def test_persistent_winerror_5_is_reported_and_probe_owned_paths_are_removed(tmp_path):
    source = tmp_path / "ORIGINAL.zip"
    digest = make_zip(source)
    inbox = tmp_path / "curator"
    inbox.mkdir()
    blocked = PermissionError(13, "Synthetic rename denial")
    blocked.winerror = 5
    with patch.object(diag.os, "rename", side_effect=blocked):
        report = diag.rename_probe(inbox, "zip", source, digest)
    assert report["status"] == "FAILED"
    assert report["winerror"] == 5
    assert report["os_rename_called"]
    assert not report["cleanup_errors"]
    assert source.exists()
    assert not list(inbox.iterdir())


def test_wrong_original_sha_never_calls_rename(tmp_path):
    source = tmp_path / "original.zip"
    make_zip(source)
    inbox = tmp_path / "curator"
    inbox.mkdir()
    with patch.object(diag.os, "rename") as move:
        report = diag.rename_probe(inbox, "zip", source, "0" * 64)
    assert report["status"] == "FAILED"
    assert report["os_rename_called"] is False
    assert not list(inbox.iterdir())
    move.assert_not_called()


def test_preexisting_probe_destination_is_preserved(tmp_path):
    class FixedUUID:
        hex = "a" * 32
    target = tmp_path / (".analyzer-rename-diag-result-text-" + "a" * 32)
    target.mkdir()
    (target / "operator_owned.txt").write_text("keep me", encoding="utf-8")
    with patch.object(diag, "uuid4", return_value=FixedUUID()):
        with patch.object(diag.os, "rename") as move:
            report = diag.rename_probe(tmp_path, "text")
    assert report["status"] == "FAILED"
    assert report["os_rename_called"] is False
    assert (target / "operator_owned.txt").read_text(encoding="utf-8") == "keep me"
    assert not (tmp_path / (".analyzer-rename-diag-text-" + "a" * 32)).exists()
    move.assert_not_called()


def test_diagnostic_does_not_attempt_non_atomic_delivery_or_security_changes():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "os.rename(stage, target)" in content
    for forbidden in ("os.replace(", "Set-Acl", "icacls", "takeown",
                      "git push", "git merge", "subprocess.run", "AllowDownload"):
        assert forbidden not in content
    assert "final_delivery_preexists" in content
    assert "source_zip_preserved" in content
