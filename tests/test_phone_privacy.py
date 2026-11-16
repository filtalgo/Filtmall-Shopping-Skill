from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class OfflinePhonePrivacyTests(unittest.TestCase):
    def test_copied_skill_works_without_site_packages_and_rejects_missing_or_corrupt_component(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copytree(root / 'scripts', target / 'scripts')
            shutil.copytree(root / 'third_party', target / 'third_party')
            script = target / 'scripts/probe.py'
            script.write_text("from phone_privacy import contains_phone\nassert contains_phone('+8613812345678')\nassert not contains_phone('测试路12号1202室')\nprint('offline passed')\n")
            result = subprocess.run(['python3', '-S', str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            wheel = next((target / 'third_party').glob('*.whl'))
            wheel.write_bytes(b'corrupt')
            for remove in (False, True):
                if remove:
                    wheel.unlink()
                result = subprocess.run(['python3', '-S', str(script)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('missing or corrupt', result.stderr)
                self.assertNotIn('+8613812345678', result.stdout)


if __name__ == '__main__':
    unittest.main()
