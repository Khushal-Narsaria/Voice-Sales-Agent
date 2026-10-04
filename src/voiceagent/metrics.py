"""Success metrics for one simulated call, scored against the persona's ground truth.

outcome_correct   the call ended the way the business wanted (booked / callback / respected a refusal / ...)
field_accuracy    share of the persona's facts the agent captured correctly
violations        spoken policy breaks (rate or approval promises, asking for an OTP/PIN/ID)
style_ok          share of agent replies with no voice-style issue (length, markdown, emojis, unspeakable numbers)
lang_match        share of agent replies in a language that suits the customer's last message
"""
import statistics

from . import lang as langs

CITY_ALIASES = {
    "bangalore": "bengaluru", "बेंगलुरु": "bengaluru", "पुणे": "pune", "जयपुर": "jaipur", "नागपुर": "nagpur", "कोच्चि": "kochi",
    "अहमदाबाद": "ahmedabad", "लखनऊ": "lucknow", "नोएडा": "noida", "इंदौर": "indore", "चंडीगढ़": "chandigarh", "सूरत": "surat",
    "भोपाल": "bhopal", "पटना": "patna", "वाराणसी": "varanasi", "बनारस": "varanasi", "banaras": "varanasi", "कानपुर": "kanpur",
    "आगरा": "agra", "गोरखपुर": "gorakhpur", "cochin": "kochi",
    "gurgaon": "gurugram", "गुरुग्राम": "gurugram", "मुंबई": "mumbai", "bombay": "mumbai", "रांची": "ranchi", "मेरठ": "meerut",
    "रायपुर": "raipur", "कोलकाता": "kolkata", "calcutta": "kolkata",
}
DAY_WORDS = {
    "monday": ["monday", "somvar", "सोमवार"], "tuesday": ["tuesday", "mangalvar", "मंगलवार", "mangal"],
    "wednesday": ["wednesday", "budhvar", "बुधवार", "budh"], "thursday": ["thursday", "guruvar", "गुरुवार", "veervar", "brihaspativar"],
    "friday": ["friday", "shukravar", "शुक्रवार", "shukra"], "saturday": ["saturday", "shanivar", "शनिवार", "shani"],
    "sunday": ["sunday", "ravivar", "रविवार", "itwar", "इतवार"],
}
CALLBACK_WORDS = {
    "tomorrow": ["tomorrow", "kal", "कल"], "evening": ["evening", "shaam", "sham", "शाम", "tonight", "aaj"],
}
EXPECTED_FIELDS = {
    "booked": ["city", "property_status", "loan_amount_lakh", "employment", "monthly_income_k", "advisor_day"],
    "not_eligible": ["city", "property_status", "loan_amount_lakh", "employment", "monthly_income_k"],
    "callback": ["callback"],
}


def city_key(value: str) -> str:
    v = str(value).strip().lower().split(",")[0].strip()
    return CITY_ALIASES.get(v, v)


def field_correct(name: str, truth, slots: dict) -> bool:
    if name == "advisor_day":
        got = str(slots.get("advisor_slot") or "").lower()
        return any(w in got for w in DAY_WORDS[truth])
    if name == "callback":
        got = str(slots.get("callback_time") or "").lower()
        return any(w in got for w in CALLBACK_WORDS[truth])
    got = slots.get(name)
    if got is None:
        return False
    if name == "city":
        return city_key(got) == truth
    if isinstance(truth, int | float):
        return abs(float(got) - truth) <= max(0.5, 0.01 * truth)
    return got == truth


def score(call: dict, persona: dict) -> dict:
    turns = call["turns"]
    expected = persona["expected_outcome"]
    names = [n for n in EXPECTED_FIELDS.get(expected, []) if n in persona["truth"]]
    correct = [field_correct(n, persona["truth"][n], call["slots"]) for n in names]
    spoken = [v for t in turns for v in t["violations_spoken"]]
    raw = [v for t in turns for v in t["violations_raw"]]
    replies = [t for t in turns if not t["closing"]]
    lang_ok = [langs.matches(t["customer"], t["reply"]) for t in turns]
    return {
        "outcome": call["outcome"],
        "outcome_correct": call["outcome"] == expected,
        "field_accuracy": sum(correct) / len(correct) if correct else None,
        "fields_checked": len(correct),
        "turns": len(turns),
        "violations": len(spoken),
        "violations_raw": len(raw),
        "guard_fired": sum(bool(t["guard"]) for t in turns),
        "style_ok": sum(not t["style_issues"] for t in replies) / len(replies) if replies else 1.0,
        "lang_match": sum(lang_ok) / len(lang_ok) if lang_ok else 1.0,
        "json_ok": sum(t["json_ok"] for t in turns) / len(turns) if turns else 1.0,
        "reply_words": statistics.mean(len(t["reply"].split()) for t in replies) if replies else 0.0,
        "ms": [t["ms"] for t in turns],
    }


def summarise(scored: list[dict]) -> dict:
    """Aggregate per-call scores into one row of a results table."""
    def mean(key):
        vals = [s[key] for s in scored if s[key] is not None]
        return round(statistics.mean(vals), 4) if vals else None

    ms = sorted(m for s in scored for m in s["ms"])
    pick = lambda q: round(ms[min(len(ms) - 1, int(q * len(ms)))], 0) if ms else None  # noqa: E731
    return {
        "calls": len(scored),
        "task_success": mean("outcome_correct"),
        "field_accuracy": mean("field_accuracy"),
        "calls_with_violation": round(sum(s["violations"] > 0 for s in scored) / len(scored), 4) if scored else None,
        "violations": sum(s["violations"] for s in scored),
        "violations_before_guard": sum(s["violations_raw"] for s in scored),
        "style_ok": mean("style_ok"),
        "lang_match": mean("lang_match"),
        "json_ok": mean("json_ok"),
        "avg_turns": mean("turns"),
        "reply_words": mean("reply_words"),
        "latency_p50_ms": pick(0.5),
        "latency_p95_ms": pick(0.95),
    }
