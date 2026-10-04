"""Load call transcripts into SQLite so conversations can be analysed with plain SQL (sql/analytics.sql)."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE configs (config TEXT PRIMARY KEY, variant TEXT, model TEXT, flow_mode TEXT);
CREATE TABLE calls (
    call_id INTEGER PRIMARY KEY, config TEXT REFERENCES configs, persona TEXT, language TEXT, behavior TEXT,
    expected TEXT, outcome TEXT, outcome_correct INTEGER, field_accuracy REAL, turns INTEGER, furthest_state TEXT
);
CREATE TABLE turns (
    call_id INTEGER REFERENCES calls, idx INTEGER, customer TEXT, customer_lang TEXT, intent TEXT, reply TEXT,
    reply_lang TEXT, state TEXT, words INTEGER, ms REAL, json_ok INTEGER, closing INTEGER, lang_retry INTEGER,
    style_ok INTEGER, guard_fired INTEGER
);
CREATE TABLE violations (call_id INTEGER REFERENCES calls, idx INTEGER, kind TEXT, stage TEXT);
CREATE TABLE field_events (call_id INTEGER REFERENCES calls, field TEXT, value TEXT, event TEXT, reason TEXT);
"""
STATE_ORDER = ["greet", "discover", "qualify", "book", "callback"]


def build(calls_dir: Path, db_path: Path) -> sqlite3.Connection:
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    call_id = 0
    for path in sorted(calls_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            variant, *model, flow_mode = r["config"].split(":")
            con.execute("INSERT OR IGNORE INTO configs VALUES (?,?,?,?)", (r["config"], variant, ":".join(model), flow_mode))
            call_id += 1
            seen = [s for s in STATE_ORDER if s in r["states_seen"]]
            s = r["score"]
            con.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                call_id, r["config"], r["persona"], r["language"], r["behavior"], r["expected"], r["outcome"],
                int(s["outcome_correct"]), s["field_accuracy"], s["turns"], seen[-1] if seen else "greet"))
            for i, t in enumerate(r["turns"]):
                con.execute("INSERT INTO turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    call_id, i, t["customer"], t["customer_lang"], t["intent"], t["reply"], t["reply_lang"], t["state"],
                    len(t["reply"].split()), t["ms"], int(t["json_ok"]), int(t["closing"]), int(t.get("lang_retry", False)),
                    int(not t["style_issues"]), int(bool(t["guard"]))))
                for kind in t["violations_raw"]:
                    con.execute("INSERT INTO violations VALUES (?,?,?,?)", (call_id, i, kind, "model output"))
                for kind in t["violations_spoken"]:
                    con.execute("INSERT INTO violations VALUES (?,?,?,?)", (call_id, i, kind, "spoken"))
            for name, value in r["slots"].items():
                con.execute("INSERT INTO field_events VALUES (?,?,?,?,?)", (call_id, name, str(value), "kept", None))
            for item in r.get("rejected", []):
                name, value, reason = (list(item) + [None, None])[:3]
                con.execute("INSERT INTO field_events VALUES (?,?,?,?,?)", (call_id, name, str(value), "rejected", reason))
            for name, before, after in r.get("fixed", []):
                con.execute("INSERT INTO field_events VALUES (?,?,?,?,?)", (call_id, name, f"{before} -> {after}", "unit_fixed", None))
    con.commit()
    return con


def run_queries(con: sqlite3.Connection, sql_path: Path, params: dict | None = None) -> dict:
    """Run every '-- name: ...' query in the SQL file; return {name: {"columns": [...], "rows": [...]}}."""
    out, name, buf = {}, None, []
    for line in sql_path.read_text().splitlines() + ["-- name: _end"]:
        if line.startswith("-- name:"):
            if name and "".join(buf).strip():
                cur = con.execute("\n".join(buf), params or {})
                out[name] = {"columns": [d[0] for d in cur.description], "rows": [list(r) for r in cur.fetchall()]}
            name, buf = line.split(":", 1)[1].strip(), []
        else:
            buf.append(line)
    return out
