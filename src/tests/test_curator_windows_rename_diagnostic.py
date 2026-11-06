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


def test_full_stage_probe_prepares_real_handoff_file_structure_and_cleans_it(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    expected = sha256(source.read_bytes()).hexdigest()
    inbox = tmp_path / "curator"
    inbox.mkdir()
    facts = diag._facts(source)
    observed = []
    real_rename = diag.os.rename

    def capture_and_rename(stage, target):
        observed.append((set(path.name for path in Path(stage).iterdir()), str(stage)))
        return real_rename(stage, target)

    with patch.object(diag.handoff, "validate_core_package", return_value={"status": "valid"}):
        with patch.object(diag.os, "rename", side_effect=capture_and_rename):
            result = diag.full_stage_probe(inbox, source, expected, facts)
    assert result["status"] == "PASS"
    assert result["os_rename_called"]
    assert result["destination_is_diagnostic_only"]
    assert not result["cleanup_errors"]
    names, stage_name = observed[0]
    assert Path(stage_name).name.startswith(".analyzer-pending-")
    assert names == {
        source.name,
        "VIDEO_EVIDENCE_INDEX.json",
        "ANALYZER_TO_CURATOR_HANDOFF.json",
        "README_HANDOFF.md",
    }
    assert sha256(source.read_bytes()).hexdigest() == expected
    assert not list(inbox.iterdir())


def test_full_stage_winerror_5_does_not_fall_back_or_overwrite(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    expected = sha256(source.read_bytes()).hexdigest()
    inbox = tmp_path / "curator"
    inbox.mkdir()
    facts = diag._facts(source)
    denied = PermissionError(13, "Synthetic Windows folder rename failed")
    denied.winerror = 5
    with patch.object(diag.handoff, "validate_core_package", return_value={"status": "valid"}):
        with patch.object(diag.os, "rename", side_effect=denied) as move:
            result = diag.full_stage_probe(inbox, source, expected, facts)
    assert result["status"] == "FAILED"
    assert result["winerror"] == 5
    assert result["os_rename_called"]
    assert not result["cleanup_errors"]
    assert move.call_count == 1
    assert not list(inbox.iterdir())
    assert source.is_file() and sha256(source.read_bytes()).hexdigest() == expected


def test_full_stage_has_no_non_atomic_delivery_or_security_bypass():
    content = SCRIPT.read_text(encoding="utf-8")
    assert 'tempfile.TemporaryDirectory(prefix=".analyzer-pending-", dir=parent)' in content
    assert "handoff._write_atomic_stage(" in content
    assert "handoff._evidence_index(" in content
    assert "handoff._readme(receipt)" in content
    assert '"delivery_status": "DIAGNOSTIC_ONLY_NOT_AN_ACTUAL_HANDOFF"' in content
    assert "os.rename(stage, target)" in content
    assert "FULL_HANDOFF_STAGE_PREPARATION_FAILED" in content
    assert "RENAME_DENIED_WITH_FULL_HANDOFF_STAGE" in content


def test_stage_matrix_variants_are_bounded_and_cleaned(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    expected = sha256(source.read_bytes()).hexdigest()
    parent = tmp_path / "curator"
    parent.mkdir()
    facts = diag._facts(source)
    expected_names = {
        "pending_empty": set(),
        "pending_text": {"DIAGNOSTIC_ONLY.txt"},
        "pending_zip_copy": {"DIAGNOSTIC_ONLY.txt", source.name},
        "pending_zip_validate": {"DIAGNOSTIC_ONLY.txt", source.name},
        "pending_zip_index": {"DIAGNOSTIC_ONLY.txt", source.name, "VIDEO_EVIDENCE_INDEX.json"},
        "pending_zip_receipt": {"DIAGNOSTIC_ONLY.txt", source.name, "VIDEO_EVIDENCE_INDEX.json",
                               "ANALYZER_TO_CURATOR_HANDOFF.json"},
        "pending_zip_readme": {"DIAGNOSTIC_ONLY.txt", source.name, "VIDEO_EVIDENCE_INDEX.json",
                              "ANALYZER_TO_CURATOR_HANDOFF.json", "README_HANDOFF.md"},
    }
    with patch.object(diag.handoff, "validate_core_package", return_value={"status": "valid"}):
        for phase in diag.STAGE_MATRIX_PHASES:
            result = diag.stage_matrix_probe(parent, source, expected, facts, phase)
            assert result["status"] == "PASS", (phase, result)
            assert result["os_rename_called"]
            assert not result["cleanup_errors"]
            assert Path(result["stage"]).name.startswith(".analyzer-pending-")
            assert set(result["stage_file_names"]) == expected_names[phase]
            assert not list(parent.iterdir())
    assert sha256(source.read_bytes()).hexdigest() == expected


def test_stage_matrix_reports_winerror_and_preserves_source(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    expected = sha256(source.read_bytes()).hexdigest()
    parent = tmp_path / "curator"
    parent.mkdir()
    blocked = PermissionError(13, "synthetic Windows WinError 5")
    blocked.winerror = 5
    with patch.object(diag.os, "rename", side_effect=blocked):
        report = diag.stage_matrix_probe(parent, source, expected, diag._facts(source),
                                         "pending_zip_copy")
    assert report["status"] == "FAILED"
    assert report["os_rename_called"]
    assert report["winerror"] == 5
    assert not report["cleanup_errors"]
    assert not list(parent.iterdir())
    assert sha256(source.read_bytes()).hexdigest() == expected


def test_stage_matrix_refuses_unsupported_phase_without_writing(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    parent = tmp_path / "curator"
    parent.mkdir()
    with patch.object(diag.os, "rename") as rename:
        try:
            diag.stage_matrix_probe(parent, source, sha256(source.read_bytes()).hexdigest(),
                                    diag._facts(source), "publish_real_delivery")
        except ValueError as exc:
            assert "unknown_diagnostic_matrix_phase" in str(exc)
        else:
            assert False, "Unsupported matrix phase must fail closed"
        rename.assert_not_called()
    assert not list(parent.iterdir())


def test_stage_matrix_does_not_modify_final_delivery_or_weaken_rename():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "STAGE_MATRIX_PHASES = (" in script
    assert 'tempfile.TemporaryDirectory(prefix=".analyzer-pending-", dir=parent)' in script
    assert '"matrix_first_failure"' in script
    assert "MATRIX_PASSED_FULL_FAILURE_MAY_BE_INTERMITTENT" in script
    assert "os.rename(stage, target)" in script
    assert "os.replace(stage, target)" not in script
    assert "chmod(" not in script
    assert "icacls" not in script



def test_full_probe_uses_offstage_zip_validation_and_original_zip_evidence():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"zip_validation_outside_curator_stage": True' in source
    assert 'evidence = handoff._evidence_index(source, facts, copied_sha)' in source
    assert 'handoff._write_atomic_stage(' in source



def test_read_pattern_probes_work_on_synthetic_zip_without_moving_source(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    expected = sha256(source.read_bytes()).hexdigest()
    parent = tmp_path / "curator"
    parent.mkdir()
    with patch.object(diag.handoff, "validate_core_package", return_value={"status": "valid"}):
        for phase in diag.READ_PATTERN_PHASES:
            result = diag.read_pattern_probe(parent, source, expected, phase)
            assert result["status"] == "PASS", (phase, result)
            assert result["os_rename_called"]
            assert not result["cleanup_errors"]
            assert Path(result["stage"]).name.startswith(".analyzer-pending-")
            assert not list(parent.iterdir())
    assert sha256(source.read_bytes()).hexdigest() == expected


def test_read_pattern_denial_has_no_non_atomic_fallback(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    sha = sha256(source.read_bytes()).hexdigest()
    parent = tmp_path / "curator"
    parent.mkdir()
    blocked = PermissionError(13, "Synthetic Windows denied rename")
    blocked.winerror = 5
    with patch.object(diag.os, "rename", side_effect=blocked) as move:
        report = diag.read_pattern_probe(parent, source, sha, "snapshot_copy")
    assert report["status"] == "FAILED"
    assert report["winerror"] == 5
    assert report["os_rename_called"]
    assert not report["cleanup_errors"]
    assert move.call_count == 1
    assert not list(parent.iterdir())
    assert sha256(source.read_bytes()).hexdigest() == sha


def test_cross_parent_full_stage_is_atomic_and_diagnostic_only(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    sha = sha256(source.read_bytes()).hexdigest()
    base = tmp_path / "curator" / "input" / "analyzer"
    parent = base / "VIDEO123"
    parent.mkdir(parents=True)
    with patch.object(diag.handoff, "validate_core_package", return_value={"status": "valid"}):
        result = diag.full_stage_probe(parent, source, sha, diag._facts(source), stage_root=base)
    assert result["status"] == "PASS", result
    assert result["cross_parent_stage"]
    assert result["stage_root"] == str(base)
    assert result["destination_is_diagnostic_only"]
    assert Path(result["target"]).parent == parent
    assert Path(result["stage"]).parent == base
    assert not result["cleanup_errors"]
    assert not list(base.iterdir()) == []   # video dir still exists
    assert not list(parent.iterdir())
    assert sha256(source.read_bytes()).hexdigest() == sha


def test_cross_parent_full_stage_never_overwrites_a_preexisting_target(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source", video_id="VIDEO123", run_id="RUN_1")
    sha = sha256(source.read_bytes()).hexdigest()
    base = tmp_path / "curator" / "input" / "analyzer"
    parent = base / "VIDEO123"
    parent.mkdir(parents=True)
    class FixedUUID:
        hex = "a" * 32
    destination = parent / (".analyzer-rename-diag-result-full-" + "a" * 32)
    destination.mkdir()
    (destination / "user_owned.txt").write_text("preserve", encoding="utf-8")
    with patch.object(diag, "uuid4", return_value=FixedUUID()):
        with patch.object(diag.os, "rename") as move:
            result = diag.full_stage_probe(
                parent, source, sha, diag._facts(source), stage_root=base
            )
    assert result["status"] == "FAILED"
    assert not result["os_rename_called"]
    assert (destination / "user_owned.txt").read_text(encoding="utf-8") == "preserve"
    move.assert_not_called()


def test_read_pattern_probe_rejects_invalid_phase_without_writes(tmp_path):
    from test_local_curator_handoff import fake_zip
    source = fake_zip(tmp_path / "source")
    parent = tmp_path / "curator"
    parent.mkdir()
    try:
        diag.read_pattern_probe(parent, source, sha256(source.read_bytes()).hexdigest(), "accept_and_publish")
    except ValueError as exc:
        assert "unknown_diagnostic_read_phase" in str(exc)
    else:
        assert False, "Unexpected acceptance of a non-diagnostic phase"
    assert not list(parent.iterdir())
