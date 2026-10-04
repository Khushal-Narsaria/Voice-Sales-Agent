"""Assemble docs/data.json for the live page, and record the agent's replies for a few example calls (gTTS).

    python build_page.py --repo https://github.com/S-Harshni/Voice-Sales-Agent --author "S Harshni"
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from run_eval import GRID, name  # noqa: E402

ROOT = Path(__file__).parent
RES, DOCS = ROOT / "results", ROOT / "docs"
BEST = "few_shot:qwen2.5:3b:code_flow"
AUDIO_CALLS = ["hi01", "hg07", "en09", "hg04"]  # Hindi booking, Hinglish rate questions, English injection attempt, Hinglish callback


def sql_blocks() -> dict:
    out, name_, buf = {}, None, []
    for line in (ROOT / "sql" / "analytics.sql").read_text().splitlines() + ["-- name: _end"]:
        if line.startswith("-- name:"):
            if name_:
                out[name_] = "\n".join(buf).strip()
            name_, buf = line.split(":", 1)[1].strip(), []
        elif name_:
            buf.append(line)
    return out


def iterations() -> list[dict]:
    rows = []
    for line in (ROOT / "notes" / "PROMPT_ITERATIONS.md").read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].isdigit():
            clean = [re.sub(r"\*\*", "", c) for c in cells]
            rows.append({"n": clean[0], "change": clean[1], "problem": clean[2], "result": clean[3]})
    return rows


def record_audio(calls: list[dict]) -> dict:
    from voiceagent.lang import detect
    from voiceagent.voice.tts import speak
    out = {}
    target = DOCS / "audio" / "calls"
    for c in calls:
        if c["config"] != BEST or c["persona"] not in AUDIO_CALLS:
            continue
        files = []
        for i, t in enumerate(c["turns"]):
            path, _ = speak(t["reply"], detect(t["reply"]), ROOT / "out" / "page_audio")
            dest = target / f"{c['persona']}_{i}.mp3"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, dest)
            files.append(f"audio/calls/{dest.name}")
        out[f"{c['config']}|{c['persona']}"] = files
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--author", required=True)
    args = ap.parse_args()

    summary = json.loads((RES / "summary.json").read_text())
    order = [name(c) for c in GRID if name(c) in summary]
    calls = []
    for cfg in order:
        for line in (RES / "calls" / f"{cfg.replace(':', '_')}.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            calls.append({
                "config": r["config"], "persona": r["persona"], "language": r["language"], "behavior": r["behavior"],
                "expected": r["expected"], "outcome": r["outcome"], "field_accuracy": r["score"]["field_accuracy"],
                "opening": r["opening"], "slots": r["slots"],
                "turns": [{k: t[k] for k in ("customer", "intent", "state", "reply", "guard", "style_issues")} | {"lang_retry": t.get("lang_retry", False)}
                          for t in r["turns"]],
            })
    voice = json.loads((RES / "voice.json").read_text()) if (RES / "voice.json").exists() else None
    if voice:
        voice["rows"] = [{k: r[k] for k in ("id", "snr", "text", "transcript", "field_ok_from_audio", "transcript_locked", "field_ok_from_audio_locked")} for r in voice["rows"]]
    data = {
        "repo": args.repo, "author": args.author, "best": BEST, "order": order, "summary": summary, "calls": calls,
        "analytics": {"results": json.loads((RES / "analytics.json").read_text()), "sql": sql_blocks()},
        "voice": voice, "iterations": iterations(), "audio": record_audio(calls),
    }
    (DOCS / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"docs/data.json: {len(calls)} calls, {(DOCS / 'data.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
