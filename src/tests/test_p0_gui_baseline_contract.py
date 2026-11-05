"""P0-01: static, headless protection of existing Tkinter GUI contracts.

No GUI windows, network, models, subprocesses, or real video are executed.
Behavioral media/GUI suites are still required for acceptance.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUI_PATH = ROOT / "app.py"
CLI_PATH = ROOT / "analyze.py"


class P0GuiBaselineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GUI_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(GUI_PATH))
        apps = [n for n in cls.tree.body if isinstance(n, ast.ClassDef) and n.name == "App"]
        assert len(apps) == 1, "Existing public App class must remain"
        cls.app = apps[0]
        cls.methods = {n.name: n for n in cls.app.body if isinstance(n, ast.FunctionDef)}
        cls.helpers = {n.name: n for n in cls.tree.body if isinstance(n, ast.FunctionDef)}

    def method_text(self, name):
        self.assertIn(name, self.methods)
        return ast.get_source_segment(self.source, self.methods[name]) or ""

    def helper_text(self, name):
        self.assertIn(name, self.helpers)
        return ast.get_source_segment(self.source, self.helpers[name]) or ""

    def test_01_public_entrypoints_exist(self):
        for name in ("ABRIR_ANALYZER.bat", "app.py", "analyze.py", "config/config.yaml",
                     "DIAGNOSTICO_WINDOWS.bat", "TESTAR_WINDOWS.bat"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())
        cli = ast.parse(CLI_PATH.read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in cli.body))

    def test_02_view_and_action_methods_remain(self):
        required = {"__init__", "start", "_start_checked", "launch", "poll", "stop",
                    "close", "verify_media", "handle_media_result", "change_media_selection",
                    "build_execution_screens", "show_execution", "show_completion",
                    "open_results_center", "new_analysis", "resume_camera",
                    "export_visual_handoff", "export_project_dossier", "verify_ocr",
                    "refresh_execution"}
        self.assertFalse(required - self.methods.keys())

    def test_03_direct_button_callbacks_are_defined(self):
        callbacks = set()
        for node in ast.walk(self.app):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    v = kw.value
                    if (kw.arg == "command" and isinstance(v, ast.Attribute)
                            and isinstance(v.value, ast.Name) and v.value.id == "self"):
                        callbacks.add(v.attr)
        self.assertGreaterEqual(len(callbacks), 12)
        self.assertFalse(callbacks - self.methods.keys())
        self.assertTrue({"start", "stop", "verify_media", "open_results_center"} <= callbacks)

    def test_04_critical_option_state_is_preserved(self):
        fields = {n.attr for n in ast.walk(self.methods["__init__"])
                  if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                  and n.value.id == "self"}
        required = {"source", "allow_download", "local_original", "media_sha256",
                    "model", "device", "ollama", "ollama_model", "ollama_profile",
                    "camera_enabled", "smart_zoom", "social_aspect", "caption_preset",
                    "ocr_enabled", "diarization", "vision", "hf_token", "start_button"}
        self.assertFalse(required - fields)

    def test_05_new_source_revokes_old_download_permission(self):
        code = self.method_text("change_media_selection")
        for token in ("self.media_generation += 1", "self.media_check_result = None",
                      "self.allow_download.set(False)"):
            self.assertIn(token, code)

    def test_06_media_validation_runs_in_worker(self):
        code = self.method_text("verify_media")
        for token in ("inspect_media_selection", "threading.Thread", "self.messages.put",
                      "media_result", "media_generation"):
            self.assertIn(token, code)

    def test_07_stale_media_results_cannot_start(self):
        code = self.method_text("handle_media_result")
        for token in ("generation != self.media_generation",
                      "options != self.media_options()",
                      "not getattr(self, 'closing_requested', False)", "self._start_checked()"):
            self.assertIn(token, code)

    def test_08_download_requires_opt_in(self):
        options = self.helper_text("media_cli_options")
        checked = self.method_text("_start_checked")
        self.assertIn("if allow_download:", options)
        self.assertIn("'--allow-download'", options)
        self.assertIn("self.allow_download.get()", checked)
        self.assertIn("OPERATOR_SELECTION_REQUIRED", checked)

    def test_09_hash_and_original_source_are_bound(self):
        options = self.helper_text("media_cli_options")
        inspect = self.helper_text("inspect_media_selection")
        for token in ("'--media-sha256'", "'--media-path'"):
            self.assertIn(token, options)
        self.assertIn("expected_sha256", inspect)
        self.assertIn("resolve_existing_media", inspect)

    def test_10_gui_invokes_existing_cli_in_subprocess(self):
        code = self.method_text("launch")
        for token in ("subprocess.Popen", "sys.executable", '"analyze.py"',
                      "cwd=ROOT", "EVENT_PREFIX"):
            self.assertIn(token, code)
        self.assertNotIn("shell=True", code)

    def test_11_quality_and_social_cli_flags_remain(self):
        code = self.method_text("_start_checked")
        for flag in ("--model", "--device", "--semantic", "--ollama-model",
                     "--ollama-profile", "--no-diarization", "--no-vision",
                     "--social-aspect", "--caption-preset", "--story-count"):
            with self.subTest(flag=flag):
                self.assertIn(flag, code)

    def test_12_safe_stop_preserves_checkpoints(self):
        code = self.method_text("stop")
        self.assertIn("CANCEL_REQUESTED", code)
        self.assertIn("safe_stop_requested", code)
        self.assertNotIn("self.proc.terminate(", code)

    def test_13_publication_and_preview_approval_stay_separate(self):
        code = self.method_text("show_completion")
        for token in ("preview_approved", "publication_ready", "final_readiness",
                      "nao registrado"):
            self.assertIn(token, code)

    def test_14_progress_remains_measured(self):
        self.assertIn("WeightedProgress()", self.method_text("__init__"))
        self.assertIn("STAGE_LABELS", self.method_text("build_execution_screens"))
        code = self.method_text("refresh_execution")
        for token in ("self.progress_model.snapshot()", "overall_fraction", "stage_eta_seconds"):
            self.assertIn(token, code)

    def test_15_setup_execution_and_completion_views_exist(self):
        self.assertIn("self.configuration_frame", self.method_text("__init__"))
        self.assertIn("self.configuration_footer", self.method_text("__init__"))
        screens = self.method_text("build_execution_screens")
        self.assertIn("self.execution_frame", screens)
        self.assertIn("self.final_frame", screens)


if __name__ == "__main__":
    unittest.main()
