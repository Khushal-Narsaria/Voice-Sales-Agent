import json

from voiceagent import prompts
from voiceagent.agent import Agent, compose, run_call
from voiceagent.llm import ScriptedModel
from voiceagent.metrics import score


def out(intent, fields=None, reply="", evidence=None):
    return json.dumps({"intent": intent, "fields": fields or {}, "evidence": evidence or {}, "reply": reply})


class ScriptedCustomer:
    def __init__(self, lines):
        self.lines = list(lines)

    def reply(self, history, seed=0):
        return self.lines.pop(0), 1.0


PERSONA = {"id": "t1", "expected_outcome": "booked", "truth": {"city": "pune", "property_status": "identified",
           "loan_amount_lakh": 60, "employment": "salaried", "monthly_income_k": 95, "advisor_day": "saturday"}}


def test_full_call_books_and_uses_fixed_closing():
    llm = ScriptedModel([
        out("provide_info", {"city": "Pune", "property_status": "identified"}, "Great, Pune.",
            {"city": "flat in Pune", "property_status": "already chosen"}),
        out("provide_info", {"loan_amount_lakh": 60, "employment": "salaried", "monthly_income_k": 95}, "Thank you.",
            {"loan_amount_lakh": "60 lakh", "employment": "salaried", "monthly_income_k": "95 thousand"}),
        out("provide_info", {"advisor_slot": "Saturday 11 am"}, "Done.", {"advisor_slot": "Saturday 11 am"}),
    ])
    customer = ScriptedCustomer(["Yes, I have already chosen a flat in Pune",
                                 "I need 60 lakh, I am salaried and earn 95 thousand a month",
                                 "Saturday 11 am"])
    call = run_call(Agent(llm, variant="persona"), customer)
    assert call["outcome"] == "booked"
    assert call["turns"][-1]["closing"] and "Saturday 11 am" in call["turns"][-1]["reply"]
    s = score(call, PERSONA)
    assert s["outcome_correct"] and s["field_accuracy"] == 1.0 and s["violations"] == 0


def test_rate_promise_is_never_spoken():
    llm = ScriptedModel([out("question", {}, "The interest rate is 8.2% for you.")])
    agent = Agent(llm, variant="persona")
    from voiceagent.flow import Call
    c = Call(state="qualify", slots={"consent": True}, states_seen=["qualify"])
    t = agent.respond(c, [{"speaker": "agent", "text": "Hi"}, {"speaker": "customer", "text": "What is the interest rate?"}])
    assert t.guard == ["rate_promise"] and "8.2" not in t.reply


def test_compose_replaces_stale_questions():
    assert compose("Okay, Pune. How much loan?", "Have you chosen a property?", "provide_info") == "Okay, Pune. Have you chosen a property?"


def test_bad_json_is_retried_then_falls_back():
    llm = ScriptedModel(["not json", out("provide_info", {"city": "Pune"}, "Okay.", {"city": "Pune"})])
    from voiceagent.flow import Call
    agent = Agent(llm, variant="few_shot")
    c = Call()
    t = agent.respond(c, [{"speaker": "agent", "text": "Hi"}, {"speaker": "customer", "text": "Pune"}])
    assert t.json_ok is False and c.slots["city"] == "Pune" and len(llm.calls) == 2


def test_prompt_variants_differ_as_designed():
    from voiceagent.flow import Call, Engine
    e, c = Engine(), Call()
    h = [{"speaker": "agent", "text": "Hi"}, {"speaker": "customer", "text": "Haan ji boliye"}]
    zero = prompts.agent_messages("zero_shot", e, c, h, "hinglish")
    few = prompts.agent_messages("few_shot", e, c, h, "hinglish")
    persona = prompts.agent_messages("persona", e, c, h, "hinglish")
    assert "Examples from OTHER calls" not in zero[0]["content"] and "Examples from OTHER calls" in few[0]["content"]
    assert "Priya" in persona[0]["content"] and "Voice rules" in persona[0]["content"]
    assert persona[-1]["content"].endswith("Reply language: Hinglish (Hindi and English mixed, written in Roman script).")
