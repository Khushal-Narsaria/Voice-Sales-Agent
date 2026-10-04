"""The voice sales agent: one customer turn in, one spoken reply out.

code_flow (default): the model returns {intent, fields, reply}; the flow engine validates the fields, moves the
call forward and decides the ending; endings use fixed closing lines; replies are cleaned for speech and passed
through compliance guardrails.
llm_flow (ablation): the model also chooses the next state and whether to end the call; no guardrails.
"""
import json
import re
from dataclasses import dataclass, field

from . import lang as langs
from . import prompts
from . import voice_rules as vr
from .flow import OUTCOMES, Call, Engine, normalise

REPEAT = {
    "en": "Sorry, I didn't catch that. Could you say it once more?",
    "hinglish": "Sorry, main samajh nahi paayi. Ek baar phir bata sakte hain?",
    "hi": "माफ़ कीजिए, मैं समझ नहीं पाई। क्या आप एक बार फिर बता सकते हैं?",
}


@dataclass
class Turn:
    intent: str
    fields: dict
    raw_reply: str
    reply: str
    lang: str
    json_ok: bool
    ms: float
    guard: list = field(default_factory=list)
    closing: bool = False
    lang_retry: bool = False


QUESTION = re.compile(r"[^.!?।]*\?")


def compose(model_reply: str, question: str, intent: str) -> str:
    """Keep the model's acknowledgement or answer, drop any question it asked, and add the engine's next question.

    The reply is generated before the engine updates the call, so the model's own question can be stale (asking for a
    field the customer just gave). The scripted question always matches the current state.
    """
    keep = QUESTION.sub("", model_reply).strip()
    if not question:
        return model_reply.strip() or keep
    if intent in ("provide_info", "agree") and len(keep.split()) > 14:  # acknowledgements stay short on a call
        keep = re.split(r"(?<=[.!।])\s", keep)[0]
    return f"{keep} {question}".strip() if keep else question


def parse_json(text: str) -> dict | None:
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            out = json.loads(m.group())
        except json.JSONDecodeError:
            return None
    return out if isinstance(out, dict) else None


class Agent:
    def __init__(self, llm, variant: str = "persona", flow_mode: str = "code_flow", engine: Engine | None = None,
                 temperature: float = 0.3):
        assert variant in ("zero_shot", "few_shot", "persona")
        assert flow_mode in ("code_flow", "llm_flow")
        self.llm, self.variant, self.flow_mode, self.temperature = llm, variant, flow_mode, temperature
        self.engine = engine or Engine()

    def opening(self) -> str:
        return prompts.OPENING

    def respond(self, call: Call, history: list[dict], seed: int = 0) -> Turn:
        customer = history[-1]["text"]
        lang = langs.detect(customer)
        if self.flow_mode == "llm_flow":
            messages = prompts.llm_flow_messages(self.engine, call, history, lang)
        else:
            messages = prompts.agent_messages(self.variant, self.engine, call, history, lang)

        text, ms = self.llm.chat(messages, json_mode=True, temperature=self.temperature, seed=seed)
        out = parse_json(text)
        json_ok = out is not None and isinstance(out.get("reply"), str)
        if not json_ok:  # one retry with a reminder, as a production system would
            retry = messages + [{"role": "assistant", "content": text}, {"role": "user", "content": "Return only the JSON object."}]
            text, ms2 = self.llm.chat(retry, json_mode=True, temperature=self.temperature, seed=seed + 1)
            ms += ms2
            out = parse_json(text)
        out = out or {}
        intent = str(out.get("intent") or "provide_info")
        fields = out.get("fields") if isinstance(out.get("fields"), dict) else {}
        evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else {}
        raw = out.get("reply") if isinstance(out.get("reply"), str) else ""

        if self.flow_mode == "llm_flow":
            return self._llm_flow(call, out, intent, fields, raw, lang, json_ok, ms)

        self.engine.apply(call, intent, fields, said=customer, evidence=evidence)
        self.engine.count_turn(call)
        if call.done:
            return Turn(intent, fields, raw, self.engine.flow.closing(call.outcome, lang, call.slots), lang, json_ok, ms, closing=True)
        reply = compose(vr.for_speech(raw), self.engine.next_question(call, lang), intent)
        lang_retry = False
        if not langs.matches(customer, reply):  # language guard: one rewrite in the customer's language and script
            lang_retry = True
            ask = [{"role": "system", "content": "Rewrite the sentence for a phone call. Keep the meaning, keep it short."},
                   {"role": "user", "content": f"Rewrite in {prompts.LANG_NAMES[lang]}:\n{reply}"}]
            fixed, ms3 = self.llm.chat(ask, temperature=0.2, seed=seed, max_tokens=120)
            ms += ms3
            fixed = vr.for_speech(fixed.strip().strip('"'))
            if fixed and langs.matches(customer, fixed):
                reply = fixed
        reply, fired = vr.guard(reply, lang)
        return Turn(intent, fields, raw, reply, lang, json_ok, ms, guard=fired, lang_retry=lang_retry)

    def _llm_flow(self, call, out, intent, fields, raw, lang, json_ok, ms) -> Turn:
        for name, value in fields.items():
            if name in self.engine.flow.fields:
                clean = normalise(name, value, self.engine.flow.fields[name])
                if clean is not None:
                    call.slots[name] = clean
        nxt = out.get("next_state")
        if nxt in self.engine.flow.states and nxt != call.state:
            call.state = nxt
            if nxt not in call.states_seen:
                call.states_seen.append(nxt)
        call.agent_turns += 1
        if out.get("end_call") is True:
            call.outcome = out.get("outcome") if out.get("outcome") in OUTCOMES else "max_turns"
        elif call.agent_turns >= self.engine.flow.rules["max_turns"]:
            call.outcome = "max_turns"
        return Turn(intent, fields, raw, vr.for_speech(raw) or REPEAT[lang], lang, json_ok, ms, closing=call.done)


def run_call(agent: Agent, customer, seed: int = 0) -> dict:
    """Play one full call between the agent and a simulated customer; return the transcript and the final state."""
    call = Call()
    history = [{"speaker": "agent", "text": agent.opening(), "state": "greet"}]
    turns = []
    for i in range(agent.engine.flow.rules["max_turns"]):
        said, sim_ms = customer.reply(history, seed=seed + 100 * i)
        history.append({"speaker": "customer", "text": said})
        t = agent.respond(call, history, seed=seed + 100 * i)
        history.append({"speaker": "agent", "text": t.reply, "state": call.state})
        turns.append({
            "customer": said, "customer_lang": langs.detect(said), "intent": t.intent, "fields": t.fields,
            "raw_reply": t.raw_reply, "reply": t.reply, "reply_lang": langs.detect(t.reply), "state": call.state,
            "json_ok": t.json_ok, "ms": round(t.ms, 1), "guard": t.guard, "closing": t.closing, "lang_retry": t.lang_retry,
            "style_issues": vr.style_issues(t.reply), "violations_raw": vr.policy_violations(t.raw_reply),
            "violations_spoken": vr.policy_violations(t.reply),
        })
        if call.done:
            break
    return {"opening": agent.opening(), "turns": turns, "outcome": call.outcome or "max_turns", "slots": call.slots,
            "states_seen": call.states_seen, "rejected": [list(r) for r in call.rejected], "fixed": [list(x) for x in call.fixed]}
