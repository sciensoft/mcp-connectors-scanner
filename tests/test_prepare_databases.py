"""The vulnerability databases are downloaded once, before any worker starts.

Background: a sweep with 32 workers failed 42 scans in its first minute because every
worker tried to download the same database at once. The Java index database is also
about 1 GB compressed, more than the scanner's in-memory /tmp, so it could never be
refreshed there. These tests pin the fix without needing Trivy or the network.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.dont_write_bytecode = True

from engine import scan  # noqa: E402


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)  # (code, stderr) consumed in order; last repeats
        self.calls = []

    def __call__(self, cmd, cwd=None, timeout=300):
        self.calls.append(list(cmd))
        code, err = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return code, "", err


class PrepareDatabases(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp()
        self._old = os.environ.get("SCAN_DB_SCRATCH")
        os.environ["SCAN_DB_SCRATCH"] = self.scratch
        self._attempts, self._pause = scan.DB_ATTEMPTS, scan.DB_PAUSE
        scan.DB_ATTEMPTS = 3

    def tearDown(self):
        scan.DB_ATTEMPTS, scan.DB_PAUSE = self._attempts, self._pause
        if self._old is None:
            os.environ.pop("SCAN_DB_SCRATCH", None)
        else:
            os.environ["SCAN_DB_SCRATCH"] = self._old

    def test_fetches_both_databases_once_each(self):
        r = FakeRunner([(0, "")])
        ok, msg = scan.prepare_databases(runner=r, sleep=lambda s: None)
        self.assertTrue(ok, msg)
        flat = [" ".join(c) for c in r.calls]
        self.assertEqual(len(flat), 2)
        self.assertTrue(any("--download-db-only" in c for c in flat))
        self.assertTrue(any("--download-java-db-only" in c for c in flat))

    def test_retries_a_transient_failure_then_succeeds(self):
        r = FakeRunner([(1, "connection reset"), (1, "connection reset"), (0, "")])
        waits = []
        ok, msg = scan.prepare_databases(runner=r, sleep=waits.append)
        self.assertTrue(ok, msg)
        self.assertEqual(len(waits), 2)  # paused between attempts, not after the last
        self.assertIn("attempt 3", msg)

    def test_gives_up_with_a_reason_and_does_not_report_success(self):
        r = FakeRunner([(1, "no space left on device")])
        ok, msg = scan.prepare_databases(runner=r, sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertIn("no space left on device", msg)
        self.assertIn("3 attempts", msg)

    def test_failure_of_the_java_database_alone_still_fails_the_step(self):
        r = FakeRunner([(0, ""), (1, "mirror down")])
        ok, msg = scan.prepare_databases(runner=r, sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertIn("Java", msg)

    def test_downloads_use_the_disk_scratch_folder_only_for_themselves(self):
        before = os.environ.get("TMPDIR")
        r = FakeRunner([(0, "")])
        scan.prepare_databases(runner=r, sleep=lambda s: None)
        for c in r.calls:
            self.assertEqual(c[0], "env")
            self.assertIn(f"TMPDIR={self.scratch}", c)
        self.assertEqual(os.environ.get("TMPDIR"), before)  # the process is untouched

    def test_scratch_is_emptied_before_and_after(self):
        with open(os.path.join(self.scratch, "left-over.tar.gz"), "w") as fh:
            fh.write("x")
        r = FakeRunner([(0, "")])
        scan.prepare_databases(runner=r, sleep=lambda s: None)
        self.assertEqual(os.listdir(self.scratch), [])


class ScansDoNotDownload(unittest.TestCase):
    def test_every_trivy_scan_skips_both_database_updates(self):
        from engine.grade import Findings
        seen = []
        real = scan.run
        scan.run = lambda cmd, cwd=None, timeout=300: (seen.append(list(cmd)) or (1, "", "stop"))
        try:
            scan._trivy("/x", Findings(), mode="fs")
            scan._trivy("/x", Findings(), mode="image")
        finally:
            scan.run = real
        self.assertEqual(len(seen), 2)
        for cmd in seen:
            self.assertIn("--skip-db-update", cmd)
            self.assertIn("--skip-java-db-update", cmd)


if __name__ == "__main__":
    unittest.main()
