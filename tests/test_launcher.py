"""Exercise dependency probes under Windows PowerShell 5.1 without launching/querying."""
import subprocess
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_shortcut_has_process_policy_and_visible_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "scripts" / "Create-Shortcut.ps1"),
                "-Directory", directory,
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            link = str(Path(directory) / "CC Balance Widget.lnk").replace("'", "''")
            inspected = subprocess.run([
                "powershell.exe", "-NoProfile", "-Command",
                f"(New-Object -ComObject WScript.Shell).CreateShortcut('{link}').Arguments | ConvertTo-Json",
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            arguments = json.loads(inspected.stdout)
            self.assertIn("-ExecutionPolicy Bypass", arguments)
            self.assertIn("-ShowErrors", arguments)

    def test_windows_powershell_dependency_probe(self):
        result = subprocess.run([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "Start.ps1"), "-DependenciesOnly",
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dependencies OK", result.stdout)
