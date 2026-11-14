"""The scanner's own database (ADR 0001, decision 3).

Everything about scanning lives here and nowhere else: grades, findings, the
dependency tree, the coverage matrix and the history. The server stores none
of it and only reads it through the API in api.py.

Schema is created idempotently on startup, so a fresh database needs no manual
step. Evidence columns are JSONB on purpose: the dependency tree, findings and
coverage matrix are published to users as data, and their shape will evolve.

Grades: A clean, B low risk, C needs attention, D serious, F quarantine
candidate (flags for human review only), ? could not be scanned.
"""
import json
import os
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id          BIGSERIAL PRIMARY KEY,
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    total       INTEGER NOT NULL DEFAULT 0,
    grade_counts JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS scans (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT REFERENCES scan_runs(id) ON DELETE SET NULL,
    entry_id         TEXT        NOT NULL,
    version          TEXT        NOT NULL DEFAULT '',
    ecosystem        TEXT        NOT NULL DEFAULT '',
    grade            TEXT        NOT NULL CHECK (grade IN ('A','B','C','D','F','?')),
    reason           TEXT        NOT NULL DEFAULT '',
    cve_counts       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    vulnerabilities  JSONB       NOT NULL DEFAULT '[]'::jsonb,
    packages         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    dependency_edges JSONB       NOT NULL DEFAULT '[]'::jsonb,
    mal_advisories   JSONB       NOT NULL DEFAULT '[]'::jsonb,
    heuristic_hits   JSONB       NOT NULL DEFAULT '[]'::jsonb,
    tools            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    coverage         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    errors           JSONB       NOT NULL DEFAULT '[]'::jsonb,
    scanned_at       TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scans_entry_time ON scans (entry_id, scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_scans_grade ON scans (grade);
"""

# Latest scan per connector, the hot path for badges and the detail page.
_LATEST = """
SELECT DISTINCT ON (entry_id) *
FROM scans
ORDER BY entry_id, scanned_at DESC
"""


def connect():
    return psycopg.connect(os.environ["SCANNER_DATABASE_URL"], row_factory=dict_row)


def init_schema() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


def _j(v):
    return json.dumps(v if v is not None else None)


def start_run(started_at: datetime) -> int:
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO scan_runs (started_at) VALUES (%s) RETURNING id", (started_at,)
        ).fetchone()
        return row["id"]


def save_result(run_id: int, r: dict) -> None:
    """Persist one connector's result immediately, so a crash mid-sweep loses
    only the connector being scanned, never the ones already finished."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO scans (run_id, entry_id, version, ecosystem, grade, reason,
                   cve_counts, vulnerabilities, packages, dependency_edges, mal_advisories,
                   heuristic_hits, tools, coverage, errors, scanned_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,
                       %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s)""",
            (
                run_id, r["entry_id"], r.get("version", ""), r.get("ecosystem", ""),
                r["grade"], r.get("reason", ""),
                _j(r.get("cve_counts", {})), _j(r.get("vulnerabilities", [])),
                _j(r.get("packages", [])), _j(r.get("dependency_edges", [])),
                _j(r.get("mal_advisories", [])), _j(r.get("heuristic_hits", [])),
                _j(r.get("tools", {})), _j(r.get("coverage", [])), _j(r.get("errors", [])),
                r.get("scanned_at") or datetime.now(timezone.utc),
            ),
        )


def finish_run(run_id: int, total: int, grade_counts: dict) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE scan_runs SET finished_at = NOW(), total = %s, grade_counts = %s::jsonb WHERE id = %s",
            (total, _j(grade_counts), run_id),
        )


# ---- read side, used by the API ----

SUMMARY_COLS = "entry_id, version, ecosystem, grade, reason, cve_counts, scanned_at"


def latest_summaries() -> list:
    with connect() as conn:
        return conn.execute(
            f"SELECT {SUMMARY_COLS} FROM ({_LATEST}) t ORDER BY entry_id"
        ).fetchall()


def latest_detail(entry_id: str):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM scans WHERE entry_id = %s ORDER BY scanned_at DESC LIMIT 1",
            (entry_id,),
        ).fetchone()


def history(entry_id: str, limit: int = 20) -> list:
    with connect() as conn:
        return conn.execute(
            f"SELECT {SUMMARY_COLS} FROM scans WHERE entry_id = %s "
            "ORDER BY scanned_at DESC LIMIT %s",
            (entry_id, limit),
        ).fetchall()


def review_queue() -> list:
    """Connectors whose latest grade needs a human look (D and F)."""
    with connect() as conn:
        return conn.execute(
            f"SELECT {SUMMARY_COLS} FROM ({_LATEST}) t "
            "WHERE grade IN ('D','F') ORDER BY grade DESC, entry_id"
        ).fetchall()


def last_run():
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
