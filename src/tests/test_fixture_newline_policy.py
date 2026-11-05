"""Unit tests for safe, immutable stage55 fixture newline repair (no GPU)."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/windows/testing/REPARAR_EOL_FIXTURE_STAGE55.py"
spec = importlib.util.spec_from_file_location("stage55_eol_repair", SCRIPT)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class Stage55FixtureNewlineTests(unittest.TestCase):
    def test_01_hash_matches_original_repository_fixture_after_lf_normalization(self):
        raw = (ROOT / "src/tests/fixtures/stage55_commercial_synthetic.json").read_bytes()
        state, normalized = repair.assess(raw)
        self.assertIn(state, {"valid", "crlf_only"})
        self.assertEqual(repair.digest(normalized), repair.EXPECTED)

    def test_02_crlf_only_is_recoverable(self):
        original = b'{"fixture":true}\n'
        expected = hashlib.sha256(original).hexdigest()
        status, normalized = repair.assess(original.replace(b"\n", b"\r\n"), expected)
        self.assertEqual(status, "crlf_only")
        self.assertEqual(normalized, original)

    def test_03_content_change_is_never_normalized_into_approval(self):
        original = b'{"fixture":true}\n'
        expected = hashlib.sha256(original).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            altered = b'{"fixture":false}\r\n'
            path.write_bytes(altered)
            with self.assertRaisesRegex(ValueError, "BLOQUEADO"):
                repair.repair_fixture(path, apply=True, expected_sha=expected)
            self.assertEqual(path.read_bytes(), altered)

    def test_04_repairs_only_matching_crlf_bytes(self):
        original = b'{"fixture":true}\n'
        expected = hashlib.sha256(original).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_bytes(original.replace(b"\n", b"\r\n"))
            result = repair.repair_fixture(path, apply=True, expected_sha=expected)
            self.assertIn("REPARADO", result)
            self.assertEqual(path.read_bytes(), original)

    def test_05_idempotent_on_correct_fixture(self):
        original = b'{"fixture":true}\n'
        expected = hashlib.sha256(original).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_bytes(original)
            self.assertIn("OK:", repair.repair_fixture(path, apply=True, expected_sha=expected))
            self.assertEqual(path.read_bytes(), original)

    def test_06_gitattributes_disables_eol_conversion_for_immutable_fixture(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn(
            "src/tests/fixtures/stage55_commercial_synthetic.json -text",
            attributes
        )


if __name__ == "__main__":
    unittest.main()
