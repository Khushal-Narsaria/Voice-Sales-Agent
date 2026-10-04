"""Voice robustness test: synthesize customer answers, add call-centre babble noise, transcribe with Whisper, and check
whether the agent still captures the right field from the transcript.

    python run_voice_eval.py          # writes results/voice.json

36 utterances (12 English, 12 Hinglish, 12 Hindi) x 4 noise levels (clean, 20, 10, 5 dB SNR).
Primary metric: field recovered end to end (audio -> Whisper -> agent -> flow engine), against the same utterance as
text. Word error rate is reported for English and Hindi, where reference and transcript use the same script.
"""
import json
import re
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))

from voiceagent.agent import Agent  # noqa: E402
from voiceagent.flow import Call  # noqa: E402
from voiceagent.llm import ChatModel  # noqa: E402
from voiceagent.metrics import field_correct  # noqa: E402
from voiceagent.numbers import WORDS  # noqa: E402
from voiceagent.voice import audio, stt, tts  # noqa: E402

ROOT = Path(__file__).parent
OUT = ROOT / "results"
AUDIO = ROOT / "out" / "voice"
SNRS = [None, 20, 10, 5]
STATE_FOR = {"city": "discover", "property_status": "discover", "loan_amount_lakh": "qualify", "employment": "qualify",
             "monthly_income_k": "qualify", "advisor_slot": "book"}
PREFILL = {"discover": {"consent": True},
           "qualify": {"consent": True, "city": "Pune", "property_status": "identified"},
           "book": {"consent": True, "city": "Pune", "property_status": "identified", "loan_amount_lakh": 60,
                    "employment": "salaried", "monthly_income_k": 95}}
TRUTH_KEY = {"advisor_slot": "advisor_day"}


def norm_words(text: str) -> list[str]:
    toks = re.sub(r"[^\wऀ-ॿ\s]", " ", text.lower().translate(str.maketrans("०१२३४५६७८९", "0123456789"))).split()
    return [str(int(WORDS[t])) if t in WORDS and float(WORDS[t]).is_integer() else t for t in toks]


def wer(ref: str, hyp: str) -> float:
    r, h = norm_words(ref), norm_words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def understood(agent: Agent, utt: dict, said: str) -> bool:
    """Run one agent turn on `said` in the stage where the field is asked; True if the field is captured correctly."""
    state = STATE_FOR[utt["field"]]
    call = Call(state=state, slots=dict(PREFILL[state]), states_seen=["greet", state])
    question = agent.engine.flow.questions[utt["field"]][utt["language"]]
    history = [{"speaker": "agent", "text": question}, {"speaker": "customer", "text": said or "..."}]
    agent.respond(call, history, seed=7)
    return field_correct(TRUTH_KEY.get(utt["field"], utt["field"]), utt["value"], call.slots)


def main() -> None:
    utts = json.loads((ROOT / "data" / "voice_utterances.json").read_text(encoding="utf-8"))
    agent = Agent(ChatModel("qwen2.5:3b", cache=OUT / "llm_cache.jsonl"), variant="few_shot")
    clean = {}
    for u in utts:
        path, _ = tts.speak(u["text"], u["language"], AUDIO / "clean")
        clean[u["id"]] = audio.load(path)

    rng = np.random.default_rng(0)
    rows = []
    for u in utts:
        others = [clean[o["id"]] for o in utts if o["id"] != u["id"]]
        noise = audio.babble([others[i] for i in rng.choice(len(others), 3, replace=False)], len(clean[u["id"]]), rng)
        text_ok = understood(agent, u, u["text"])
        for snr in SNRS:
            samples = clean[u["id"]] if snr is None else audio.mix(clean[u["id"]], noise, snr)
            if snr is not None and u["id"] in ("en-1", "hg-1", "hi-1"):
                audio.save_wav(samples, ROOT / "docs" / "audio" / "noise" / f"{u['id']}_{snr}db.wav")
            res = stt.transcribe(samples)
            locked = stt.transcribe(samples, language="en" if u["language"] == "en" else "hi")  # language known from the call
            rows.append({
                "id": u["id"], "language": u["language"], "field": u["field"], "snr": "clean" if snr is None else snr,
                "text": u["text"], "transcript": res["text"], "detected_language": res["language"],
                "audio_s": round(len(samples) / audio.RATE, 2), "stt_s": round(res["seconds"], 3),
                "wer": round(wer(u["text"], res["text"]), 3) if u["language"] in ("en", "hi") else None,
                "field_ok_from_text": text_ok, "field_ok_from_audio": understood(agent, u, res["text"]),
                "transcript_locked": locked["text"], "stt_locked_s": round(locked["seconds"], 3),
                "wer_locked": round(wer(u["text"], locked["text"]), 3) if u["language"] in ("en", "hi") else None,
                "field_ok_from_audio_locked": understood(agent, u, locked["text"]),
            })
            print(f"{u['id']:6} {rows[-1]['snr']!s:5} ok={rows[-1]['field_ok_from_audio']!s:5} {res['text'][:70]}", flush=True)

    summary = {"by_snr": {}, "by_language": {}}
    for snr in ["clean", 20, 10, 5]:
        sel = [r for r in rows if r["snr"] == snr]
        summary["by_snr"][str(snr)] = {
            "field_ok_from_audio": round(statistics.mean(r["field_ok_from_audio"] for r in sel), 3),
            "wer_en": round(statistics.mean(r["wer"] for r in sel if r["language"] == "en"), 3),
            "wer_hi": round(statistics.mean(r["wer"] for r in sel if r["language"] == "hi"), 3),
            "field_ok_from_audio_locked": round(statistics.mean(r["field_ok_from_audio_locked"] for r in sel), 3),
            "wer_hi_locked": round(statistics.mean(r["wer_locked"] for r in sel if r["language"] == "hi"), 3),
        }
    for lang in ["en", "hinglish", "hi"]:
        sel = [r for r in rows if r["language"] == lang]
        summary["by_language"][lang] = {
            "field_ok_from_text": round(statistics.mean(r["field_ok_from_text"] for r in sel if r["snr"] == "clean"), 3),
            **{f"field_ok_from_audio_{s}": round(statistics.mean(r["field_ok_from_audio"] for r in sel if r["snr"] == s), 3)
               for s in ["clean", 20, 10, 5]},
            **{f"field_ok_locked_{s}": round(statistics.mean(r["field_ok_from_audio_locked"] for r in sel if r["snr"] == s), 3)
               for s in ["clean", 20, 10, 5]},
            "detected_as": {k: sum(r["detected_language"] == k for r in sel) for k in sorted({r["detected_language"] for r in sel})},
        }
    clean_rows = [r for r in rows if r["snr"] == "clean"]
    summary["field_ok_from_text"] = round(statistics.mean(r["field_ok_from_text"] for r in clean_rows), 3)
    summary["stt_seconds_median"] = round(statistics.median(r["stt_s"] for r in rows), 3)
    summary["real_time_factor_median"] = round(statistics.median(r["stt_s"] / r["audio_s"] for r in rows), 3)
    summary["audio_seconds_median"] = round(statistics.median(r["audio_s"] for r in rows), 2)

    # Text-to-speech time for agent replies (network gTTS), measured on fresh sentences from the evaluated calls.
    calls = [json.loads(line) for line in (OUT / "calls" / "few_shot_qwen2.5_3b_code_flow.jsonl").read_text().splitlines()]
    replies = [(t["reply"], t["reply_lang"]) for c in calls for t in c["turns"]][:24]
    tts_times = [tts.speak(text, lang, AUDIO / "replies")[1] for text, lang in replies]
    tts_times = [t for t in tts_times if t > 0] or [0.0]
    summary["tts_seconds_median"] = round(statistics.median(tts_times), 3)

    (OUT / "voice.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
