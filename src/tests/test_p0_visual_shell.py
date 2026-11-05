"""P0-02: isolated, headless tests of the themed navigation shell."""
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUI = ROOT / "app.py"
PARTS = ROOT / "src/ldporto/gui"


class VisualShellP0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GUI.read_text(encoding="utf-8")
        syntax = ast.parse(cls.source)
        app = next(n for n in syntax.body if isinstance(n, ast.ClassDef) and n.name == "App")
        cls.methods = {n.name: n for n in app.body if isinstance(n, ast.FunctionDef)}
        spec = importlib.util.spec_from_file_location("analyzer_gui_navigation", PARTS / "navigation.py")
        cls.navigation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.navigation)

    def test_01_navigation_bounds(self):
        f = self.navigation.scroll_fraction
        self.assertEqual(f(100, 500, 600), 0.0)
        self.assertEqual(f(-20, 500, 200), 0.0)
        self.assertAlmostEqual(f(100, 500, 200), .2)
        self.assertAlmostEqual(f(999, 500, 200), .6)

    def test_02_all_six_anchor_sections_exist(self):
        for key in ("origem", "asr", "camera", "social", "ocr", "logs"):
            with self.subTest(section=key):
                self.assertIn('mark_section("' + key + '"', self.source)
        self.assertIn("navigate_to_section", self.methods)

    def test_03_primary_action_and_style_exist(self):
        self.assertIn('style="Primary.TButton", command=self.start', self.source)
        self.assertIn("apply_theme(style)", self.source)
        self.assertIn("Primary.TButton", (PARTS / "theme.py").read_text(encoding="utf-8"))

    def test_04_execution_security_contracts_preserved(self):
        for key in ("start", "_start_checked", "launch", "stop", "show_completion",
                    "handle_media_result", "build_execution_screens"):
            self.assertIn(key, self.methods)
        for token in ("CANCEL_REQUESTED", "preview_approved", "publication_ready",
                      "self.allow_download.set(False)", "media_cli_options"):
            self.assertIn(token, self.source)

    def test_05_themed_modules_are_presentation_only(self):
        for name in ("theme.py", "navigation.py"):
            code = (PARTS / name).read_text(encoding="utf-8")
            ast.parse(code)
            for token in ("subprocess", "torch", "ollama", "download", "model.load"):
                self.assertNotIn(token, code)

    def test_06_navigation_moves_canvas_without_starting_analysis(self):
        node = self.methods["navigate_to_section"]
        code = ast.get_source_segment(self.source, node)
        self.assertIn("scroll_fraction(", code)
        self.assertIn("yview_moveto(", code)
        self.assertNotIn("Popen", code)
        self.assertNotIn("_start_checked(", code)


if __name__ == "__main__":
    unittest.main()
