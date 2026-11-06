"""Static safety contracts for the Windows real-pilot operator script.

These tests do NOT pretend to run inference, GitHub, YouTube or PowerShell.
Physical acceptance still requires a real Windows run and its local receipts.
"""
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/windows/testing/PILOTO_E2E_REAL.ps1"


class PilotE2EWindowsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_01_file_exists_and_requires_source_or_reuse(self):
        self.assertTrue(SCRIPT.is_file())
        self.assertIn('DefaultParameterSetName="New"', self.script)
        self.assertIn('[string]$SourceUrl', self.script)
        self.assertIn('[string]$AnalysisDir', self.script)

    def test_02_download_is_explicit_and_local_media_has_sha(self):
        self.assertIn('if ($AllowDownload) { $arguments+="--allow-download" }', self.script)
        self.assertIn('if ($media)', self.script)
        self.assertIn('"--media-sha256"', self.script)
        self.assertIn('Informe -MediaPath com a fonte local ou -AllowDownload explicitamente.', self.script)

    def test_03_both_branches_must_be_develop(self):
        self.assertIn('foreach ($repoRoot in @($analyzer,$curator))', self.script)
        self.assertIn('if ($branch -ne "develop")', self.script)
        self.assertNotIn('git pull', self.script)
        self.assertNotIn('git push', self.script)

    def test_04_real_delivery_and_sha_integrity_gate(self):
        self.assertIn('VALIDAR_ENTREGA_CURATOR.ps1', self.script)
        self.assertIn('-AnalysisDir $folder -CuratorRoot $curator', self.script)
        self.assertIn('curator_delivery.json', self.script)
        self.assertIn('ALREADY_DELIVERED', self.script)

    def test_05_draft_is_test_only_no_render(self):
        self.assertIn('r6-smoke', self.script)
        self.assertIn('r6-media-audit', self.script)
        self.assertIn('render_ready=$false', self.script)
        self.assertIn('human_approved=$false', self.script)
        self.assertIn('published=$false', self.script)
        self.assertNotIn('batch-finals', self.script)
        self.assertNotIn('--force', self.script)

    def test_06_report_written_under_ignored_analysis_root(self):
        self.assertIn('analysis\\pilot_e2e_', self.script)
        self.assertIn('PILOT_E2E_REPORT.json', self.script)
        self.assertIn('ConvertTo-Json -Depth 8', self.script)
        gitignore = (SCRIPT.parents[3] / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('analysis/', gitignore)


if __name__ == "__main__":
    unittest.main()
