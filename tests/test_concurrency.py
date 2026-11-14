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

        real = (main.fetch_catalog, main.scan_one, main.store)
        main.fetch_catalog, main.scan_one, main.store = (lambda: entries), fake_scan_one, FakeStore()
        os.environ["SCAN_CONCURRENCY"] = "10"
        try:
            main.sweep()
        finally:
            main.fetch_catalog, main.scan_one, main.store = real
            os.environ.pop("SCAN_CONCURRENCY", None)
        self.assertEqual(len(saved), 30)
        self.assertEqual(len(set(saved)), 30)
        self.assertEqual(FakeStore.counts, {"A": 28, "?": 2})
        self.assertEqual(active["peak"], 10)


if __name__ == "__main__":
    unittest.main()
