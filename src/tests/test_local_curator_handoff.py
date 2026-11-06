"""Synthetic local inbox delivery tests, plus a real official ZIP validation test.

No external Curator project, model, download, render or historical evidence
is touched. Monkeypatched tests validate transfer mechanics only.
"""
from pathlib import Path
import hashlib
import json
from unittest.mock import patch
import zipfile

import pytest

from ldporto import local_curator_handoff as delivery


def fake_curator(tmp_path, name="LDPORTO_VIDEO_CURATOR"):
    root = tmp_path / name
    (root / "ldporto_studio").mkdir(parents=True)
    (root / "ldporto_studio" / "core.py").write_text("# synthetic Curator marker\n", encoding="utf-8")
    (root / ".gitignore").write_text("/input/\n/output/\n", encoding="utf-8")
    return root


def fake_zip(folder, *, video_id="VIDEO123", run_id="RUN_1", status="complete",
             review_ready=True, candidates=2, stories=1):
    folder.mkdir(parents=True, exist_ok=True)
    archive_path = folder / ("SECOND_CURATION_" + run_id + ".zip")
    manifest = {
        "run_id": run_id, "source_hash": "a" * 64,
        "analysis_status": status, "analyzer_version": "synthetic.test",
        "preview_approved": False, "publication_ready": False,
        "workflow": {"review_ready": review_ready},
        "readiness_reasons": {"transcript_ready": None, "camera_ready": "synthetic_gap"},
        "readiness": {"transcript_ready": True, "camera_ready": False},
        "files": [],
    }
    contents = {
        "SECOND_CURATION_MANIFEST.json": manifest,
        "CURATION_INDEX.json": {"candidate_count": candidates,
                                "source": {"title": "Vídeo sintético", "duration": 120}},
        "SECOND_CURATOR_BRIEF.json": {"source_id": video_id},
        "source/metadata.json": {"sha256": "a" * 64, "duration": 120, "width": 1920,
                                 "height": 1080, "fps": 30,
                                 "source": {"id": video_id}},
        "editorial/candidate_catalog.json": {"candidates": [
            {"candidate_id": "SYN_" + str(i)} for i in range(candidates)]},
        "social/stories_manifest.json": {"stories": [
            {"story_id": "STORY_" + str(i)} for i in range(stories)]},
        "subtitles/caption_preflight_r6.json": {"status": "pending_review"},
    }
    with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED) as archive:
        for key, value in contents.items():
            archive.writestr(key, json.dumps(value, ensure_ascii=False))
    return archive_path


def synthetic_validator(_):
    # Deliberately mocked: isolates file-transfer behavior from schema validation.
    return {"status": "valid", "checksums_valid": True, "errors": []}


@pytest.fixture
def stubbed_validator(monkeypatch):
    monkeypatch.setattr(delivery, "validate_core_package", synthetic_validator)


def test_01_validated_synthetic_zip_copied_with_matching_sha_and_receipt(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "analysis")
    original_hash = delivery.file_hash(source)
    result = delivery.deliver_package(source, curator_root=root, expected_sha=original_hash)
    assert result["delivery_status"] == "DELIVERED"
    target = Path(result["destination"])
    assert target == root / "input" / "analyzer" / "VIDEO123" / "RUN_1"
    assert delivery.file_hash(target / source.name) == original_hash == delivery.file_hash(source)
    receipt = json.loads((target / "ANALYZER_TO_CURATOR_HANDOFF.json").read_text(encoding="utf-8"))
    assert receipt["zip"]["sha256"] == original_hash
    assert receipt["reel_candidate_count"] == 2 and receipt["story_candidate_count"] == 1
    assert receipt["curator_import_status"] == "CURATOR_IMPORT_PENDING"
    assert receipt["human_approval"] is False and receipt["publication_ready"] is False
    assert receipt["checks"]["copied_zip"] == "valid"
    assert "R57" in (target / "README_HANDOFF.md").read_text(encoding="utf-8")
    evidence_path = target / "VIDEO_EVIDENCE_INDEX.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["zip_sha256"] == original_hash
    assert evidence["run_id"] == "RUN_1"
    assert evidence["source_sha256"] == "a" * 64
    with zipfile.ZipFile(target / source.name) as archived:
        assert {x["path"] for x in evidence["artifacts"]} == set(archived.namelist())
    assert receipt["evidence_index"]["sha256"] == delivery.file_hash(evidence_path)
    assert evidence["video_file_included"] is False
    assert evidence["publication_ready"] is False
    assert not list((root / "input" / "analyzer" / "VIDEO123").glob(".analyzer-pending-*"))


def test_02_curator_missing_returns_blocked_without_losing_source(tmp_path, stubbed_validator):
    source = fake_zip(tmp_path / "analysis")
    sha = delivery.file_hash(source)
    result = delivery.auto_delivery({"path": str(source), "zip_sha256": sha},
                                    curator_root=tmp_path / "not_installed")
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert result["source_preserved"] is True
    assert delivery.file_hash(source) == sha


def test_03_copy_failure_keeps_original_and_has_no_announced_zip(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "analysis")
    with patch.object(delivery.shutil, "copyfileobj", side_effect=OSError("synthetic_disk_full")):
        result = delivery.auto_delivery({"path": str(source)}, curator_root=root)
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert "synthetic_disk_full" in result["reason"]
    assert source.is_file()
    assert not list((root / "input" / "analyzer" / "VIDEO123").glob("RUN_1"))
    assert not list((root / "input" / "analyzer" / "VIDEO123").glob(".analyzer-pending-*"))


def test_04_two_runs_of_same_video_have_separate_deliveries(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    first = fake_zip(tmp_path / "first", run_id="RUN_1")
    second = fake_zip(tmp_path / "second", run_id="RUN_2")
    a = delivery.deliver_package(first, curator_root=root)
    b = delivery.deliver_package(second, curator_root=root)
    assert Path(a["destination"]) != Path(b["destination"])
    assert Path(a["destination"]).is_dir() and Path(b["destination"]).is_dir()


def test_05_same_run_and_hash_is_idempotent(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    a = delivery.deliver_package(source, curator_root=root)
    b = delivery.deliver_package(source, curator_root=root)
    assert b["delivery_status"] == "ALREADY_DELIVERED"
    assert a["destination"] == b["destination"]
    assert len(list((root / "input" / "analyzer" / "VIDEO123").iterdir())) == 1


def test_06_partial_source_cannot_become_ready_or_approved(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run", status="partial", review_ready=True)
    result = delivery.deliver_package(source, curator_root=root)
    receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["analysis_state"] == "PARTIAL"
    assert result["analysis_state"] == "PARTIAL"
    assert receipt["curator_import_verified"] is False
    assert receipt["publication_ready"] is False


def test_07_windows_style_spaces_and_unicode_path(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path, name="Projetos Especiais - São José")
    source = fake_zip(tmp_path / "Meus Projetos" / "Análise com espaços")
    result = delivery.deliver_package(source, curator_root=root)
    assert Path(result["receipt_path"]).exists()
    assert Path(result["destination"]).is_relative_to(root)


def test_08_changed_source_hash_is_blocked(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    result = delivery.auto_delivery({"path": str(source), "zip_sha256": "0" * 64},
                                    curator_root=root)
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert "source_package_sha256_changed" in result["reason"]
    assert source.is_file()


def test_09_same_run_with_different_hash_preserves_original(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    one = fake_zip(tmp_path / "one", candidates=1)
    two = fake_zip(tmp_path / "two", candidates=3)
    result1 = delivery.deliver_package(one, curator_root=root)
    result2 = delivery.deliver_package(two, curator_root=root)
    assert result1["destination"] != result2["destination"]
    assert "sha-" in Path(result2["destination"]).name
    assert Path(result1["receipt_path"]).is_file()
    assert Path(result2["receipt_path"]).is_file()


def test_10_corrupted_original_is_rejected_by_official_validation(tmp_path):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    result = delivery.auto_delivery({"path": str(source)}, curator_root=root)
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert source.is_file()
    assert not list((root / "input").rglob("ANALYZER_TO_CURATOR_HANDOFF.json"))


def test_11_refuses_destination_symlinks(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    external = tmp_path / "elsewhere"
    external.mkdir()
    try:
        (root / "input").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink creation requires Developer Mode or elevated privileges")
    source = fake_zip(tmp_path / "run")
    assert delivery.auto_delivery({"path": str(source)}, curator_root=root)["delivery_status"] == "DELIVERY_BLOCKED"
    assert not list(external.rglob("*.zip"))


def test_12_broken_existing_delivery_is_preserved_and_refused(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    first = delivery.deliver_package(source, curator_root=root)
    target = Path(first["destination"]) / source.name
    original = target.read_bytes()
    target.write_bytes(b"corrupted")
    report = delivery.auto_delivery({"path": str(source)}, curator_root=root)
    assert report["delivery_status"] == "DELIVERY_BLOCKED"
    assert target.read_bytes() == b"corrupted"
    assert original != target.read_bytes()


def test_13_git_ignores_runtime_media_and_zip_outputs():
    gitignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8")
    assert "input/" in gitignore
    assert "*.mp4" in gitignore and "*.zip" in gitignore
    assert "analysis/" in gitignore and "pacotes_para_enviar/" in gitignore


def test_14_corrupted_evidence_index_blocks_idempotent_retry(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    package = fake_zip(tmp_path / "run")
    first = delivery.deliver_package(package, curator_root=root)
    evidence_path = Path(first["destination"]) / "VIDEO_EVIDENCE_INDEX.json"
    evidence_path.write_text("{}", encoding="utf-8")
    repeated = delivery.auto_delivery({"path": str(package)}, curator_root=root)
    assert repeated["delivery_status"] == "DELIVERY_BLOCKED"
    assert "existing_evidence_index_corrupted" in repeated["reason"]
    assert package.exists()
    assert evidence_path.read_text(encoding="utf-8") == "{}"


def test_15_integration_is_after_final_report_receipt_and_nonblocking():
    code = (Path(__file__).resolve().parents[1] / "ldporto" / "reports.py").read_text(encoding="utf-8")
    assert code.index("finalize_report_receipt(ctx,") < code.index("auto_delivery(package_result, export_cfg)")
    assert code.index("auto_delivery(package_result, export_cfg)") < code.index("return ok({")
    assert "second_curation_export" in code
    assert "curator_delivery.json" in code


def test_15_real_core_package_validator_accepts_synthetic_export(tmp_path):
    # This test does NOT require or claim real video inference.
    from test_v43_handoff import analysis_fixture
    from ldporto.second_curation_export import build_core_package, validate_core_package
    root = fake_curator(tmp_path)
    analysis = analysis_fixture()
    analysis["metadata"]["source"]["id"] = "SYNTHETIC_VALIDATED"
    analysis.setdefault("run_manifest", {})["run_id"] = "VALIDATED_SYNTHETIC_RUN"
    package = build_core_package(analysis, output_dir=tmp_path / "official_core")
    assert validate_core_package(package["path"])["status"] == "valid"
    result = delivery.deliver_package(package["path"], curator_root=root, expected_sha=package["zip_sha256"])
    assert result["delivery_status"] == "DELIVERED"
    assert result["curator_import_status"] == "CURATOR_IMPORT_PENDING"
    assert delivery.file_hash(result["zip"]["path"]) == package["zip_sha256"]
    assert Path(result["receipt_path"]).is_file()


def test_16_config_accepts_local_curator_options_without_unknown_field_errors():
    from ldporto.config import DEFAULTS, merge, validate
    cfg = merge(DEFAULTS, {"export": {"curator_delivery_auto": False,
                                     "curator_delivery_root": "C:/Meus Projetos/Curator"}})
    validate(cfg)
    assert cfg["export"]["curator_delivery_auto"] is False
    assert cfg["export"]["curator_delivery_root"] == "C:/Meus Projetos/Curator"


def test_17_config_rejects_wrong_types_and_empty_curator_path():
    from ldporto.config import DEFAULTS, merge, validate
    for invalid in (123, True, "  "):
        cfg = merge(DEFAULTS, {"export": {"curator_delivery_root": invalid}})
        with pytest.raises(ValueError, match="curator_delivery_root"):
            validate(cfg)
    cfg = merge(DEFAULTS, {"export": {"curator_delivery_auto": "sim"}})
    with pytest.raises(ValueError, match="curator_delivery_auto"):
        validate(cfg)


def test_18_auto_delivery_can_be_explicitly_disabled(tmp_path):
    result = delivery.auto_delivery(None, config={"curator_delivery_auto": False})
    assert result["delivery_status"] == "DELIVERY_DISABLED"
    assert not (tmp_path / "input").exists()


def test_19_windows_handoff_gate_accepts_script_only_input_layout():
    gate = (Path(__file__).resolve().parents[2] /
            "scripts/windows/testing/VALIDAR_ENTREGA_CURATOR.ps1").read_text(encoding="utf-8")
    assert "git.exe check-ignore --no-index -q" in gate
    assert "input/videos/abcdefghijk/source.mp4" in gate
    assert "input/analyzer/__git_gate__/run/SECOND_CURATION.zip" in gate
    assert "git.exe ls-files -- input/analyzer input/videos input/curadorias" in gate
    assert "input/scripts/__git_gate__/REVISION.json" in gate
    assert "Select-String -LiteralPath \".gitignore\" -Pattern '^\\s*/input/\\s*$'" not in gate


def test_20_cli_reports_verified_delivery_and_not_unverified_import():
    root = Path(__file__).resolve().parents[2]
    code = (root / "analyze.py").read_text(encoding="utf-8")
    assert "ANÁLISE FINALIZADA — PACOTE ENTREGUE AO VIDEO CURATOR" in code
    assert "delivery.get('curator_import_status')" in code
    assert "delivery.get('destination')" in code
    assert "delivery.get('analysis_state')" in code
    assert "delivery.get('delivery_status') in ('DELIVERED', 'ALREADY_DELIVERED')" in code
    assert "VIDEO CURATOR: DELIVERY_BLOCKED" in code

def _windows_rename_error(code=5):
    error = PermissionError(13, "synthetic Windows directory rename denied")
    error.winerror = code
    return error


def test_21_windows_transient_rename_denial_retries_then_commits_atomically(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    real_rename = delivery.os.rename
    calls = []

    def transient(source_dir, destination):
        calls.append((source_dir, destination))
        if len(calls) <= 2:
            raise _windows_rename_error(5)
        return real_rename(source_dir, destination)

    with patch.object(delivery.os, "rename", side_effect=transient), (
        patch.object(delivery.time, "sleep", return_value=None)
    ):
        delivered = delivery.deliver_package(source, curator_root=root)
    assert delivered["delivery_status"] == "DELIVERED"
    assert len(calls) == 3
    assert Path(delivered["destination"]).is_dir()
    assert source.is_file()
    assert delivery.file_hash(Path(delivered["destination"]) / source.name) == delivery.file_hash(source)


def test_22_windows_persistent_rename_denial_preserves_original_and_reports_cause(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    original_sha = delivery.file_hash(source)
    with patch.object(delivery.os, "rename", side_effect=_windows_rename_error(5)) as rename_mock, (
        patch.object(delivery.time, "sleep", return_value=None)
    ):
        result = delivery.auto_delivery({"path": str(source)}, curator_root=root)
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert "curator_atomic_directory_rename_denied:winerror=5;attempts=6" in result["reason"]
    assert rename_mock.call_count == 6
    assert source.is_file() and delivery.file_hash(source) == original_sha
    assert not (root / "input" / "analyzer" / "VIDEO123" / "RUN_1").exists()
    assert not list((root / "input" / "analyzer" / "VIDEO123").glob(".analyzer-pending-*"))


def test_23_nontransient_rename_errors_are_not_retried(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    with patch.object(delivery.os, "rename", side_effect=_windows_rename_error(123)) as rename_mock, (
        patch.object(delivery.time, "sleep", return_value=None)
    ):
        result = delivery.auto_delivery({"path": str(source)}, curator_root=root)
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert rename_mock.call_count == 1
    assert source.is_file()


def test_24_rename_race_never_overwrites_someone_elses_directory(tmp_path, stubbed_validator):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "run")
    conflicting = root / "input" / "analyzer" / "VIDEO123" / "RUN_1"
    calls = []

    def race(source_dir, destination):
        calls.append(destination)
        Path(destination).mkdir(parents=True, exist_ok=False)
        (Path(destination) / "unrelated.txt").write_text("other publisher", encoding="utf-8")
        raise _windows_rename_error(32)

    with patch.object(delivery.os, "rename", side_effect=race), (
        patch.object(delivery.time, "sleep", return_value=None)
    ):
        result = delivery.auto_delivery({"path": str(source)}, curator_root=root)
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert "delivery_destination_race_without_overwrite" in result["reason"]
    assert len(calls) == 1
    assert (conflicting / "unrelated.txt").read_text(encoding="utf-8") == "other publisher"
    assert source.is_file()





def test_25_validates_byte_identical_snapshot_outside_pending_curator_folder(tmp_path):
    """ZIP reader must never touch pending-stage ZIP; copied bytes stay verified."""
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "analysis")
    source_sha = delivery.file_hash(source)
    validated_paths = []

    def validate_guard(path):
        path = Path(path)
        validated_paths.append(path)
        assert path.is_file()
        assert delivery.file_hash(path) == source_sha
        assert ".analyzer-pending-" not in str(path)
        return synthetic_validator(path)

    # Also block reading ZIP evidence from any .analyzer-pending- directory.
    original_index = delivery._evidence_index
    evidence_paths = []

    def index_guard(path, facts, zip_sha):
        evidence_paths.append(Path(path))
        assert Path(path) == source
        assert zip_sha == source_sha
        return original_index(path, facts, zip_sha)

    with patch.object(delivery, "validate_core_package", side_effect=validate_guard):
        with patch.object(delivery, "_evidence_index", side_effect=index_guard):
            result = delivery.deliver_package(source, curator_root=root, expected_sha=source_sha)
    assert result["delivery_status"] == "DELIVERED"
    assert len(validated_paths) == 2
    assert validated_paths[0] == source
    assert validated_paths[1] != source
    assert "ldporto-handoff-zip-validation-" in str(validated_paths[1])
    assert not validated_paths[1].exists()  # Snapshot removed after successful check.
    assert evidence_paths == [source]
    assert delivery.file_hash(Path(result["destination"]) / source.name) == source_sha
    assert delivery.file_hash(source) == source_sha


def test_26_snapshot_validation_rejection_never_publishes_an_unverified_package(tmp_path):
    root = fake_curator(tmp_path)
    source = fake_zip(tmp_path / "analysis")
    original_sha = delivery.file_hash(source)
    validated_paths = []

    def reject_snapshot(path):
        path = Path(path)
        validated_paths.append(path)
        if "ldporto-handoff-zip-validation-" in str(path):
            return {"status": "failed", "errors": ["synthetic_copy_rejected"]}
        return {"status": "valid", "errors": []}

    with patch.object(delivery, "validate_core_package", side_effect=reject_snapshot):
        result = delivery.auto_delivery(
            {"path": str(source), "zip_sha256": original_sha}, curator_root=root
        )
    assert result["delivery_status"] == "DELIVERY_BLOCKED"
    assert "copied_zip_validation_failed:synthetic_copy_rejected" in result["reason"]
    assert len(validated_paths) == 2
    assert not (root / "input" / "analyzer" / "VIDEO123" / "RUN_1").exists()
    assert not list((root / "input" / "analyzer" / "VIDEO123").iterdir())
    assert delivery.file_hash(source) == original_sha


def test_27_original_and_stage_are_checked_after_offstage_validation(tmp_path):
    code = (Path(__file__).resolve().parents[1] / "ldporto" /
            "local_curator_handoff.py").read_text(encoding="utf-8")
    assert 'tempfile.TemporaryDirectory(prefix="ldporto-handoff-zip-validation-")' in code
    assert 'if file_hash(snapshot) != expected_sha:' in code
    assert 'validation = validate_core_package(snapshot)' in code
    assert 'if file_hash(target) != expected_sha or file_hash(package) != expected_sha:' in code
    assert 'index_document = _evidence_index(package, facts, copied_sha)' in code
    assert 'if file_hash(staging / package.name) != original_sha or file_hash(package) != original_sha:' in code
    assert "os.replace(staging, folder)" not in code
    assert "os.rename(staging, folder)" in code
