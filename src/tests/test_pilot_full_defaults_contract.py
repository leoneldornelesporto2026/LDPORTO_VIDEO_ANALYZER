"""Safety contract for full-suite / real-video / technical-preview pilot.

These are static checks; only execution on the user's Windows can establish a
real pass of the two full suites, source processing, ZIP handoff and FFmpeg video.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/windows/testing/PILOTO_FULL_DEFAULTS.ps1'


class FullDefaultsPilotContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script=SCRIPT.read_text(encoding='utf-8')
    def test_full_analyzer_suite_and_fixture_integrity_gate(self):
        self.assertIn('VALIDAR_P0_GUI.ps1',self.script)
        self.assertIn(' -FullSuite',self.script)
        self.assertIn('Assert-Exit "Suite completa Analyzer',self.script)
    def test_missing_historical_fixtures_use_exact_originals_and_block_otherwise(self):
        self.assertIn('RESTAURAR_FIXTURES_HISTORICAS.ps1',self.script)
        self.assertIn('FixtureSearchRoot',self.script)
        self.assertIn('Assert-Exit "Restauracao de fixtures originais"',self.script)
        self.assertIn('CHATGPT_REVIEW.zip',self.script)
        self.assertIn('SECOND_CURATION_READY.zip',self.script)
        self.assertIn('Get-FileHash -LiteralPath $target -Algorithm SHA256',self.script)
        self.assertIn('BLOQUEADO: SHA256 da fixture diferente',self.script)
        self.assertIn('BLOQUEADO: tamanho da fixture diferente',self.script)
        self.assertNotIn('--ignore=',self.script)

    def test_missing_historical_baseline_requires_explicit_switch(self):
        self.assertIn('[switch]$CurrentBaselineWithoutHistoricalFixtures',self.script)
        self.assertIn('if ($fixtureMissing.Count -gt 0 -and $CurrentBaselineWithoutHistoricalFixtures)',self.script)
        self.assertIn('$historicalMode="HISTORICAL_FIXTURES_MISSING"',self.script)
        self.assertIn('BLOQUEADO: SHA256 da fixture diferente',self.script)

    def test_current_baseline_runs_all_other_analyzer_tests_without_false_full_pass(self):
        self.assertIn('VALIDAR_P0_GUI.ps1")',self.script)
        self.assertIn('pytest -q src/tests --deselect=src/tests/test_historical_fixture_provenance.py::test_relocated_historical_zip_bytes_match_original_provenance',self.script)
        self.assertIn('CURRENT_BASELINE_PASS_ONE_HISTORICAL_TEST_DESELECTED',self.script)
        self.assertIn('historical_full_suite_passed=($historicalMode -eq "FULL_VERIFIED")',self.script)
        self.assertIn('CURRENT_BASELINE_AND_REAL_TECHNICAL_PREVIEW_PASS_HISTORICAL_PENDING',self.script)

    def test_full_historical_gate_remains_unchanged_for_normal_mode(self):
        self.assertIn('if ($historicalMode -eq "FULL_VERIFIED")',self.script)
        self.assertIn('VALIDAR_P0_GUI.ps1") -FullSuite',self.script)
        self.assertIn('FULL_SUITES_AND_REAL_TECHNICAL_PREVIEW_PASS',self.script)
        self.assertIn('deselected_tests=@($deselectedTests)',self.script)

    def test_full_curator_suite_not_just_selected_r6_tests(self):
        self.assertIn('unittest discover -s tests -p "test_*.py" -v',self.script)
        self.assertIn('Assert-Exit "Suite completa Curator',self.script)
    def test_uses_real_verified_short_nasa_youtube_sample(self):
        self.assertIn('https://www.youtube.com/watch?v=Eo2bUJcxASI',self.script)
        self.assertIn('if ($AllowDownload)',self.script)
        self.assertIn('if (-not $media -and -not $AllowDownload)',self.script)
        self.assertIn('PILOTO_E2E_REAL.ps1',self.script)
    def test_default_yaml_is_unmodified_and_not_downscaled(self):
        self.assertIn('config\\config.yaml',self.script)
        self.assertIn('Get-FileHash',self.script)
        self.assertIn('if ($before -ne $after)',self.script)
        for prohibited in ('--no-vision','--no-diarization','--offline','--device cpu',
                           '--semantic heuristic','--model tiny','--force'):
            self.assertNotIn(prohibited,self.script)
    def test_source_exact_sha_and_real_preview_only(self):
        self.assertIn('r6-review --inbox $inbox --summary',self.script)
        self.assertIn('r6-media-audit --inbox $inbox --media $media',self.script)
        self.assertIn('r6-preview-smoke --inbox $inbox --media $media',self.script)
        self.assertIn('--confirm-preview-test',self.script)
        self.assertIn('TECHNICAL_PREVIEW_REVIEW_REQUIRED',self.script)
    def test_no_git_write_or_false_editorial_approvals(self):
        for action in ('git push','git add','git reset','git checkout','git merge'):
            self.assertNotIn(action,self.script)
        self.assertIn('editorial_r6_to_r57_ready=$false',self.script)
        self.assertIn('human_approved=$false',self.script)
        self.assertIn('publication_ready=$false',self.script)
        self.assertIn('PILOT_FULL_DEFAULTS_REPORT.json',self.script)
        self.assertIn('analysis/',(ROOT/'.gitignore').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
