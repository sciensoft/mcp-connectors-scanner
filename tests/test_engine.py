"""Unit tests for the pure scanner logic: grading, extraction, coverage.

No network, no database, no scanners: run with `python3 -m unittest discover -s tests`
from the scanner/ directory (the CI image already has Python).

The heuristic-to-D rule is deliberately NOT asserted here. Whether a GuardDog hit
should ever cost a full letter grade is an open calibration question (see
.docs/todos/build-connector-security-scan-engine.md), to be settled with data
from a full sweep. These tests pin only the behaviour that is intended.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.dont_write_bytecode = True

from engine.coverage import CHECKS, matrix  # noqa: E402
from engine.extract import extract  # noqa: E402
from engine.grade import Findings, grade  # noqa: E402


def entry(kind, args, eid="x", **extra):
    e = {"id": eid, "preferred_runtime": kind, "runtimes": {kind: {"args": args}}}
    e.update(extra)
    return e


class GradeTests(unittest.TestCase):
    def test_known_malicious_is_always_f(self):
        f = Findings(scanned=True, mal_advisories=["MAL-2026-1"])
        self.assertEqual(grade(f).letter, "F")

    def test_malicious_wins_even_when_nothing_else_ran(self):
        f = Findings(scanned=False, mal_advisories=["MAL-2026-1"])
        self.assertEqual(grade(f).letter, "F")

    def test_tool_poisoning_is_f(self):
        f = Findings(scanned=True, poisoning_hits=["hidden-instruction"])
        self.assertEqual(grade(f).letter, "F")

    def test_unscanned_is_question_mark_never_a(self):
        g = grade(Findings(scanned=False, errors=["trivy: db download failed"]))
        self.assertEqual(g.letter, "?")
        self.assertIn("db download failed", g.reason)

    def test_unscanned_without_errors_still_not_a(self):
        self.assertEqual(grade(Findings(scanned=False)).letter, "?")

    def test_clean_scan_is_a(self):
        self.assertEqual(grade(Findings(scanned=True, packages=[{"id": "a@1"}])).letter, "A")

    def test_empty_tree_is_never_a_or_b(self):
        # Scanners ran, found nothing, because there was nothing to look at.
        g = grade(Findings(scanned=True))
        self.assertEqual(g.letter, "?")
        self.assertIn("nothing was resolved", g.reason)
        self.assertEqual(grade(Findings(scanned=True, cve_counts={"LOW": 1})).letter, "?")

    def test_a_requires_packages_and_names_the_count(self):
        g = grade(Findings(scanned=True, packages=[{"id": "a@1"}, {"id": "b@2"}]))
        self.assertEqual(g.letter, "A")
        self.assertIn("2 package(s) checked", g.reason)

    def test_no_evidence_means_no_grade_for_any_letter(self):
        # Findings with no resolved package behind them are not graded: no basis.
        for f in (Findings(scanned=True, cve_counts={"HIGH": 1}),
                  Findings(scanned=True, cve_counts={"CRITICAL": 2}, critical_with_fix=True),
                  Findings(scanned=True, heuristic_hits=["capability-network-outbound"]),
                  Findings(scanned=True)):
            g = grade(f)
            self.assertEqual(g.letter, "?")
            self.assertIn("not yet assessed", g.reason)

    def test_a_named_malicious_advisory_is_its_own_evidence(self):
        # F does not need a package list: the advisory names the package.
        self.assertEqual(grade(Findings(scanned=True, mal_advisories=["MAL-2026-1"])).letter, "F")

    def test_capability_findings_never_lower_a_grade(self):
        f = Findings(scanned=True, packages=[{"id": "a@1"}],
                     heuristic_hits=["capability-network-outbound", "capability-process-spawn",
                                     "threat-runtime-environment-read"])
        g = grade(f)
        self.assertEqual(g.letter, "A")
        self.assertIn("3 capability note(s) listed", g.reason)

    def test_strong_signal_gives_d_and_names_the_rule(self):
        for rule in ("threat-runtime-obfuscation-base64exec", "threat-runtime-obfuscation",
                     "threat-process-download-exec"):
            f = Findings(scanned=True, packages=[{"id": "a@1"}], heuristic_hits=["capability-network-outbound", rule])
            g = grade(f)
            self.assertEqual(g.letter, "D", rule)
            self.assertIn(rule, g.reason)

    def test_weak_hits_do_not_hide_a_real_cve_grade(self):
        f = Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"HIGH": 1},
                     heuristic_hits=["capability-network-outbound"])
        self.assertEqual(grade(f).letter, "C")

    def test_heuristic_hit_with_packages_is_d(self):
        f = Findings(scanned=True, packages=[{"id": "a@1"}], heuristic_hits=["threat-process-download-exec"])
        self.assertEqual(grade(f).letter, "D")

    def test_scanner_crash_never_yields_a(self):
        # The real case: Trivy ran, OSV-Scanner panicked, nothing was found.
        f = Findings(scanned=True, packages=[{"id": "a@1"}], errors=["osv-scanner: panic: nil pointer dereference"])
        g = grade(f)
        self.assertEqual(g.letter, "?")
        self.assertIn("partially scanned", g.reason)

    def test_scanner_error_never_yields_b(self):
        f = Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"LOW": 2}, errors=["guarddog: timeout"])
        self.assertEqual(grade(f).letter, "?")

    def test_bad_grades_stand_even_when_a_scanner_errored(self):
        # More data can only make a bad result worse, never better.
        high = Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"HIGH": 1}, errors=["osv-scanner: crash"])
        self.assertEqual(grade(high).letter, "C")
        crit = Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"CRITICAL": 1}, critical_with_fix=True,
                        errors=["osv-scanner: crash"])
        self.assertEqual(grade(crit).letter, "D")
        mal = Findings(scanned=True, mal_advisories=["MAL-2026-1"], errors=["trivy: crash"])
        self.assertEqual(grade(mal).letter, "F")

    def test_low_only_is_b(self):
        self.assertEqual(grade(Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"LOW": 4})).letter, "B")

    def test_one_or_two_medium_is_b(self):
        self.assertEqual(grade(Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"MEDIUM": 2})).letter, "B")

    def test_three_medium_is_c(self):
        self.assertEqual(grade(Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"MEDIUM": 3})).letter, "C")

    def test_any_high_is_c(self):
        self.assertEqual(grade(Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"HIGH": 1})).letter, "C")

    def test_critical_with_fix_is_d(self):
        f = Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"CRITICAL": 1}, critical_with_fix=True)
        self.assertEqual(grade(f).letter, "D")

    def test_critical_without_fix_is_c(self):
        f = Findings(scanned=True, packages=[{"id": "a@1"}], cve_counts={"CRITICAL": 1}, critical_with_fix=False)
        self.assertEqual(grade(f).letter, "C")

    def test_reason_is_always_present(self):
        for f in (Findings(scanned=True), Findings(scanned=False),
                  Findings(scanned=True, cve_counts={"HIGH": 1})):
            self.assertTrue(grade(f).reason)


class ExtractTests(unittest.TestCase):
    def test_npx_scoped_pinned(self):
        t = extract(entry("npx", ["-y", "@scope/pkg@1.2.3"]))
        self.assertEqual((t.ecosystem, t.package, t.version), ("npm", "@scope/pkg", "1.2.3"))

    def test_npx_unpinned_has_empty_version(self):
        t = extract(entry("npx", ["-y", "left-pad"]))
        self.assertEqual((t.ecosystem, t.package, t.version), ("npm", "left-pad", ""))

    def test_npx_github_source(self):
        t = extract(entry("npx", ["github:own/repo#abc123"]))
        self.assertEqual((t.ecosystem, t.repo, t.ref), ("git", "own/repo", "abc123"))

    def test_npx_mcp_remote_is_manual(self):
        self.assertEqual(extract(entry("npx", ["-y", "mcp-remote", "https://x"])).ecosystem, "manual")

    def test_uvx_pinned(self):
        t = extract(entry("uvx", ["mcp-server-x==0.4.1"]))
        self.assertEqual((t.ecosystem, t.package, t.version), ("pypi", "mcp-server-x", "0.4.1"))

    def test_uvx_skips_option_values(self):
        t = extract(entry("uvx", ["--python", "3.12", "pkg==2.0"]))
        self.assertEqual((t.package, t.version), ("pkg", "2.0"))

    def test_uvx_from_git(self):
        t = extract(entry("uvx", ["--from", "git+https://github.com/o/r@v1", "cmd"]))
        self.assertEqual((t.ecosystem, t.repo, t.ref), ("git", "o/r", "v1"))

    def test_go_install(self):
        t = extract(entry("go", ["install", "github.com/o/r/cmd/x@v1.0.0"]))
        self.assertEqual((t.ecosystem, t.version), ("go", "v1.0.0"))

    def test_go_with_odd_args_is_manual_not_crash(self):
        self.assertEqual(extract(entry("go", ["weird"])).ecosystem, "manual")

    def test_container_image(self):
        t = extract(entry("container", ["run", "-i", "--rm", "ghcr.io/o/img:1.0"]))
        self.assertEqual((t.ecosystem, t.image), ("container", "ghcr.io/o/img:1.0"))

    def test_jbang_github_spec(self):
        t = extract(entry("jbang", ["run", "github.com/TomCools/twitch-mcp"]))
        self.assertEqual((t.ecosystem, t.repo), ("git", "TomCools/twitch-mcp"))

    def test_jbang_maven_coordinate(self):
        t = extract(entry("jbang", ["run", "io.github.o:art:1.2.0"]))
        self.assertEqual((t.ecosystem, t.package, t.version), ("maven", "io.github.o:art", "1.2.0"))

    def test_jbang_bare_url_is_manual(self):
        self.assertEqual(extract(entry("jbang", ["run", "https://example.com/x.java"])).ecosystem, "manual")

    def test_capitalised_legacy_keys(self):
        e = {"id": "old", "preferred_runtime": "npx", "runtimes": {"npx": {"Args": ["-y", "pkg@1.0.0"]}}}
        self.assertEqual(extract(e).package, "pkg")

    def test_missing_runtime_never_raises(self):
        t = extract({"id": "broken", "preferred_runtime": "npx", "runtimes": {}})
        self.assertEqual(t.ecosystem, "unknown")

    def test_unknown_kind_never_raises(self):
        self.assertEqual(extract(entry("cobol", ["x"])).ecosystem, "unknown")


class CoverageTests(unittest.TestCase):
    def states(self, eco, tools):
        return {c["id"]: c["state"] for c in matrix(eco, tools)}

    def test_failed_tool_reads_as_skipped_not_checked(self):
        # The core honesty promise: a scanner that did not run is never a pass.
        s = self.states("go", ["trivy"])
        self.assertEqual(s["known-malicious"], "skipped")

    def test_tool_that_ran_reads_as_checked(self):
        s = self.states("npm", ["trivy", "osv-scanner", "guarddog"])
        self.assertEqual(s["known-cve"], "checked")
        self.assertEqual(s["malicious-code-heuristics"], "checked")

    def test_not_covered_stays_not_covered_even_if_something_ran(self):
        s = self.states("npm", ["trivy", "osv-scanner", "guarddog", "cisco-mcp-scanner"])
        self.assertEqual(s["runtime-response-attacks"], "not_covered")

    def test_heuristics_not_applicable_to_go(self):
        self.assertEqual(self.states("go", ["trivy"])["malicious-code-heuristics"], "not_applicable")

    def test_every_check_is_reported_for_every_ecosystem(self):
        ids = {c["id"] for c in CHECKS}
        for eco in ("npm", "pypi", "go", "git", "maven", "container", "manual"):
            self.assertEqual({c["id"] for c in matrix(eco, [])}, ids)

    def test_nothing_ran_means_nothing_checked(self):
        for c in matrix("npm", []):
            self.assertNotEqual(c["state"], "checked")


class ApiAuthTests(unittest.TestCase):
    """The scanner API must fail closed. The server-side feed once accepted a bare
    token with no Bearer scheme (TrimPrefix instead of CutPrefix), so pin the same
    property here: a regression would be silent."""

    def setUp(self):
        import types
        fake = types.ModuleType("engine.store")
        for name in ("latest_summaries", "review_queue", "history", "last_run", "latest_detail"):
            setattr(fake, name, lambda *a, **k: [])
        sys.modules["engine.store"] = fake
        import engine
        engine.store = fake
        from engine import api
        self.api = api

    def tearDown(self):
        os.environ.pop("SCANNER_API_TOKEN", None)

    def check(self, header, token="s3cret"):
        if token is None:
            os.environ.pop("SCANNER_API_TOKEN", None)
        else:
            os.environ["SCANNER_API_TOKEN"] = token

        class Fake:
            headers = {"Authorization": header} if header is not None else {}
        return self.api.Handler._authorised(Fake())

    def test_good_bearer_is_accepted(self):
        self.assertTrue(self.check("Bearer s3cret"))

    def test_bare_token_without_scheme_is_rejected(self):
        self.assertFalse(self.check("s3cret"))

    def test_wrong_token_is_rejected(self):
        self.assertFalse(self.check("Bearer nope"))

    def test_missing_header_is_rejected(self):
        self.assertFalse(self.check(None))

    def test_empty_bearer_is_rejected(self):
        self.assertFalse(self.check("Bearer "))

    def test_unset_token_rejects_everything_even_an_empty_bearer(self):
        for h in ("Bearer ", "Bearer anything", "anything", None):
            self.assertFalse(self.check(h, token=None), h)

    def test_scheme_is_case_sensitive_and_exact(self):
        self.assertFalse(self.check("bearer s3cret"))
        self.assertFalse(self.check("Basic s3cret"))


if __name__ == "__main__":
    unittest.main()
