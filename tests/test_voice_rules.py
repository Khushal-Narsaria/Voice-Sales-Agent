from voiceagent import voice_rules as vr


def test_for_speech_strips_markdown_emoji_links():
    assert vr.for_speech("**Sure!** 😊 see https://x.y\n- item") == "Sure! see item"


def test_style_issues():
    assert vr.style_issues("Which city is the property in?") == []
    assert "too_long" in vr.style_issues(" ".join(["word"] * 40))
    assert "unspeakable_number" in vr.style_issues("You need ₹50,00,000")


def test_policy_and_guard():
    assert vr.policy_violations("Your interest rate will be 8.5%") == ["rate_promise"]
    assert vr.policy_violations("Please share the OTP") == ["sensitive_ask"]
    assert "approval_promise" in vr.policy_violations("Approval is guaranteed")
    text, fired = vr.guard("Rate is just 7 percent", "hi")
    assert fired == ["rate_promise"] and text == vr.DEFLECT["hi"]
    text, fired = vr.guard("Bata dijiye OTP", "hinglish")
    assert text == vr.NO_SENSITIVE["hinglish"]
    assert vr.policy_violations(vr.NO_SENSITIVE["en"]) == []  # the safety line itself is not a violation
