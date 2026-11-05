"""Offline static contract for Windows batch entrypoints."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIN = ROOT / "scripts" / "windows"


class WindowsBatchPathsTests(unittest.TestCase):
    def test_dp0_call_targets_exist(self):
        batches = list(ROOT.glob("*.bat")) + list(WIN.rglob("*.bat"))
        self.assertTrue(batches)
        for script in batches:
            content = script.read_text(encoding="utf-8")
            calls = re.findall(r'(?im)^\s*call\s+"%~dp0([^"]+\.bat)"', content)
            for relative in calls:
                target = script.parent.joinpath(*re.split(r"[\\/]+", relative)).resolve()
                with self.subTest(script=script.name, target=relative):
                    self.assertTrue(target.is_file(), str(target))

    def test_diagnostics_dispatch_to_existing_read_only_python(self):
        doctor = (WIN / "diagnostics" / "DIAGNOSTICO_WINDOWS.bat").read_text(encoding="utf-8")
        gpu = (WIN / "diagnostics" / "DIAGNOSTICO_GPU_WINDOWS.bat").read_text(encoding="utf-8")
        self.assertIn("CHECK_RUNTIME.bat", doctor)
        self.assertIn("CHECK_RUNTIME.bat", gpu)
        self.assertIn("analyze.py --doctor --offline", doctor)
        self.assertIn("scripts\\test_gpu.py --check-only", gpu)
        self.assertTrue((ROOT / "analyze.py").is_file())
        self.assertTrue((ROOT / "scripts" / "test_gpu.py").is_file())

    def test_base_installer_propagates_failure_code(self):
        content = (WIN / "install" / "INSTALAR_WINDOWS.bat").read_text(encoding="utf-8")
        self.assertIn('set "RESULT=%ERRORLEVEL%"', content)
        self.assertIn("exit /b %RESULT%", content)


if __name__ == "__main__":
    unittest.main()
