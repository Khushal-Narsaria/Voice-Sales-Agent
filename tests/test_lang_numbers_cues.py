from voiceagent import cues
from voiceagent.lang import detect, matches
from voiceagent.numbers import amounts, reconcile


def test_detect_three_languages():
    assert detect("I need a loan of sixty lakh") == "en"
    assert detect("Haan ji, mujhe loan chahiye") == "hinglish"
    assert detect("मुझे लोन चाहिए") == "hi"


def test_language_match_rules():
    assert matches("मुझे लोन चाहिए", "जी, बताइए")
    assert not matches("मुझे लोन चाहिए", "Sure, tell me more")
    assert matches("Haan mujhe chahiye", "Sure, which city?")
    assert not matches("Which documents do you need?", "Aapko kaunse documents chahiye hain bataiye")


def test_spoken_amounts():
    assert amounts("about 1.5 crore") == [(1.5, "crore")]
    assert amounts("dedh lakh") == [(1.5, "lakh")]
    assert amounts("मुझे २८ लाख चाहिए") == [(28.0, "lakh")]
    assert amounts("ninety five thousand a month") == [(95.0, "thousand")]
    assert amounts("ek laakh 50 thousand") == [(1.5, "lakh")]
    assert amounts("around 80k") == [(80.0, "thousand")]


def test_reconcile_fixes_unit_slips_only():
    assert reconcile("loan_amount_lakh", 15, "I need about 1.5 crore") == 150
    assert reconcile("monthly_income_k", 50, "90 lakh loan, I earn 1.5 lakh a month") == 150
    assert reconcile("loan_amount_lakh", 9, "90 lakh loan, 1.5 lakh a month") == 90
    assert reconcile("loan_amount_lakh", 60, "sixty lakh") == 60  # nothing parsed in digits: keep the model's value


def test_callback_cues_do_not_override_refusals():
    assert cues.wants_callback("I'm driving, call me back tomorrow")
    assert cues.wants_callback("kal subah baat karein")
    assert not cues.wants_callback("don't call me again, not interested")
    assert cues.refuses("mujhe loan nahi chahiye, dobara call mat karna")


def test_slot_time_and_grounding():
    assert cues.slot_time("Saturday 11 am") and cues.slot_time("शनिवार शाम") and not cues.slot_time("message")
    assert cues.grounded("flat Pune mein hai", "Haan, flat Pune mein hai ji")
    assert not cues.grounded("I am salaried", "I live in Pune")
