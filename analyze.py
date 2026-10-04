"""Load every scored call into SQLite and run the conversation analytics in sql/analytics.sql.

    python analyze.py        # writes results/calls.db and results/analytics.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from voiceagent.store import build, run_queries  # noqa: E402

ROOT = Path(__file__).parent
BEST = "few_shot:qwen2.5:3b:code_flow"

if __name__ == "__main__":
    con = build(ROOT / "results" / "calls", ROOT / "results" / "calls.db")
    out = run_queries(con, ROOT / "sql" / "analytics.sql", {"best": BEST})
    (ROOT / "results" / "analytics.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for name, table in out.items():
        print(f"\n## {name}\n" + " | ".join(table["columns"]))
        for row in table["rows"]:
            print(" | ".join(str(x) for x in row))
