import concurrent.futures
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_check.py"


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "missing update checker implementation")
        spec = importlib.util.spec_from_file_location("update_check", SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / "skill"
        self.skill.mkdir()
        self.version("2.9.0")
        self.state = self.root / "state"
        self.checker = self.mod.UpdateChecker(self.skill, self.state)

    def version(self, value):
        (self.skill / "SKILL.md").write_text('---\nname: filtmall-shopping\nmetadata:\n  version: "' + value + '"\n---\n', encoding="utf-8")

    def release(self, version="v2.10.0", **kw):
        return dict(tag_name=version, draft=False, prerelease=False, **kw)

    def remote(self, data):
        return patch.object(self.mod.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(data), ""))

    def test_numeric_versions_and_original_tag(self):
        for remote, expected in [("2.8.0", "local_newer"), ("v2.9.0", "up_to_date"), ("v2.10.0", "available")]:
            with self.subTest(remote=remote), self.remote(self.release(remote)):
                result = self.checker.check()
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["release_tag"], remote)
                self.assertTrue(result["release_url"].endswith("/" + remote))

    def test_invalid_releases_and_local_version(self):
        invalid = [self.release("2.10.0-rc.1"), self.release("../2.10.0"), {}, [],
                   dict(tag_name="2.10.0", draft=True, prerelease=False),
                   dict(tag_name="2.10.0", draft=False, prerelease=True),
                   dict(tag_name="2.10.0", draft="false", prerelease=False)]
        for payload in invalid:
            with self.subTest(payload=payload), self.remote(payload):
                self.assertEqual(self.checker.check()["status"], "unknown")
        self.version("2.9.0-preview")
        with self.remote(self.release()):
            self.assertEqual(self.checker.check()["status"], "unknown")

    def test_local_metadata_name_and_boundaries(self):
        for content in (
            '---\nname: other-skill\nmetadata:\n  version: "2.9.0"\n---\n',
            '---\nname: filtmall-shopping\nother:\n  version: "2.9.0"\n---\n',
            '---\nname: filtmall-shopping\nmetadata:\n  version: "2.9.0"\nmetadata:\n  version: "2.8.0"\n---\n',
            '---\nname: filtmall-shopping\nmetadata:\n  version: "2.9.0"\n',
        ):
            with self.subTest(content=content):
                (self.skill / "SKILL.md").write_text(content, encoding="utf-8")
                with self.remote(self.release()) as run:
                    self.assertEqual(self.checker.check()["status"], "unknown")
                    self.assertFalse(run.called)

    def test_fresh_query_even_ignored_and_failure_after_success(self):
        self.assertTrue(self.checker.record("ignore", "2.10.0")["ok"])
        with self.remote(self.release()) as run:
            for _ in range(2):
                result = self.checker.check("private conversation text")
                self.assertEqual(result["status"], "available")
                self.assertFalse(result["notify"])
            self.assertEqual(run.call_count, 2)
            self.assertNotIn("private conversation text", str(run.call_args))
        with self.remote(self.release("2.11.0")):
            self.assertTrue(self.checker.check()["notify"])
        with patch.object(self.mod.subprocess, "run", side_effect=subprocess.TimeoutExpired([], 0.1)):
            self.assertEqual(self.checker.check()["status"], "unknown")

    def test_shown_later_persist_and_scope(self):
        for action in ("shown", "later"):
            self.assertTrue(self.checker.record(action, "v2.10.0", "secret conversation")["ok"])
            second = self.mod.UpdateChecker(self.skill, self.state)
            with self.remote(self.release()):
                self.assertFalse(second.check("secret conversation")["notify"])
                self.assertTrue(second.check("different")["notify"])
                self.assertTrue(self.mod.UpdateChecker(self.skill, self.state, "other").check("secret conversation")["notify"])
        for file in self.state.rglob("*.json"):
            self.assertNotIn("secret conversation", file.read_text())
        self.assertTrue(self.checker.record("reset", None)["ok"])
        with self.remote(self.release()):
            self.assertTrue(self.checker.check("secret conversation")["notify"])

    def test_invalid_record_and_unwritable_or_corrupt_state(self):
        self.assertFalse(self.checker.record("shown", "2.10.0")["ok"])
        self.assertFalse(self.checker.record("ignore", "bad")["ok"])
        self.state.write_text("blocked", encoding="utf-8")
        with self.remote(self.release()):
            self.assertTrue(self.checker.check()["notify"])
        self.assertFalse(self.checker.record("ignore", "2.10.0")["ok"])
        self.state.unlink()
        self.assertTrue(self.checker.record("ignore", "2.10.0")["ok"])
        for file in self.state.rglob("*.json"):
            file.write_text("{broken", encoding="utf-8")
        with self.remote(self.release()):
            self.assertTrue(self.checker.check()["notify"])
        self.assertFalse(self.checker.record("ignore", "2.10.0")["ok"])

    def test_concurrent_records_preserve_choices(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i: self.checker.record("shown", "2.10.0", str(i)), range(12)))
        self.assertTrue(all(r["ok"] for r in results), results)
        with self.remote(self.release()):
            for i in range(12):
                self.assertFalse(self.checker.check(str(i))["notify"])

    def test_installation_scope_permissions_and_bad_state_file(self):
        self.assertTrue(self.checker.record("ignore", "2.10.0")["ok"])
        other = self.root / "another-install"
        other.mkdir()
        (other / "SKILL.md").write_text((self.skill / "SKILL.md").read_text(), encoding="utf-8")
        with self.remote(self.release()):
            self.assertTrue(self.mod.UpdateChecker(other, self.state).check()["notify"])
        with patch.object(self.mod.os, "replace", side_effect=PermissionError("secret token must not escape")):
            result = self.checker.record("ignore", "2.11.0")
            self.assertFalse(result["ok"])
            self.assertNotIn("secret", json.dumps(result))
        self.checker.state_path.unlink()
        self.checker.state_path.mkdir()
        with self.remote(self.release()):
            self.assertTrue(self.checker.check()["notify"])
        self.assertFalse(self.checker.record("ignore", "2.10.0")["ok"])

    def test_worker_errors_do_not_escape_and_timeout_validation(self):
        for stdout, code in [('not json', 0), ('{"error":"secret"}', 0), ('', 1)]:
            with patch.object(self.mod.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, "secret credential")):
                result = self.checker.check()
                self.assertEqual(result["status"], "unknown")
                self.assertNotIn("secret", json.dumps(result))
        for timeout in (0, -1, float("nan"), float("inf"), 31):
            with self.assertRaises(ValueError):
                self.mod.UpdateChecker(self.skill, self.state, timeout=timeout)

    def test_symlink_state_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            self.state.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink creation not permitted")
        self.assertFalse(self.checker.record("ignore", "2.10.0")["ok"])
        self.assertEqual(list(outside.iterdir()), [])

    def test_worker_preserves_host_proxy(self):
        opener = unittest.mock.MagicMock()
        opener.open.return_value.__enter__.return_value.status = 200
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(self.release()).encode()
        proxies = {"https": "http://proxy.invalid:8080"}
        with patch.object(self.mod.urllib.request, "getproxies", return_value=proxies), patch.object(self.mod.urllib.request, "build_opener", return_value=opener) as build:
            self.mod._fetch_release(1)
        self.assertEqual(build.call_args.args[0].proxies, proxies)

    def test_terminated_lock_holder_does_not_block_records(self):
        code = "import importlib.util,sys,time; s=importlib.util.spec_from_file_location('checker',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); c=m.UpdateChecker(sys.argv[2],sys.argv[3]); ctx=c._locked_state(); ctx.__enter__(); print('locked',flush=True); time.sleep(30)"
        child = subprocess.Popen([sys.executable, "-c", code, str(SCRIPT), str(self.skill), str(self.state)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
        finally:
            child.terminate()
            child.wait(timeout=5)
            child.stdout.close()
        self.assertTrue(self.checker.record("ignore", "2.10.0")["ok"])

    def test_worker_fixed_url_limits_and_http_errors(self):
        class Reply(io.BytesIO):
            status = 200
        opener = unittest.mock.Mock()
        opener.open.return_value = Reply(json.dumps(self.release()).encode())
        with patch.object(self.mod.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(self.mod._fetch_release(1)["tag_name"], "v2.10.0")
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.github.com/repos/filtalgo/Filtmall-Shopping-Skill/releases/latest")
            self.assertNotIn("Authorization", request.headers)
            opener.open.return_value = Reply(b"x" * (self.mod.MAX_RESPONSE + 1))
            with self.assertRaises(ValueError):
                self.mod._fetch_release(1)
            for status in (403, 429, 404, 302):
                opener.open.side_effect = self.mod.urllib.error.HTTPError(request.full_url, status, "error", {}, None)
                with self.assertRaises(self.mod.urllib.error.HTTPError):
                    self.mod._fetch_release(1)
        self.assertIsNone(self.mod._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))

    def test_total_timeout_kills_worker(self):
        original = subprocess.Popen
        children = []
        def slow(*args, **kwargs):
            child = original([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
            children.append(child)
            return child
        checker = self.mod.UpdateChecker(self.skill, self.state, timeout=0.1)
        start = time.monotonic()
        with patch.object(self.mod.subprocess, "Popen", side_effect=slow):
            self.assertEqual(checker.check()["status"], "unknown")
        self.assertLess(time.monotonic() - start, 2)
        self.assertTrue(children)
        self.assertTrue(all(c.poll() is not None for c in children))

    def test_cli_record_single_json_and_worker_protocol(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--state-dir", str(self.state), "--action", "ignore", "--version", "v2.10.0"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertEqual(result.stderr, "")
        result = subprocess.run([sys.executable, str(SCRIPT), "--worker"], input='{"timeout": 0}\n', capture_output=True, text=True)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
