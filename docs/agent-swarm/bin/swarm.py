#!/usr/bin/env python3
"""Agent swarm: spawn and supervise headless Claude CLI workers from a JSON registry.

Commands
  swarm.py launch  <registry.json> [--worker ID ...]   start the next queued task of each idle worker
  swarm.py watch   <registry.json> [--interval 5]      keep the registry current until all workers are terminal
  swarm.py status  <registry.json>                     print a compact table
  swarm.py stop    <registry.json> [--worker ID ...]   SIGTERM the worker process groups
  swarm.py verify  <registry.json>                     mark tasks done/partial/unknown from expected_outputs
  swarm.py qa-add  <registry.json> --worker ID --task ID --claim TEXT --verdict V [--entry E]
                   [--worker-value TEXT] [--observed TEXT] [--evidence TEXT] [--qa-status S] [--by NAME]
                                                       record one independent QA check on a task, recompute its tally
  swarm.py qa-report <registry.json> [--pending]       print per-task QA score; --pending lists tasks still needing QA
  swarm.py validate  <registry.json> [--schema PATH]   check the registry against the JSON schema (needs the optional jsonschema package)

Design notes
  * One registry JSON is the single source of truth. Only this script writes it (atomic replace).
  * Every worker runs `claude -p ... --output-format stream-json --verbose`, so each step is one JSON line.
    The raw stream goes to the worker's log file untouched; the registry keeps a capped rolling activity feed.
  * The model is ALWAYS passed explicitly with --model. The CLI default is never relied upon.
  * Workers are detached (own session), so they survive the shell that launched them.
  * Standard library only. The one exception is the optional `validate` command, which imports jsonschema
    lazily and prints an install hint if it is missing; every other command works without it.
"""
import argparse, json, os, signal, subprocess, sys, tempfile, time
from datetime import datetime, timezone

STALL_AFTER_SECONDS = 300
ACTIVITIES_MAX = 12
TERMINAL = {"done", "failed", "stopped", "idle"}


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load(path):
    with open(path) as f:
        return json.load(f)


def save(path, reg):
    reg["updated_at"] = now()
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".reg-", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(reg, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def runtime_for(reg, w):
    r = dict(reg.get("defaults", {}))
    r.update(w.get("runtime", {}))
    r.setdefault("model", "sonnet")
    r.setdefault("effort", "medium")
    r.setdefault("max_turns", 200)
    r.setdefault("permission_mode", "bypassPermissions")
    return r


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # zombie check
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def next_task(w):
    done_ids = {t["id"] for t in w["tasks"] if t["status"] == "done"}
    for t in w["tasks"]:
        if t["status"] == "queued" and all(d in done_ids for d in t.get("depends_on", [])):
            return t
    return None


def build_cmd(reg, w, task):
    r = runtime_for(reg, w)
    prompt = task["prompt"]
    if reg.get("brief_path"):
        prompt = f"First read {reg['brief_path']} in full and obey it. Never guess; mark anything unverified as UNVERIFIED.\n\n" + prompt
    cmd = ["claude", "-p", prompt,
           "--model", r["model"], "--effort", r["effort"],
           "--output-format", "stream-json", "--verbose",
           "--permission-mode", r["permission_mode"],
           "--max-turns", str(r["max_turns"]),
           "--name", f"{reg['swarm_id']}-{w['id']}"]
    if r.get("max_budget_usd"):
        cmd += ["--max-budget-usd", str(r["max_budget_usd"])]
    for d in r.get("add_dirs", []):
        cmd += ["--add-dir", d]
    if r.get("deny_tools"):
        cmd += ["--disallowedTools", *r["deny_tools"]]
    if w.get("session_id") and task.get("resume"):
        cmd += ["--resume", w["session_id"]]
    return cmd


def launch(path, only):
    reg = load(path)
    for w in reg["workers"]:
        if only and w["id"] not in only:
            continue
        if pid_alive(w.get("pid")):
            print(f"{w['id']}: already running (pid {w['pid']})")
            continue
        task = next_task(w)
        if not task:
            print(f"{w['id']}: no runnable queued task")
            continue
        os.makedirs(w["sandbox"], exist_ok=True)
        w.setdefault("stream_log", os.path.join(os.path.dirname(os.path.abspath(path)), "logs", f"{w['id']}.jsonl"))
        os.makedirs(os.path.dirname(w["stream_log"]), exist_ok=True)
        cmd = build_cmd(reg, w, task)
        log = open(w["stream_log"], "a")
        log.write(json.dumps({"type": "swarm_launch", "at": now(), "task": task["id"], "model_requested": runtime_for(reg, w)["model"]}) + "\n")
        log.flush()
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        p = subprocess.Popen(cmd, cwd=w["sandbox"], stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True, env=env)
        task.update(status="running", started_at=now(), ended_at=None, attempts=task.get("attempts", 0) + 1)
        w.update(status="starting", pid=p.pid, started_at=now(), ended_at=None, exit_code=None,
                 last_event_at=now(), state_detail=f"launched task {task['id']}", _offset=0)
        print(f"{w['id']}: launched task {task['id']} pid {p.pid} model {runtime_for(reg, w)['model']}")
        time.sleep(1)
    save(path, reg)


def push_activity(w, kind, text):
    w.setdefault("activities", []).append({"at": now(), "kind": kind, "text": text[:300]})
    w["activities"] = w["activities"][-ACTIVITIES_MAX:]


def describe_tool(block):
    name = block.get("name", "tool")
    inp = block.get("input", {}) or {}
    hint = inp.get("command") or inp.get("file_path") or inp.get("url") or inp.get("query") or inp.get("pattern") or ""
    return f"{name}: {str(hint)[:200]}"


def state_from_tool(name):
    if name in ("Write", "Edit", "NotebookEdit"):
        return "writing"
    return "researching"


def ingest(w):
    """Read new lines from the worker's stream log and update its state."""
    lp = w.get("stream_log")
    if w.get("stream_format") == "plain-text":
        return
    if not lp or not os.path.exists(lp):
        return
    off = w.get("_offset", 0)
    with open(lp, "rb") as f:
        f.seek(off)
        chunk = f.read()
    if not chunk:
        return
    # only consume complete lines
    end = chunk.rfind(b"\n")
    if end < 0:
        return
    w["_offset"] = off + end + 1
    for raw in chunk[: end + 1].splitlines():
        try:
            ev = json.loads(raw)
        except ValueError:
            if raw.strip():
                push_activity(w, "system", raw.decode("utf8", "replace"))
            continue
        w["last_event_at"] = now()
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            w["session_id"] = ev.get("session_id")
            w["model_seen"] = ev.get("model")
            push_activity(w, "system", f"init model={ev.get('model')}")
        elif t == "assistant":
            msg = ev.get("message", {})
            w["model_seen"] = msg.get("model") or w.get("model_seen")
            for b in msg.get("content", []):
                bt = b.get("type")
                if bt == "thinking":
                    w["status"] = "thinking"
                    w["state_detail"] = "reasoning"
                    push_activity(w, "thinking", (b.get("thinking") or "")[:300])
                elif bt == "text":
                    push_activity(w, "text", b.get("text", ""))
                elif bt == "tool_use":
                    w["status"] = state_from_tool(b.get("name", ""))
                    w["state_detail"] = describe_tool(b)
                    push_activity(w, "tool_call", describe_tool(b))
        elif t == "user":
            for b in ev.get("message", {}).get("content", []) if isinstance(ev.get("message", {}).get("content"), list) else []:
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    s = c if isinstance(c, str) else json.dumps(c)[:300]
                    push_activity(w, "tool_result", s[:300])
        elif t == "rate_limit_event":
            info = ev.get("rate_limit_info", {})
            if info.get("status") not in ("allowed", None):
                w["status"] = "rate_limited"
                w["state_detail"] = f"rate limit: {info.get('status')} resets {info.get('resetsAt')}"
            push_activity(w, "rate_limit", json.dumps(info)[:300])
        elif t == "result":
            w["cost_usd"] = ev.get("total_cost_usd")
            w["turns"] = ev.get("num_turns")
            w["_result_error"] = bool(ev.get("is_error"))
            w["_result_text"] = str(ev.get("result", ""))[:300]
            push_activity(w, "system", f"result error={ev.get('is_error')} {w['_result_text']}")


def finish_if_dead(reg, w):
    if w["status"] in TERMINAL:
        return
    if pid_alive(w.get("pid")):
        la = w.get("last_event_at")
        if la:
            age = (datetime.now(timezone.utc).astimezone() - datetime.fromisoformat(la)).total_seconds()
            if age > STALL_AFTER_SECONDS and w["status"] not in ("rate_limited",):
                w["status"] = "stalled"
                w["state_detail"] = f"no event for {int(age)}s"
        return
    # process is gone: decide the outcome from outputs, never from hope
    w["ended_at"] = now()
    task = next((t for t in w["tasks"] if t["status"] == "running"), None)
    if task:
        outs = [os.path.join(w["sandbox"], p) for p in task.get("expected_outputs", [])]
        have = [p for p in outs if os.path.exists(p) and os.path.getsize(p) > 0]
        task["ended_at"] = now()
        if outs and len(have) == len(outs) and not w.get("_result_error"):
            task["status"], w["status"] = "done", "done"
            task["result_note"] = "all expected outputs exist and are non-empty (content not yet reviewed)"
        elif have or w.get("activities"):
            rl = any(r["kind"] == "rate_limit" for r in w.get("activities", [])) or "limit" in w.get("_result_text", "").lower()
            task["status"] = "partial" if have else "failed"
            w["status"] = "rate_limited" if rl else ("failed" if not have else "stopped")
            task["result_note"] = f"{len(have)}/{len(outs)} expected outputs present" + (", hit a usage limit" if rl else "")
        else:
            task["status"], w["status"] = "unknown", "failed"
    else:
        w["status"] = "idle"
    w["state_detail"] = w["status"]
    w["pid"] = None


def refresh(path):
    reg = load(path)
    for w in reg["workers"]:
        if w.get("stream_log"):
            ingest(w)
        finish_if_dead(reg, w)
    save(path, reg)
    return reg


def table(reg):
    rows = []
    for w in reg["workers"]:
        counts = {}
        for t in w["tasks"]:
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        rows.append((w["id"], w["status"], w.get("model_seen") or "-", ",".join(f"{k}:{v}" for k, v in counts.items()), (w.get("state_detail") or "")[:70]))
    wid = max(len(r[0]) for r in rows)
    print(f"{'worker'.ljust(wid)}  {'status'.ljust(12)} {'model'.ljust(18)} tasks / detail")
    for r in rows:
        print(f"{r[0].ljust(wid)}  {r[1].ljust(12)} {r[2].ljust(18)} {r[3]} | {r[4]}")


def watch(path, interval):
    while True:
        reg = refresh(path)
        os.system("clear" if sys.stdout.isatty() else "true")
        table(reg)
        if all(w["status"] in TERMINAL for w in reg["workers"]):
            print("all workers terminal")
            return
        time.sleep(interval)


def stop(path, only):
    reg = load(path)
    for w in reg["workers"]:
        if only and w["id"] not in only:
            continue
        if pid_alive(w.get("pid")):
            try:
                os.killpg(os.getpgid(w["pid"]), signal.SIGTERM)
                print(f"{w['id']}: stopped pid {w['pid']}")
            except ProcessLookupError:
                pass
            w["status"] = "stopped"
            w["state_detail"] = "stopped by operator"
    save(path, reg)


def verify(path):
    reg = load(path)
    for w in reg["workers"]:
        for t in w["tasks"]:
            if t["status"] in ("running", "unknown", "partial", "failed") and not pid_alive(w.get("pid")):
                outs = [os.path.join(w["sandbox"], p) for p in t.get("expected_outputs", [])]
                have = [p for p in outs if os.path.exists(p) and os.path.getsize(p) > 0]
                if outs and len(have) == len(outs):
                    t["status"] = "done"
                    t["result_note"] = "outputs exist (found by verify); content review still required"
                elif have:
                    t["status"] = "partial"
                    t["result_note"] = f"{len(have)}/{len(outs)} outputs present"
    save(path, reg)
    table(reg)


VERDICTS = ("confirmed", "corrected", "wrong", "inconclusive")


def qa_tally(checks):
    t = {v: 0 for v in VERDICTS}
    for c in checks:
        t[c["verdict"]] += 1
    return t


def qa_score(tally):
    """confirmed / (confirmed + corrected + wrong). Inconclusive is excluded: it is a limit of the checker."""
    decided = tally["confirmed"] + tally["corrected"] + tally["wrong"]
    return None if decided == 0 else tally["confirmed"] / decided


def qa_add(path, a):
    if not (a.worker and a.task and a.claim and a.verdict):
        sys.exit("qa-add needs --worker, --task, --claim and --verdict")
    reg = load(path)
    w = next((x for x in reg["workers"] if x["id"] == a.worker[0]), None)
    if w is None:
        sys.exit(f"no worker {a.worker[0]}")
    t = next((x for x in w["tasks"] if x["id"] == a.task), None)
    if t is None:
        sys.exit(f"no task {a.task} on worker {w['id']}")
    qa = t.setdefault("qa", {"status": "pending", "checks": []})
    check = {"claim": a.claim, "verdict": a.verdict}
    for key, val in (("entry", a.entry), ("worker_value", a.worker_value), ("observed_value", a.observed), ("evidence", a.evidence)):
        if val:
            check[key] = val
    qa.setdefault("checks", []).append(check)
    qa["tally"] = qa_tally(qa["checks"])
    qa["checked_at"] = now()
    qa["checked_by"] = a.by
    qa["status"] = a.qa_status or ("in_progress" if qa["status"] == "pending" else qa["status"])
    save(path, reg)
    s = qa_score(qa["tally"])
    print(f"{w['id']}/{t['id']}: {len(qa['checks'])} checks, score {'n/a' if s is None else format(s, '.0%')}, qa {qa['status']}")


def qa_report(path, pending_only):
    reg = load(path)
    print(f"{'WORKER':<24}{'TASK':<26}{'QA':<13}{'OK':>4}{'FIX':>5}{'BAD':>5}{'?':>4}  SCORE")
    for w in reg["workers"]:
        for t in w["tasks"]:
            qa = t.get("qa")
            status = qa["status"] if qa else "pending"
            if pending_only and status == "complete":
                continue
            tl = qa.get("tally") if qa else None
            tl = tl or {v: 0 for v in VERDICTS}
            s = qa_score(tl)
            print(f"{w['id']:<24}{t['id']:<26}{status:<13}{tl['confirmed']:>4}{tl['corrected']:>5}{tl['wrong']:>5}{tl['inconclusive']:>4}  {'n/a' if s is None else format(s, '.0%')}")


def validate(path, schema_path):
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        sys.exit("validate needs the jsonschema package: pip install jsonschema")
    if not schema_path:
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "schema", "swarm.schema.json")
    schema = load(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(load(path)), key=lambda e: list(e.absolute_path))
    if not errors:
        print("VALID: registry matches schema")
        return
    print(f"INVALID: {len(errors)} errors")
    for e in errors[:20]:
        print("  at", "/".join(str(p) for p in e.absolute_path), "->", e.message[:200])
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["launch", "watch", "status", "stop", "verify", "qa-add", "qa-report", "validate"])
    ap.add_argument("registry")
    ap.add_argument("--worker", action="append", default=[])
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--task")
    ap.add_argument("--claim")
    ap.add_argument("--verdict", choices=VERDICTS)
    ap.add_argument("--entry")
    ap.add_argument("--worker-value", dest="worker_value")
    ap.add_argument("--observed")
    ap.add_argument("--evidence")
    ap.add_argument("--qa-status", dest="qa_status", choices=["pending", "in_progress", "complete"])
    ap.add_argument("--by", default="claude-sonnet-5 (operator session)")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--schema")
    a = ap.parse_args()
    if a.cmd == "launch":
        launch(a.registry, a.worker)
    elif a.cmd == "watch":
        watch(a.registry, a.interval)
    elif a.cmd == "status":
        table(refresh(a.registry))
    elif a.cmd == "stop":
        stop(a.registry, a.worker)
    elif a.cmd == "verify":
        verify(a.registry)
    elif a.cmd == "qa-add":
        qa_add(a.registry, a)
    elif a.cmd == "qa-report":
        qa_report(a.registry, a.pending)
    elif a.cmd == "validate":
        validate(a.registry, a.schema)


if __name__ == "__main__":
    main()
