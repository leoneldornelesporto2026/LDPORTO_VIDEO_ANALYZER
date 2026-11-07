"""Canonical Analyzer R6 text snapshot, only after local human Git-review opt-in."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/dev/export_r6_git_review.py"
SPEC = importlib.util.spec_from_file_location("r6_git_review", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class R6GitEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="r6_git_snapshot_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.delivery = self.root / "curator" / "input" / "analyzer" / "VIDEO123" / "RUN_ABC"
        self.delivery.mkdir(parents=True)
        self.destination = self.root / "analyzer" / "docs" / "analyzer_runs"
        self.files = {
            "source/metadata.json": b'{"sha256":"' + b"a" * 64 + b'"}',
            "editorial/candidate_catalog.json": b'{"candidates":[{"candidate_id":"X"}]}',
            "transcript/transcript.srt": b"1\n00:00:00,000 --> 00:00:01,000\nOriginal words\n",
            "transcript/relevant_segments.jsonl": b'{"text":"Original words"}\n',
            "camera/candidate_camera_plans.json": b'{"camera":"pending_review"}',
            "images/contact_sheet.jpg": b"\xff\xd8\xff\x00 fake media ignored by Git",
        }
        self._write()

    def _write(self, override=None):
        content = dict(self.files)
        if override:
            content.update(override)
        manifest = {
            "run_id": "RUN_ABC",
            "files": [
                {"path": name, "bytes": len(raw),
                 "sha256": sha256(raw).hexdigest()}
                for name, raw in content.items()
            ],
        }
        zip_path = self.delivery / "SECOND_CURATION_RUN_ABC.zip"
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as z:
            for name, raw in content.items():
                z.writestr(name, raw)
            z.writestr("SECOND_CURATION_MANIFEST.json",
                       json.dumps(manifest).encode("utf-8"))
        receipt = {
            "run_id": "RUN_ABC", "source_sha256": "a" * 64,
            "human_approval": False, "publication_ready": False,
            "curator_import_status": "CURATOR_IMPORT_PENDING",
            "zip": {"name": zip_path.name, "bytes": zip_path.stat().st_size,
                    "sha256": audit.digest(zip_path)},
        }
        (self.delivery / "ANALYZER_TO_CURATOR_HANDOFF.json").write_text(
            json.dumps(receipt), encoding="utf-8")
        return zip_path

    def test_default_is_read_only_full_text_inventory(self):
        result = audit.plan_snapshot(self.delivery)
        self.assertEqual(result["status"], "GIT_TEXT_REVIEW_PENDING")
        self.assertEqual(result["zip_members_total"], 7)
        self.assertEqual(len(result["git_text_files"]), 6)
        self.assertEqual(len(result["excluded_binary_files"]), 1)
        self.assertIn("transcript/transcript.srt",
                      [x["path"] for x in result["git_text_files"]])
        self.assertFalse(result["human_approved"])
        self.assertFalse(result["git_push_executed"])
        self.assertFalse(self.destination.exists())

    def test_save_preserves_all_text_bytes_and_does_not_copy_media(self):
        original = audit.digest(self.delivery / "SECOND_CURATION_RUN_ABC.zip")
        folder = audit.save_snapshot(self.delivery, self.destination)
        self.assertEqual(folder, audit.save_snapshot(self.delivery, self.destination))
        for path, raw in self.files.items():
            if path.lower().endswith(".jpg"):
                self.assertFalse((folder / "evidence" / path).exists())
            else:
                self.assertEqual((folder / "evidence" / path).read_bytes(), raw)
        self.assertEqual(original, audit.digest(self.delivery / "SECOND_CURATION_RUN_ABC.zip"))
        self.assertFalse(any(p.suffix == ".mp4" for p in folder.rglob("*")))
        report = json.loads((folder / "ANALYZER_GIT_EVIDENCE_MANIFEST.json").read_text())
        self.assertEqual(report["source_zip_sha256"], original)
        self.assertIn("images/contact_sheet.jpg",
                      [x["path"] for x in report["excluded_binary_files"]])

    def test_missing_save_confirmation_prevents_any_disk_writes(self):
        with self.assertRaisesRegex(ValueError, "--confirm-git-text-review"):
            audit.main(["--delivery", str(self.delivery),
                        "--destination-root", str(self.destination), "--save"])
        self.assertFalse(self.destination.exists())

    def test_modified_existing_srt_cannot_be_overwritten(self):
        folder = audit.save_snapshot(self.delivery, self.destination)
        srt = folder / "evidence/transcript/transcript.srt"
        srt.write_bytes(b"human changed")
        with self.assertRaisesRegex(ValueError, "modificado"):
            audit.save_snapshot(self.delivery, self.destination)
        self.assertEqual(srt.read_bytes(), b"human changed")

    def test_tampered_zip_is_blocked_before_any_write(self):
        package = self.delivery / "SECOND_CURATION_RUN_ABC.zip"
        package.write_bytes(package.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "recibo"):
            audit.save_snapshot(self.delivery, self.destination)
        self.assertFalse(self.destination.exists())

    def test_missing_manifest_member_is_rejected(self):
        z = self._write({"unmanifested.txt": b"some text"})
        with ZipFile(z, "r") as original:
            files = {name: original.read(name) for name in original.namelist()}
        manifest = json.loads(files["SECOND_CURATION_MANIFEST.json"])
        manifest["files"] = manifest["files"][:-1]
        files["SECOND_CURATION_MANIFEST.json"] = json.dumps(manifest).encode()
        with ZipFile(z, "w", ZIP_DEFLATED) as next_zip:
            for name, raw in files.items():
                next_zip.writestr(name, raw)
        receipt_path = self.delivery / "ANALYZER_TO_CURATOR_HANDOFF.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["zip"]["sha256"] = audit.digest(z)
        receipt["zip"]["bytes"] = z.stat().st_size
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "Manifesto"):
            audit.plan_snapshot(self.delivery)

    def test_path_traversal_zip_blocked(self):
        self._write({"../escaped.json": b"{}"})
        with self.assertRaisesRegex(ValueError, "inseguros"):
            audit.plan_snapshot(self.delivery)


if __name__ == "__main__":
    unittest.main()
