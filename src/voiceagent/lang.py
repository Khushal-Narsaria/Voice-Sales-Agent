"""Language of a short utterance: Hindi in Devanagari ("hi"), romanised Hindi mixed with English ("hinglish"), or English ("en").

Indian sales calls switch between the three all the time, and a voice agent should answer in the customer's mix.
This is a fast rule-based detector, good enough for one-line call turns (tested in tests/test_lang.py).
"""
import re

# Common romanised Hindi words. English words that look the same ("me", "to", "the") are left out on purpose.
HINGLISH_WORDS = {
    "haan", "han", "haa", "nahi", "nahin", "nai", "kya", "kyu", "kyun", "kaise", "kab", "kahan", "kitna", "kitne", "kitni",
    "mera", "meri", "mere", "mujhe", "main", "mai", "hum", "humein", "aap", "aapka", "aapki", "aapke", "apna", "apni",
    "hai", "hain", "tha", "thi", "ho", "hoon", "hu", "raha", "rahi", "rahe", "karna", "karo", "karein", "kar", "karke",
    "chahiye", "chahta", "chahti", "lena", "dena", "abhi", "baad", "kal", "parso", "subah", "shaam", "raat", "dopahar",
    "accha", "acha", "theek", "thik", "bilkul", "ji", "jee", "bhai", "lakh", "lakhs", "crore", "hazaar", "hazar",
    "naukri", "khud", "dhanda", "dukaan", "bas", "matlab", "lekin", "aur", "par", "pe", "se", "ka", "ki", "ke", "ko",
    "mein", "wala", "wali", "baat", "koi", "kuch", "sab", "bahut", "zyada", "kam", "ghar", "flat", "ab", "phir", "fir",
    "batao", "bataiye", "boliye", "samjha", "samjhi", "dobara", "mat", "shukriya", "dhanyavaad", "namaste",
}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LETTER = re.compile(r"[A-Za-zऀ-ॿ]")
WORD = re.compile(r"[a-z]+")


def detect(text: str) -> str:
    letters = LETTER.findall(text)
    if not letters:
        return "en"
    if len(DEVANAGARI.findall(text)) / len(letters) > 0.5:
        return "hi"
    words = WORD.findall(text.lower())
    if not words:
        return "en"
    hindi = sum(w in HINGLISH_WORDS for w in words)
    return "hinglish" if hindi >= 2 or hindi / len(words) >= 0.25 else "en"


def matches(customer: str, reply: str) -> bool:
    """Does the agent's reply suit the customer's language?

    Devanagari must be answered in Devanagari. Romanised Hindi may be answered in Hinglish or plain English
    (both are natural on a call). English should not get a Hindi reply.
    """
    c, r = detect(customer), detect(reply)
    if c == "hi":
        return r == "hi"
    if c == "hinglish":
        return r in ("hinglish", "en")
    return r == "en"
