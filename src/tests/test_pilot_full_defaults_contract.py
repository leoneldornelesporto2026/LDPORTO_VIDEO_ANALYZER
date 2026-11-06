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
        self.assertIn('pytest -q src/tests @historicalDeselectArgs',self.script)
        self.assertIn('CURRENT_BASELINE_PASS_7_HISTORICAL_TESTS_DESELECTED',self.script)
        self.assertIn('historical_full_suite_passed=($historicalMode -eq "FULL_VERIFIED")',self.script)
        self.assertIn('CURRENT_BASELINE_AND_REAL_TECHNICAL_PREVIEW_PASS_HISTORICAL_PENDING',self.script)

    def test_seven_specific_historical_nodes_are_audited_not_whole_files(self):
        import ast
        ids=[]
        for line in self.script.splitlines():
            item=line.strip().rstrip(',')
            if item.startswith('"src/tests/test_') and '::test_' in item:
                ids.append(item.strip('"'))
        required={
            'src/tests/test_historical_fixture_provenance.py::test_relocated_historical_zip_bytes_match_original_provenance',
            'src/tests/test_stage13_explainability.py::test_all_52_historical_candidates_receive_stable_diagnostics',
            'src/tests/test_stage17_editorial_replay.py::test_real_same_52_ids_reproducible_and_unapproved',
            'src/tests/test_stage17_editorial_replay.py::test_mismatched_run_rejected',
            'src/tests/test_stage17_editorial_replay.py::test_missing_upstream_does_not_promote',
            'src/tests/test_stage18_handoff_audit.py::test_real_historical_fixture_hashes_links_and_contact_sheets',
            'src/tests/test_stage19_uncertain_words.py::test_historical_flags_are_not_the_prompt_percentage'
        }
        self.assertEqual(len(ids),7)
        self.assertEqual(set(ids),required)
        for item in ids:
            path,func=item.split('::')
            parsed=ast.parse((ROOT/path).read_text(encoding='utf-8'))
            functions={node.name for node in ast.walk(parsed)
                       if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
            self.assertIn(func,functions)
        self.assertIn('HISTORICAL_PENDING:',self.script)
        self.assertIn('$deselectedTests=@($historicalTestIds)',self.script)

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
        self.assertIn('-AllowDownload:$AllowDownload',self.script)
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
    def test_powershell_51_calls_child_script_with_named_parameters(self):
        self.assertIn(
            '& $pilot -SourceUrl $SourceUrl -SmokeCount 1 -MediaPath $media -AllowDownload:$AllowDownload',
            self.script)
        self.assertNotIn('& $pilot @pilotArgs',self.script)
        self.assertNotIn('$pilotArgs=@("-SourceUrl"',self.script)

    def test_fast_resume_is_explicit_and_restricted_to_logged_suite_baselines(self):
        self.assertIn('[switch]$ResumeAfterValidatedSuites',self.script)
        self.assertIn('751ac18e47765a918c859d194a60871a891616ac',self.script)
        self.assertIn('70c3c7150d1f84057fb0dbda819f5fef0218544b',self.script)
        self.assertIn('git.exe -C $analyzer diff --name-only $testedAnalyzer HEAD',self.script)
        self.assertIn('foreach ($changedFile in $filesChanged)',self.script)
        self.assertIn('if ($changedFile -notin $allowedOnly)',self.script)
        self.assertIn('src/tests/test_pilot_e2e_windows_contract.py',self.script)
        self.assertIn('RESUMED_REAL_TECHNICAL_PREVIEW_WITH_PRIOR_SUITES_HISTORICAL_PENDING',self.script)
        self.assertIn('suites_executed_nesta_invocacao=(-not $ResumeAfterValidatedSuites)',self.script)
        self.assertIn('suites_retoma_com_evidencia_anterior=[bool]$ResumeAfterValidatedSuites',self.script)
        self.assertNotIn('suite_curator="FULL_SUITE_PASS"',self.script)

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
