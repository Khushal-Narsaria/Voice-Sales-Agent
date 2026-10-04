import json

import numpy as np

from voiceagent.store import build, run_queries
from voiceagent.voice.audio import mix


def test_sql_analytics_on_a_tiny_run(tmp_path):
    calls = tmp_path / "calls"
    calls.mkdir()
    turn = {"customer": "Pune", "customer_lang": "en", "intent": "provide_info", "reply": "Which city?", "reply_lang": "en",
            "state": "discover", "ms": 100.0, "json_ok": True, "closing": False, "lang_retry": False, "style_issues": [],
            "guard": [], "violations_raw": ["rate_promise"], "violations_spoken": []}
    row = {"config": "persona:qwen2.5:3b:code_flow", "persona": "p1", "language": "en", "behavior": "cooperative",
           "expected": "booked", "outcome": "booked", "states_seen": ["greet", "discover", "qualify", "book"], "turns": [turn],
           "slots": {"city": "Pune"}, "rejected": [["employment", "x", "invalid value"]], "fixed": [],
           "score": {"outcome_correct": True, "field_accuracy": 1.0, "turns": 1}}
    (calls / "a.jsonl").write_text(json.dumps(row) + "\n")
    con = build(calls, tmp_path / "x.db")
    sql = tmp_path / "q.sql"
    sql.write_text("-- name: n\nSELECT COUNT(*) AS c FROM calls WHERE config = :best\n-- name: g\nSELECT kind, stage FROM violations\n")
    out = run_queries(con, sql, {"best": "persona:qwen2.5:3b:code_flow"})
    assert out["n"]["rows"] == [[1]] and out["g"]["rows"] == [["rate_promise", "model output"]]


def test_mix_hits_the_target_snr():
    rng = np.random.default_rng(0)
    speech = np.sin(np.linspace(0, 200, 16000)).astype(np.float32) * 0.3
    noise = rng.normal(0, 1, 16000).astype(np.float32)
    mixed = mix(speech, noise, 10)
    added = mixed - speech
    snr = 10 * np.log10(np.mean(speech ** 2) / np.mean(added ** 2))
    assert abs(snr - 10) < 0.5
