"""Every published result says what it was scanned with.

Tool versions and database dates are read from the real tools and files, and a missing
piece is reported as missing (None) rather than guessed.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.dont_write_bytecode = True

from engine import versions  # noqa: E402


class Out:
    def __init__(self, stdout):
        self.stdout = stdout


OUTPUTS = {
    "trivy": "Version: 0.58.1\nVulnerability DB:\n  Version: 2\n",
    "osv-scanner": "osv-scanner version: 2.0.0\ncommit: 0e986b49c4e7\n",
    "guarddog": "3.2.0\n",
    "uv": "uv 0.13.8 (x86_64-unknown-linux-gnu)\n",
}


def fake_run(cmd, **kw):
    return Out(OUTPUTS[cmd[0]])


def write_meta(root, sub, data):
    d = os.path.join(root, sub)
    os.makedirs(d)
    with open(os.path.join(d, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


class Collect(unittest.TestCase):
    def test_reads_tool_versions_from_their_own_output(self):
        got = versions.collect(cache_root=tempfile.mkdtemp(), run=fake_run)["tools"]
        self.assertEqual(got, {"trivy": "0.58.1", "osv-scanner": "2.0.0",
                               "guarddog": "3.2.0", "uv": "0.13.8"})

    def test_reads_database_dates_and_drops_unrelated_keys(self):
        root = tempfile.mkdtemp()
        write_meta(root, "trivy/db", {"Version": 2, "UpdatedAt": "2026-11-15T12:50:30Z",
                                      "DownloadedAt": "2026-11-15T15:06:40Z",
                                      "NextUpdate": "2026-11-16T12:50:30Z"})
        write_meta(root, "trivy/java-db", {"Version": 1, "UpdatedAt": "2026-11-15T00:58:42Z",
                                           "DownloadedAt": "2026-11-15T15:25:04Z"})
        dbs = versions.collect(cache_root=root, run=fake_run)["databases"]
        self.assertEqual(dbs["trivy-db"], {"Version": 2, "UpdatedAt": "2026-11-15T12:50:30Z",
                                           "DownloadedAt": "2026-11-15T15:06:40Z"})
        self.assertEqual(dbs["trivy-java-db"]["UpdatedAt"], "2026-11-15T00:58:42Z")

    def test_a_missing_database_is_none_not_a_guess(self):
        dbs = versions.collect(cache_root=tempfile.mkdtemp(), run=fake_run)["databases"]
        self.assertEqual(dbs, {"trivy-db": None, "trivy-java-db": None})

    def test_a_broken_metadata_file_is_none(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "trivy/db"))
        with open(os.path.join(root, "trivy/db/metadata.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertIsNone(versions.collect(cache_root=root, run=fake_run)["databases"]["trivy-db"])

    def test_a_missing_or_failing_tool_is_none(self):
        def broken(cmd, **kw):
            if cmd[0] == "guarddog":
                raise FileNotFoundError("guarddog")
            if cmd[0] == "uv":
                raise subprocess.TimeoutExpired(cmd, 20)
            return fake_run(cmd)
        tools = versions.collect(cache_root=tempfile.mkdtemp(), run=broken)["tools"]
        self.assertIsNone(tools["guarddog"])
        self.assertIsNone(tools["uv"])
        self.assertEqual(tools["trivy"], "0.58.1")

    def test_output_holds_no_paths_or_hosts(self):
        root = tempfile.mkdtemp()
        write_meta(root, "trivy/db", {"Version": 2, "UpdatedAt": "x", "DownloadedAt": "y"})
        text = json.dumps(versions.collect(cache_root=root, run=fake_run))
        self.assertNotIn(root, text)
        self.assertNotIn("/home/", text)


if __name__ == "__main__":
    unittest.main()
