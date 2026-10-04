"""Write the results tables into README.md (between the <!-- results --> markers) from results/*.json."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
RES = ROOT / "results"
VARIANT = {"zero_shot": "Zero-shot", "few_shot": "Few-shot", "persona": "Few-shot + persona & voice rules"}
FLOW = {"code_flow": "flow engine in code", "llm_flow": "LLM runs the flow"}
pct = lambda v: "–" if v is None else f"{v * 100:.1f}%"  # noqa: E731


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(header))) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    s = json.loads((RES / "summary.json").read_text())
    rows = [[f"{VARIANT[v['variant']]} · {v['model']} · {FLOW[v['flow_mode']]}", pct(v["task_success"]), pct(v["field_accuracy"]),
             v["violations"], v["violations_before_guard"], pct(v["style_ok"]), pct(v["lang_match"]), pct(v["json_ok"]),
             f"{v['avg_turns']:.1f}", f"{v['latency_p50_ms']:,.0f} / {v['latency_p95_ms']:,.0f}"] for v in s.values()]
    parts = ["### Simulated calls (26 held-out personas per row)\n",
             table(["Agent", "Task success", "Fields correct", "Spoken violations", "Caught by guard", "Voice style", "Language match",
                    "Valid JSON", "Turns", "Latency p50 / p95 ms"], rows)]
    a = json.loads((RES / "analytics.json").read_text())
    for name, title in [("by_language", "By language (deployed agent)"), ("by_behavior", "By customer behaviour (deployed agent)")]:
        t = a[name]
        parts += [f"\n### {title}\n", table(t["columns"], [[("–" if c is None else c) for c in r] for r in t["rows"]])]
    if (RES / "voice.json").exists():
        v = json.loads((RES / "voice.json").read_text())["summary"]
        names = {"en": "English", "hinglish": "Hinglish", "hi": "Hindi"}
        rows = []
        for lang, d in v["by_language"].items():
            rows.append([names[lang], "auto-detect", pct(d["field_ok_from_text"])] + [pct(d[f"field_ok_from_audio_{k}"]) for k in ("clean", 20, 10, 5)])
            rows.append([names[lang], "language locked", ""] + [pct(d[f"field_ok_locked_{k}"]) for k in ("clean", 20, 10, 5)])
        parts += ["\n### Voice: fact captured from audio (12 utterances per language)\n",
                  "Whisper either detects the language itself (auto) or is told the call's language (locked: Hindi for Hindi and "
                  "Hinglish callers, English otherwise), as the agent already knows it from earlier turns.\n",
                  table(["Language", "Whisper", "Typed text", "Clean audio", "20 dB", "10 dB", "5 dB"], rows),
                  f"\nWord error rate, English: {pct(v['by_snr']['clean']['wer_en'])} clean, {pct(v['by_snr']['5']['wer_en'])} at 5 dB; "
                  f"Hindi: {pct(v['by_snr']['clean']['wer_hi'])} clean ({pct(v['by_snr']['clean']['wer_hi_locked'])} locked), "
                  f"{pct(v['by_snr']['5']['wer_hi'])} at 5 dB ({pct(v['by_snr']['5']['wer_hi_locked'])} locked). "
                  f"Whisper small (int8, CPU) median {v['stt_seconds_median']} s for {v['audio_seconds_median']} s of audio "
                  f"(real-time factor {v['real_time_factor_median']}); gTTS median {v['tts_seconds_median']} s per reply."]
    readme = (ROOT / "README.md").read_text()
    readme = re.sub(r"<!-- results -->.*<!-- /results -->", "<!-- results -->\n" + "\n".join(parts) + "\n<!-- /results -->", readme, flags=re.S)
    (ROOT / "README.md").write_text(readme)
    print("README tables updated")


if __name__ == "__main__":
    main()
