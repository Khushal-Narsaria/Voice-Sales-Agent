"""Conversation flow engine: turns a business goal (the YAML flow) into deterministic call logic.

The language model proposes an intent and field values for each customer turn; this engine validates them,
moves the call between states, applies business rules (eligibility, loan range) and decides when and how the
call ends. Keeping these decisions in code makes every call auditable and stops the model from skipping steps.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import cues
from .numbers import reconcile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FLOW = ROOT / "config" / "home_loan_flow.yaml"

INTENTS = ("provide_info", "agree", "busy", "not_interested", "wrong_person", "question", "objection", "off_topic")
OUTCOMES = ("booked", "callback", "not_interested", "not_eligible", "wrong_number", "max_turns")
ORDER = ("greet", "discover", "qualify", "book")

ENUM_SYNONYMS = {
    "property_status": {
        "identified": "identified", "finalised": "identified", "finalized": "identified", "chosen": "identified",
        "selected": "identified", "decided": "identified", "booked": "identified", "yes": "identified",
        "searching": "searching", "looking": "searching", "still looking": "searching", "not yet": "searching",
        "no": "searching", "exploring": "searching", "not decided": "searching",
    },
    "employment": {
        "salaried": "salaried", "salary": "salaried", "job": "salaried", "employee": "salaried", "service": "salaried",
        "self_employed": "self_employed", "self employed": "self_employed", "self-employed": "self_employed",
        "business": "self_employed", "businessman": "self_employed", "own business": "self_employed",
        "freelancer": "self_employed", "professional": "self_employed",
    },
}


class Flow:
    def __init__(self, path: Path = DEFAULT_FLOW):
        spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.business = spec["business"]
        self.rules = spec["rules"]
        self.fields = spec["fields"]
        self.states = spec["states"]
        self.closings = spec["closings"]
        self.questions = spec["questions"]

    def closing(self, outcome: str, lang: str, slots: dict) -> str:
        values = {k: (v if v is not None else "") for k, v in slots.items()}
        values.setdefault("advisor_slot", "the chosen time")
        values.setdefault("callback_time", "later")
        values["name_hint"] = ""
        return self.closings[outcome][lang if lang in ("en", "hinglish", "hi") else "en"].format(**values)


def _number(value) -> float | None:
    """Accept 50, "50", "50 lakh", "1.2 crore", "80k", "80,000"; return a float or None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).lower().replace(",", "")
    m = re.search(r"\d+(\.\d+)?", text)
    if not m:
        return None
    n = float(m.group())
    if "crore" in text or "cr" in text.split():
        n *= 100
    return n


def normalise(name: str, value, spec: dict):
    """Validate one field value from the model. Returns the cleaned value, or None if it is unusable."""
    if value is None or value == "":
        return None
    kind = spec["type"]
    if kind == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return True if text in ("true", "yes", "haan", "ha", "हाँ") else False if text in ("false", "no", "nahi", "नहीं") else None
    if kind == "enum":
        key = str(value).strip().lower().replace("-", " ") if name != "employment" else str(value).strip().lower()
        if key in spec["values"]:
            return key
        return ENUM_SYNONYMS.get(name, {}).get(key) or ENUM_SYNONYMS.get(name, {}).get(key.replace("_", " "))
    if kind == "number":
        n = _number(value)
        if n is None or n <= 0:
            return None
        if name == "loan_amount_lakh" and n >= 10_000:  # given in rupees
            n /= 100_000
        if name == "monthly_income_k" and n >= 5_000:  # given in rupees
            n /= 1_000
        return round(n, 2)
    text = str(value).strip()
    return text[:80] if text and text.lower() not in ("none", "null", "unknown", "n/a") else None


@dataclass
class Call:
    state: str = "greet"
    slots: dict = field(default_factory=dict)
    outcome: str | None = None
    agent_turns: int = 0
    states_seen: list = field(default_factory=lambda: ["greet"])
    rejected: list = field(default_factory=list)  # (field, value, reason) the engine refused
    fixed: list = field(default_factory=list)  # (field, model value, corrected value) unit slips caught by the number check

    @property
    def done(self) -> bool:
        return self.outcome is not None


class Engine:
    def __init__(self, flow: Flow | None = None):
        self.flow = flow or Flow()

    def missing(self, call: Call) -> list[str]:
        """Fields still needed in the current state, in asking order."""
        return [f for f in self.flow.states[call.state]["collect"] if call.slots.get(f) is None]

    def goal(self, call: Call) -> list[str]:
        """What the agent should try to collect next: the current state's gaps, then the next state's fields."""
        need = self.missing(call)
        if call.state in ORDER and call.state != "book":
            nxt = ORDER[ORDER.index(call.state) + 1]
            need += [f for f in self.flow.states[nxt]["collect"] if call.slots.get(f) is None]
        return need

    def next_question(self, call: Call, lang: str) -> str:
        need = self.missing(call)
        return self.flow.questions[need[0]][lang if lang in ("en", "hinglish", "hi") else "en"] if need else ""

    def _enter(self, call: Call, state: str) -> None:
        call.state = state
        if state not in call.states_seen:
            call.states_seen.append(state)

    def apply(self, call: Call, intent: str, slots: dict, said: str = "", evidence: dict | None = None) -> Call:
        """Apply one understood customer turn and advance the call.

        said      the customer's raw words: used to check numbers, quotes and callback cues
        evidence  {field: the customer's words the model based it on}; when given, a field without a quote that
                  really occurs in `said` is rejected (stops invented values)
        """
        intent = intent if intent in INTENTS else "provide_info"
        # Safety net on the customer's own words: "call me tomorrow" is a callback, not a refusal.
        if said and cues.wants_callback(said) and intent in ("not_interested", "off_topic", "objection", "provide_info", "question") \
                and call.state in ("greet", "discover", "qualify"):  # at booking, a time is the answer, not a callback
            intent = "busy"

        # Accept only fields that make sense now: the current goal, corrections of known fields, and callback timing.
        upcoming = ORDER[ORDER.index(call.state):] if call.state in ORDER else ()
        allowed = {f for s in upcoming for f in self.flow.states[s]["collect"]} | {k for k, v in call.slots.items() if v is not None} \
            | {"consent", "callback_time"}
        for name, value in (slots or {}).items():
            if name not in self.flow.fields or value in (None, ""):
                continue
            if name not in allowed:
                call.rejected.append((name, value, "not asked yet"))
                continue
            if evidence is not None and name != "consent":
                quote = evidence.get(name)
                ok = cues.grounded(quote, said) if quote else cues.supported(name, value, said)
                if not ok:
                    call.rejected.append((name, value, "not supported by the customer's words"))
                    continue
            clean = normalise(name, value, self.flow.fields[name])
            if clean is None:
                call.rejected.append((name, value, "invalid value"))
                continue
            if name in ("advisor_slot", "callback_time") and not cues.slot_time(clean):
                call.rejected.append((name, value, "no day or time"))
                continue
            if self.flow.fields[name]["type"] == "number":
                fixed = reconcile(name, clean, said)
                if fixed != clean:
                    call.fixed.append((name, clean, fixed))
                clean = fixed
            call.slots[name] = clean

        if intent == "wrong_person":
            call.outcome = "wrong_number"
            return call
        if intent == "not_interested":
            call.outcome = "not_interested"
            return call
        if intent == "busy" and call.state != "callback":
            self._enter(call, "callback")
        if call.state == "greet" and call.slots.get("consent") is False and intent != "busy":
            self._enter(call, "callback")
        if call.state == "callback" and not call.slots.get("callback_time") and said and cues.slot_time(said):
            call.slots["callback_time"] = " ".join(dict.fromkeys(m.group(0) for m in cues.DAY_OR_TIME.finditer(said)))

        # Engaging with the call (answering, asking, even objecting) counts as agreeing to talk.
        engaged = intent in ("agree", "provide_info", "question", "objection")
        if call.state == "greet" and call.slots.get("consent") is not False and (call.slots.get("consent") or engaged):
            call.slots["consent"] = True
            self._enter(call, "discover")

        # Move forward through every state whose fields are complete (a customer may answer several at once).
        while call.state in ORDER and not self.missing(call):
            if call.state in ("qualify", "book"):  # re-checked before booking: a late correction can change eligibility
                verdict = self._eligibility(call)
                if verdict:
                    call.outcome = verdict
                    return call
            if call.state == "book":
                call.outcome = "booked"
                return call
            self._enter(call, ORDER[ORDER.index(call.state) + 1])

        if call.state == "callback" and call.slots.get("callback_time"):
            call.outcome = "callback"
        return call

    def _eligibility(self, call: Call) -> str | None:
        lo, hi = self.flow.rules["loan_amount_lakh"]
        if call.slots["monthly_income_k"] < self.flow.rules["min_monthly_income_k"]:
            return "not_eligible"
        if not lo <= call.slots["loan_amount_lakh"] <= hi:
            return "not_eligible"
        return None

    def count_turn(self, call: Call) -> None:
        call.agent_turns += 1
        if not call.done and call.agent_turns >= self.flow.rules["max_turns"]:
            call.outcome = "max_turns"
