"""Concurrency tests: per-registry gates, rate-limit back-off, parallel sweep.

No network and no real scanners: the work is faked so only the scheduling is tested.
"""
import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from engine import gates, main, scan


def _hold(registry, peak, now, lock):
    with gates.gate(registry):
        with lock:
            now[registry] = now.get(registry, 0) + 1
            peak[registry] = max(peak.get(registry, 0), now[registry])
        time.sleep(0.05)
        with lock:
            now[registry] -= 1


class GateTests(unittest.TestCase):
    def setUp(self):
        gates._gates.clear()
        gates._backoff_until.clear()

    def tearDown(self):
        os.environ.pop("SCAN_GATE_GIT", None)
        gates._gates.clear()

    def _drive(self, jobs):
        peak, now, lock = {}, {}, threading.Lock()
        with ThreadPoolExecutor(32) as p:
            list(p.map(lambda r: _hold(r, peak, now, lock), jobs))
        return peak

    def test_five_per_registry_and_lanes_are_independent(self):
        peak = self._drive(["npm"] * 20 + ["git"] * 20)
        self.assertEqual(peak["npm"], 5)
        self.assertEqual(peak["git"], 5)

    def test_per_registry_override(self):
        os.environ["SCAN_GATE_GIT"] = "2"
        peak = self._drive(["git"] * 10 + ["npm"] * 10)
        self.assertEqual(peak["git"], 2)
        self.assertEqual(peak["npm"], 5)

    def test_rate_limit_backs_off_and_retries_once(self):
        calls = []

        def fake_run(cmd, cwd=None, timeout=300):
            calls.append(time.time())
            return (1, "", "429 Too Many Requests") if len(calls) == 1 else (0, "ok", "")

        real_run, real_back = scan.run, gates.back_off
        scan.run, gates.back_off = fake_run, lambda n, s=30.0: real_back(n, 0.2)
        try:
            code, _, _ = scan.run_gated("npm", ["npm", "x"])
        finally:
            scan.run, gates.back_off = real_run, real_back
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertGreaterEqual(calls[1] - calls[0], 0.19)

    def test_ordinary_failure_is_not_retried(self):
        calls = []
        real_run = scan.run
        scan.run = lambda cmd, cwd=None, timeout=300: (calls.append(1), (1, "", "E404 not found"))[1]
        try:
            code, _, _ = scan.run_gated("npm", ["npm", "x"])
        finally:
            scan.run = real_run
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)


class RetryTests(unittest.TestCase):
    def setUp(self):
        gates._gates.clear()
        self._pause = scan.RETRY_PAUSE
        scan.RETRY_PAUSE = 0.05
        self._run = scan.run

    def tearDown(self):
        scan.RETRY_PAUSE = self._pause
        scan.run = self._run
        gates._gates.clear()

    def _fake(self, results):
        calls = []

        def fake_run(cmd, cwd=None, timeout=300):
            calls.append(1)
            return results[min(len(calls), len(results)) - 1]

        scan.run = fake_run
        return calls

    def test_timeout_is_retried_once_and_can_succeed(self):
        calls = self._fake([(-1, "", "timeout after 300s: git clone"), (0, "ok", "")])
        code, _, _ = scan.run_gated("git", ["git", "clone"])
        self.assertEqual((code, len(calls)), (0, 2))

    def test_connection_failure_is_retried_once_then_gives_up(self):
        err = "fatal: Failed to connect to github.com port 443: Could not connect to server"
        calls = self._fake([(128, "", err), (128, "", err), (0, "never", "")])
        code, _, _ = scan.run_gated("git", ["git", "clone"])
        self.assertEqual((code, len(calls)), (128, 2))

    def test_missing_package_is_not_retried(self):
        calls = self._fake([(1, "", "npm ERR! code E404 not found")])
        code, _, _ = scan.run_gated("npm", ["npm", "install"])
        self.assertEqual((code, len(calls)), (1, 1))


class PackageEvidenceTests(unittest.TestCase):
    def test_osv_alone_fills_the_package_list_and_dedupes(self):
        import json
        from engine.grade import Findings
        osv = json.dumps({"results": [{"source": {"path": "/w/src/package-lock.json"}, "packages": [
            {"package": {"name": "lodash", "version": "4.17.20"}, "vulnerabilities": [], "groups": []},
            {"package": {"name": "lodash", "version": "4.17.20"}, "vulnerabilities": [], "groups": []},
            {"package": {"name": "left-pad", "version": "1.3.0"}, "vulnerabilities": [], "groups": []},
        ]}]})
        real_run, real_mark = scan.run, scan._mark_ran
        scan.run = lambda cmd, cwd=None, timeout=300: (0, osv, "")
        scan._mark_ran = lambda f, tool: f.tools.__setitem__(tool, "test")
        try:
            f = Findings()
            scan._osv("/w/src", f)
        finally:
            scan.run, scan._mark_ran = real_run, real_mark
        self.assertEqual(sorted(p["id"] for p in f.packages), ["left-pad@1.3.0", "lodash@4.17.20"])


class SweepTests(unittest.TestCase):
    def test_parallel_sweep_saves_everything_once_and_survives_errors(self):
        entries = [{"id": f"c{i}"} for i in range(30)]
        active, lock, saved = {"now": 0, "peak": 0}, threading.Lock(), []

        def fake_scan_one(entry):
            with lock:
                active["now"] += 1
                active["peak"] = max(active["peak"], active["now"])
            time.sleep(0.05)
            with lock:
                active["now"] -= 1
            if entry["id"] in ("c3", "c17"):
                raise RuntimeError("boom")
            return {"entry_id": entry["id"], "grade": "A", "reason": "x"}

        class FakeStore:
            counts = None
            def start_run(self, t): return 1
            def save_result(self, rid, r): saved.append(r["entry_id"])
            def finish_run(self, rid, total, counts): FakeStore.counts = counts

        real = (main.fetch_catalog, main.scan_one, main.store, main.prepare_databases)
        main.fetch_catalog, main.scan_one, main.store = (lambda: entries), fake_scan_one, FakeStore()
        main.prepare_databases = lambda: (True, "databases ready (fake)")
        os.environ["SCAN_CONCURRENCY"] = "10"
        try:
            main.sweep()
        finally:
            main.fetch_catalog, main.scan_one, main.store, main.prepare_databases = real
            os.environ.pop("SCAN_CONCURRENCY", None)
        self.assertEqual(len(saved), 30)
        self.assertEqual(len(set(saved)), 30)
        self.assertEqual(FakeStore.counts, {"A": 28, "?": 2})
        self.assertEqual(active["peak"], 10)


class WarmUpOrderTests(unittest.TestCase):
    """The database is fetched once, first. A missing database stops the sweep cleanly."""

    def _run_sweep(self, warm_up):
        events = []

        class FakeStore:
            def start_run(self, t): events.append("start_run"); return 1
            def save_result(self, rid, r): events.append("save")
            def finish_run(self, rid, total, counts): events.append("finish")

        def fake_scan_one(entry):
            events.append("scan")
            return {"entry_id": entry["id"], "grade": "A", "reason": "x"}

        def fake_warm_up():
            events.append("warm_up")
            return warm_up

        real = (main.fetch_catalog, main.scan_one, main.store, main.prepare_databases)
        main.fetch_catalog = lambda: [{"id": "a"}, {"id": "b"}]
        main.scan_one, main.store, main.prepare_databases = fake_scan_one, FakeStore(), fake_warm_up
        try:
            main.sweep()
            error = None
        except RuntimeError as e:
            error = str(e)
        finally:
            main.fetch_catalog, main.scan_one, main.store, main.prepare_databases = real
        return events, error

    def test_warm_up_runs_once_before_any_scan_or_record(self):
        events, error = self._run_sweep((True, "databases ready"))
        self.assertIsNone(error)
        self.assertEqual(events.count("warm_up"), 1)
        self.assertEqual(events[0], "warm_up")
        self.assertLess(events.index("warm_up"), events.index("start_run"))
        self.assertLess(events.index("warm_up"), events.index("scan"))

    def test_missing_database_stops_before_recording_anything(self):
        events, error = self._run_sweep((False, "vulnerability database unavailable after 4 attempts"))
        self.assertIn("unavailable", error)
        self.assertEqual(events, ["warm_up"])  # no run row, no scans, no false results


if __name__ == "__main__":
    unittest.main()
