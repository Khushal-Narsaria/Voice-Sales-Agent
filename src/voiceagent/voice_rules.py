"""Rules for text that will be spoken by a text-to-speech engine, and compliance guardrails for a sales call.

Voice-first replies must be short, contain no markdown, emojis or links, and write amounts the way people
say them ("50 lakh", not "₹50,00,000"). A sales agent must also never promise an interest rate or approval,
and never ask for an OTP, PIN, card or ID number on a call.
"""
import re

MAX_WORDS = 35
MAX_SENTENCES = 3

MARKDOWN = re.compile(r"(\*\*|__|`|^\s*[-*•]\s|^\s*#+\s|\[[^\]]*\]\([^)]*\))", re.M)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
URL = re.compile(r"https?://|www\.", re.I)
UNSPEAKABLE_NUMBER = re.compile(r"₹|\d{1,3}(,\d{2,3}){2,}")
SENTENCE_END = re.compile(r"[.!?।]+(\s|$)")

RATE_PROMISE = re.compile(
    r"\d+(\.\d+)?\s*(%|percent|per cent|प्रतिशत|pratishat|pratishat)|"
    r"(interest|byaj|ब्याज)\s*(rate)?\s*(is|hai|है|will be|hoga|होगा)\s*(just|only|sirf|केवल)?\s*\d",
    re.I,
)
GUARANTEE = re.compile(r"guarantee|guaranteed|pakka approve|100% approv|ज़रूर मंज़ूर|पक्का मंज़ूर|definitely (get|be) approved", re.I)
SENSITIVE_ASK = re.compile(
    r"\b(otp|cvv|pin|password|aadhaar number|aadhar number|pan number|card number|account number)\b|ओटीपी|पासवर्ड|आधार नंबर",
    re.I,
)

DEFLECT = {
    "en": "The exact rate depends on your profile, and our loan advisor will share it on the free call.",
    "hinglish": "Exact rate aapki profile par depend karta hai, woh hamare loan advisor free call par batayenge.",
    "hi": "सटीक ब्याज दर आपकी प्रोफ़ाइल पर निर्भर करती है, वह हमारे लोन सलाहकार मुफ़्त कॉल पर बताएँगे।",
}
NO_SENSITIVE = {
    "en": "For your safety, please never share an OTP, PIN or card number on a call.",
    "hinglish": "Aapki safety ke liye, call par kabhi OTP, PIN ya card number share mat kijiye.",
    "hi": "आपकी सुरक्षा के लिए, कॉल पर कभी OTP, PIN या कार्ड नंबर साझा न करें।",
}
SAFE_LINES = set(DEFLECT.values()) | set(NO_SENSITIVE.values())


def for_speech(text: str) -> str:
    """Strip what a TTS engine would read out badly: markdown, emojis, links and stray whitespace."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*\*|__|`)", "", text)
    text = re.sub(r"^\s*([-*•]|#+)\s*", "", text, flags=re.M)
    text = EMOJI.sub("", text)
    text = re.sub(r"(https?://|www\.)\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> int:
    return len(text.split())


def sentences(text: str) -> int:
    return max(1, len(SENTENCE_END.findall(text.strip())) or 1)


def style_issues(text: str) -> list[str]:
    """Voice-style problems in an agent reply (empty list = fine to speak)."""
    issues = []
    if words(text) > MAX_WORDS:
        issues.append("too_long")
    if sentences(text) > MAX_SENTENCES:
        issues.append("too_many_sentences")
    if MARKDOWN.search(text):
        issues.append("markdown")
    if EMOJI.search(text):
        issues.append("emoji")
    if URL.search(text):
        issues.append("link")
    if UNSPEAKABLE_NUMBER.search(text):
        issues.append("unspeakable_number")
    return issues


def policy_violations(text: str) -> list[str]:
    if text in SAFE_LINES:
        return []
    found = []
    if RATE_PROMISE.search(text):
        found.append("rate_promise")
    if GUARANTEE.search(text):
        found.append("approval_promise")
    if SENSITIVE_ASK.search(text):
        found.append("sensitive_ask")
    return found


def guard(text: str, lang: str) -> tuple[str, list[str]]:
    """Replace a reply that breaks a compliance rule with a safe line. Returns (text, rules that fired)."""
    lang = lang if lang in DEFLECT else "en"
    fired = policy_violations(text)
    if not fired:
        return text, []
    if "sensitive_ask" in fired:
        return NO_SENSITIVE[lang], fired
    return DEFLECT[lang], fired
