"""P0-03: static, headless media source card contracts (no Tk window)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class P0MediaCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "app.py").read_text(encoding="utf-8")
        syntax = ast.parse(cls.source)
        app = next(n for n in syntax.body if isinstance(n, ast.ClassDef) and n.name == "App")
        cls.methods = {n.name: n for n in app.body if isinstance(n, ast.FunctionDef)}

    def body(self, name):
        self.assertIn(name, self.methods)
        return ast.get_source_segment(self.source, self.methods[name]) or ""

    def test_01_video_and_youtube_actions_exist(self):
        constructor = self.body("__init__")
        for token in ('text="Selecionar vídeo"', 'text="Informar link do YouTube"',
                      "command=self.select", "command=self.focus_media_link",
                      "self.media_source_entry", "textvariable=self.source"):
            self.assertIn(token, constructor)

    def test_02_explicit_download_consent_remains_unchecked(self):
        body = self.body("__init__")
        self.assertIn("self.allow_download = tk.BooleanVar(value=False)", body)
        self.assertIn("variable=self.allow_download", body)
        self.assertIn("Autorizar download se o original estiver ausente", body)

    def test_03_verify_status_and_integrity_fields_remain(self):
        body = self.body("__init__")
        for token in ("command=self.verify_media", "textvariable=self.media_status",
                      "self.media_details = ttk.Frame", "command=self.select_media_original",
                      "textvariable=self.local_original", "textvariable=self.media_sha256"):
            self.assertIn(token, body)

    def test_04_focus_is_navigation_only(self):
        body = self.body("focus_media_link")
        self.assertIn("self.media_source_entry.focus_set()", body)
        self.assertIn("self.media_source_entry.selection_range(", body)
        for bad in ("source.set(", "allow_download.set(", "verify_media(", "download("):
            self.assertNotIn(bad, body)

    def test_05_optional_details_are_only_shown_or_hidden(self):
        body = self.body("toggle_media_details")
        for key in ("winfo_manager()", "pack_forget()", 'self.media_details.pack(fill="x"',
                    "media_details_button.configure"):
            self.assertIn(key, body)
        for bad in ("source.set(", "media_sha256.set(", "allow_download.set(", "verify_media("):
            self.assertNotIn(bad, body)

    def test_06_media_invalidation_is_not_weakened(self):
        ctor = self.body("__init__")
        for key in ("self.source.trace_add", "clear_original=True",
                    "self.local_original.trace_add", "self.media_sha256.trace_add"):
            self.assertIn(key, ctor)
        invalidate = self.body("change_media_selection")
        for key in ("self.media_generation += 1", "self.media_check_result = None",
                    "self.allow_download.set(False)"):
            self.assertIn(key, invalidate)

    def test_07_existing_hash_and_worker_gates_remain(self):
        checked = self.body("_start_checked")
        media = self.body("handle_media_result")
        self.assertIn("OPERATOR_SELECTION_REQUIRED", checked)
        self.assertIn("self.allow_download.get()", checked)
        self.assertIn("media_cli_options(", checked)
        self.assertIn("generation != self.media_generation", media)
        self.assertIn("options != self.media_options()", media)

    def test_08_theme_is_presentation_only(self):
        theme = (ROOT / "src/ldporto/gui/theme.py").read_text(encoding="utf-8")
        ast.parse(theme)
        for style in ("MediaCard.TFrame", "Media.TEntry", "MediaStatus.TLabel",
                      "MediaAction.TButton", "Media.TCheckbutton"):
            self.assertIn(style, theme)
        for forbidden in ("subprocess", "urllib", "requests.", "torch"):
            self.assertNotIn(forbidden, theme)


if __name__ == "__main__":
    unittest.main()
