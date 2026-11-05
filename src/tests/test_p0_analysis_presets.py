"""P0-04 tests for explicit analysis presets without GUI or inference."""
import ast
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app.py"
PRESETS = ROOT / "src/ldporto/gui/presets.py"


def load_presets():
    spec = importlib.util.spec_from_file_location("analyzer_p0_presets", PRESETS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeVar:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class P0ProfilePresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.presets = load_presets()
        cls.app_source = APP.read_text(encoding="utf-8")
        syntax = ast.parse(cls.app_source)
        app = next(n for n in syntax.body if isinstance(n, ast.ClassDef) and n.name == "App")
        cls.methods = {n.name: n for n in app.body if isinstance(n, ast.FunctionDef)}

    def body(self, name):
        self.assertIn(name, self.methods)
        return ast.get_source_segment(self.app_source, self.methods[name]) or ""

    def test_01_profile_selection_is_explicit_and_custom_by_default(self):
        constructor = self.body("__init__")
        self.assertIn('self.analysis_profile = tk.StringVar(value="Personalizado")', constructor)
        self.assertIn('state="readonly"', constructor)
        self.assertIn('"<<ComboboxSelected>>"', constructor)
        self.assertIn("self.apply_analysis_profile()", constructor)

    def test_02_presets_contain_only_asr_and_ollama_profile(self):
        expected = {
            "Qualidade (large-v3)": ("large-v3", "max"),
            "Equilibrado (medium)": ("medium", "balanced"),
            "Rápido (turbo)": ("turbo", "fast"),
        }
        for name, (asr, semantic) in expected.items():
            with self.subTest(name=name):
                options = self.presets.preset_settings(name)
                self.assertEqual(options, {"asr_model": asr, "ollama_profile": semantic})
        self.assertIsNone(self.presets.preset_settings("Personalizado"))

    def test_03_profile_settings_do_not_share_mutable_state(self):
        a = self.presets.preset_settings("Rápido (turbo)")
        a["asr_model"] = "not-the-preset"
        b = self.presets.preset_settings("Rápido (turbo)")
        self.assertEqual(b["asr_model"], "turbo")

    def test_04_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Perfil nao reconhecido"):
            self.presets.preset_settings("unknown")

    def test_05_apply_updates_only_two_existing_variables(self):
        code = self.body("apply_analysis_profile")
        self.assertIn('self.model.set(settings["asr_model"])', code)
        self.assertIn('self.ollama_profile.set(settings["ollama_profile"])', code)
        for forbidden in ("self.device.set(", "self.ollama.set(", "self.allow_download.set(",
                          "self.hf_token.set(", "self.force.set(", "self.vision.set(",
                          "self.diarization.set(", "self.ollama_model.set("):
            self.assertNotIn(forbidden, code)

    def isolated_method(self, name, *, globals_dict=None):
        """Execute only the parsed App method, without starting Tkinter."""
        self.assertIn(name, self.methods)
        module = ast.fix_missing_locations(
            ast.Module(body=[self.methods[name]], type_ignores=[])
        )
        namespace = dict(globals_dict or {})
        exec(compile(module, str(APP), "exec"), namespace)
        return namespace[name]

    def test_06_manual_changes_turn_named_profile_into_custom(self):
        code = self.body("on_manual_analysis_setting_change")
        self.assertIn('getattr(self, "_applying_analysis_profile", False)', code)
        self.assertIn('self.analysis_profile.set("Personalizado")', code)
        constructor = self.body("__init__")
        for name in ("self.model", "self.device", "self.ollama", "self.ollama_model", "self.ollama_profile"):
            self.assertIn(name, constructor)
        self.assertIn('trace_add("write", lambda *_: self.on_manual_analysis_setting_change())', constructor)

        callback = self.isolated_method("on_manual_analysis_setting_change")
        summary = Mock()
        state = SimpleNamespace(
            analysis_profile=FakeVar("Qualidade (large-v3)"),
            update_analysis_profile_summary=summary,
        )
        callback(state)
        self.assertEqual(state.analysis_profile.get(), "Personalizado")
        summary.assert_called_once_with()

        # Changes triggered by applying a preset must NOT clear its name.
        state.analysis_profile.set("Rápido (turbo)")
        state._applying_analysis_profile = True
        summary.reset_mock()
        callback(state)
        self.assertEqual(state.analysis_profile.get(), "Rápido (turbo)")
        summary.assert_not_called()

    def test_07_effective_summary_shows_actual_values_and_no_fake_benchmarks(self):
        text = self.presets.describe_effective_profile(
            "Rápido (turbo)", "turbo", "cpu", False, "qwen3:14b", "fast"
        )
        self.assertIn("ASR: turbo", text)
        self.assertIn("Dispositivo: cpu", text)
        self.assertIn("Ollama desligado", text)
        self.assertIn("não medidos", text)
        enabled = self.presets.describe_effective_profile(
            "Personalizado", "large-v3", "cuda", True, "qwen3:14b", "max"
        )
        self.assertIn("Ollama qwen3:14b / max", enabled)

    def test_08_existing_cli_model_device_and_semantic_options_are_unchanged(self):
        checked = self.body("_start_checked")
        self.assertIn('"--model", self.model.get()', checked)
        self.assertIn('"--device", self.device.get()', checked)
        self.assertIn('"--semantic", "ollama" if self.ollama.get() else "heuristic"', checked)
        self.assertIn('"--ollama-profile", self.ollama_profile.get()', checked)

    def test_09_presets_have_no_inference_network_or_file_writes(self):
        code = PRESETS.read_text(encoding="utf-8")
        module = ast.parse(code)
        self.assertFalse(any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in module.body))
        for bad in ("subprocess", "torch", "requests", "open(", "download", "Popen", "yaml"):
            self.assertNotIn(bad, code)

    def test_10_no_implicit_download_or_security_setting_changes(self):
        for name in ("apply_analysis_profile", "on_manual_analysis_setting_change"):
            code = self.body(name)
            for token in ("--allow-download", "allow_download.set(", "media_sha256.set(",
                          "local_original.set(", "_start_checked(", "self.launch(",
                          "subprocess.Popen(", "config.yaml"):
                self.assertNotIn(token, code)

    def test_11_applying_preset_changes_only_expected_values_in_headless_runtime(self):
        apply = self.isolated_method(
            "apply_analysis_profile",
            globals_dict={"preset_settings": self.presets.preset_settings},
        )
        summary = Mock()
        state = SimpleNamespace(
            analysis_profile=FakeVar("Equilibrado (medium)"),
            model=FakeVar("tiny"),
            ollama_profile=FakeVar("fast"),
            device=FakeVar("cuda"),
            ollama=FakeVar(False),
            ollama_model=FakeVar("qwen3:14b"),
            allow_download=FakeVar(False),
            media_sha256=FakeVar("f" * 64),
            update_analysis_profile_summary=summary,
        )
        apply(state)
        self.assertEqual(state.model.get(), "medium")
        self.assertEqual(state.ollama_profile.get(), "balanced")
        self.assertEqual(state.device.get(), "cuda")
        self.assertIs(state.ollama.get(), False)
        self.assertEqual(state.ollama_model.get(), "qwen3:14b")
        self.assertIs(state.allow_download.get(), False)
        self.assertEqual(state.media_sha256.get(), "f" * 64)
        self.assertIs(state._applying_analysis_profile, False)
        summary.assert_called_once_with()

        # Switching back to Custom must not rewrite the manual values.
        state.analysis_profile.set("Personalizado")
        state.model.set("small")
        state.ollama_profile.set("max")
        apply(state)
        self.assertEqual(state.model.get(), "small")
        self.assertEqual(state.ollama_profile.get(), "max")
        self.assertEqual(summary.call_count, 2)


if __name__ == "__main__":
    unittest.main()
