"""The collector's scrubber stands between production data and a public repository.

These tests pin both directions: internal references must go, and public package
names and URLs that merely contain the same words must stay untouched.
"""
import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(__file__), "..", "deploy", "collect.py")
_spec = importlib.util.spec_from_file_location("collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)


class ScrubRemoves(unittest.TestCase):
    # Fake credentials are assembled from pieces so no token-shaped string sits in
    # this file for secret scanners to flag.
    CASES = {
        "dial tcp mcp-server:8080: refused": "<internal-host>",
        "GET http://mcp-db:5432/x": "<internal-host>",
        "GET https://mcp-server:8080/internal/scanner/catalog": "<internal-host>",
        "feed at http://mcp-scanner:9090/v1/grades": "<internal-host>",
        "scanner:pw@mcp-db:5432": "<internal-host>",
        "host sciensoft-ws-01 down": "<internal-host>",
        "ssh hrollers": "<internal-host>",
        "cloned to /work/aws-abc123/src/pkg": "<work-dir>",
        "see /home/someone/.cache/uv": "<path>",
        "connect 10.89.1.12:9090": "<private-ip>",
        "ip 192.168.1.5": "<private-ip>",
        "url postgres://scanner:secret@mcp-db:5432/scanner": "<redacted-url>",
        "Authorization: Bear" + "er abcdefghijklmnop123": "Bearer <redacted>",
        "token " + "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123456789": "<redacted-token>",
        "key " + "AKIA" + "ABCDEFGHIJKLMNOP": "<redacted-token>",
    }

    def test_each_case_is_scrubbed_and_passes_the_guard(self):
        for text, want in self.CASES.items():
            with self.subTest(text=text):
                out = collect.scrub(text)
                self.assertIn(want, out)
                self.assertIsNone(collect._GUARD.search(out))


class ScrubKeeps(unittest.TestCase):
    KEEP = [
        "awslabs-aws-diagram-mcp-server>=1.0.5 was yanked",
        "pip install foo-mcp-server",
        "https://pypi.org/project/airtable-mcp-server/",
        "https://github.com/foo/mcp-server",
        "git clone https://github.com/awslabs/mcp-server.git",
        "@modelcontextprotocol/server-filesystem",
        "https://github.com/awslabs/mcp/tree/main/src/foo",
        "uv resolve: error: No solution found when resolving dependencies",
        "8.8.8.8 and 1.1.1.1 are public",
    ]

    def test_public_names_are_left_alone(self):
        for text in self.KEEP:
            with self.subTest(text=text):
                self.assertEqual(collect.scrub(text), text)
                self.assertIsNone(collect._GUARD.search(text))


class GuardRefuses(unittest.TestCase):
    def test_guard_stops_what_scrub_missed(self):
        for text in ("see /work/x/y", "host mcp-db", "ip 10.89.1.12", "postgres://u:p@h/d"):
            with self.subTest(text=text):
                with self.assertRaises(SystemExit):
                    collect.guard("test", text)

    def test_scrub_handles_nested_data(self):
        data = {"errors": ["failed in /work/a-1/src", {"host": "mcp-db"}], "n": 3}
        out = collect.scrub(data)
        self.assertEqual(out["n"], 3)
        self.assertIsNone(collect._GUARD.search(str(out)))


class MetaCarriesScannerVersions(unittest.TestCase):
    """The published files say what the scan was made with, and the scrubber keeps it."""

    VERSIONS = {
        "tools": {"trivy": "0.58.1", "osv-scanner": "2.0.0", "guarddog": "3.2.0", "uv": "0.13.8"},
        "databases": {
            "trivy-db": {"Version": 2, "UpdatedAt": "2026-11-15T12:50:30Z",
                         "DownloadedAt": "2026-11-15T15:06:40Z"},
            "trivy-java-db": None,
        },
    }

    def _run_main(self):
        import json
        import tempfile
        row = {"entry_id": "demo", "version": "1.0", "ecosystem": "npm", "grade": "A",
               "reason": "clean", "cve_counts": {}, "scanned_at": "2026-11-15T15:00:00Z"}
        answers = {
            "/v1/grades": {"grades": [row]},
            "/v1/grades/demo": dict(row, id=7, run_id=9),
            "/v1/versions": self.VERSIONS,
        }
        real = collect.get
        collect.get = lambda path: answers[path]
        out = tempfile.mkdtemp()
        try:
            self.assertEqual(collect.main(out), 0)
        finally:
            collect.get = real
        loaded = {}
        for name in ("summary.json", "full.json"):
            with open(os.path.join(out, name), encoding="utf-8") as fh:
                loaded[name] = json.load(fh)
        return loaded

    def test_both_published_files_carry_the_versions_unchanged(self):
        for name, doc in self._run_main().items():
            with self.subTest(file=name):
                self.assertEqual(doc["meta"]["scanner"], self.VERSIONS)

    def test_a_missing_database_stays_visible_as_null(self):
        doc = self._run_main()["summary.json"]
        self.assertIsNone(doc["meta"]["scanner"]["databases"]["trivy-java-db"])


if __name__ == "__main__":
    unittest.main()
