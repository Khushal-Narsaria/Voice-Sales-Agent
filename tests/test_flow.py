from voiceagent.flow import Call, Engine


def engine():
    return Engine()


def test_engaging_counts_as_consent_and_moves_on():
    e, c = engine(), Call()
    e.apply(c, "provide_info", {"city": "Pune"}, said="I live in Pune", evidence={"city": "I live in Pune"})
    assert c.slots["consent"] is True and c.state == "discover" and c.slots["city"] == "Pune"


def test_all_at_once_skips_ahead_to_booking():
    e, c = engine(), Call()
    said = "Pune, flat chosen, 60 lakh loan, salaried, 95 thousand a month"
    e.apply(c, "provide_info", {"city": "Pune", "property_status": "identified", "loan_amount_lakh": 60,
                                "employment": "salaried", "monthly_income_k": 95}, said=said, evidence=None)
    assert c.state == "book" and not c.done


def test_booking_and_eligibility():
    e, c = engine(), Call()
    e.apply(c, "provide_info", {"city": "Pune", "property_status": "identified", "loan_amount_lakh": 60,
                                "employment": "salaried", "monthly_income_k": 95}, said="x 60 lakh 95 thousand")
    e.apply(c, "provide_info", {"advisor_slot": "Saturday 11 am"}, said="Saturday 11 am")
    assert c.outcome == "booked"
    c2 = Call()
    e.apply(c2, "provide_info", {"city": "Kochi", "property_status": "searching", "loan_amount_lakh": 30,
                                 "employment": "salaried", "monthly_income_k": 18}, said="30 lakh 18 thousand")
    assert c2.outcome == "not_eligible"


def test_busy_goes_to_callback_and_reads_the_time():
    e, c = engine(), Call()
    e.apply(c, "not_interested", {}, said="I'm driving, call me back tomorrow morning")
    assert c.outcome == "callback" and "tomorrow" in c.slots["callback_time"]


def test_refusal_and_wrong_number_end_the_call():
    e = engine()
    c = Call()
    e.apply(c, "not_interested", {}, said="Not interested, don't call again")
    assert c.outcome == "not_interested"
    c = Call()
    e.apply(c, "wrong_person", {}, said="Wrong number")
    assert c.outcome == "wrong_number"


def test_ungrounded_and_invalid_fields_are_rejected():
    e, c = engine(), Call(state="discover", states_seen=["greet", "discover"], slots={"consent": True})
    e.apply(c, "provide_info", {"city": "Pune", "property_status": "searching"}, said="I live in Pune",
            evidence={"city": "I live in Pune", "property_status": "we are searching"})
    assert c.slots.get("property_status") is None and c.slots["city"] == "Pune"
    c2 = Call(state="book", states_seen=["book"], slots={"consent": True, "city": "Pune", "property_status": "identified",
                                                       "loan_amount_lakh": 60, "employment": "salaried", "monthly_income_k": 95})
    e.apply(c2, "provide_info", {"advisor_slot": "message"}, said="message")
    assert c2.slots.get("advisor_slot") is None and not c2.done


def test_unit_slip_is_fixed_and_logged():
    e, c = engine(), Call(state="qualify", states_seen=["qualify"], slots={"consent": True, "city": "Mumbai", "property_status": "identified"})
    e.apply(c, "provide_info", {"loan_amount_lakh": 15}, said="about 1.5 crore", evidence={"loan_amount_lakh": "about 1.5 crore"})
    assert c.slots["loan_amount_lakh"] == 150 and c.fixed == [("loan_amount_lakh", 15.0, 150.0)]


def test_max_turns():
    e, c = engine(), Call()
    for _ in range(e.flow.rules["max_turns"]):
        e.count_turn(c)
    assert c.outcome == "max_turns"


def test_scripted_question_follows_the_state():
    e, c = engine(), Call(state="qualify", slots={"loan_amount_lakh": 50})
    assert e.next_question(c, "hinglish") == e.flow.questions["employment"]["hinglish"]
