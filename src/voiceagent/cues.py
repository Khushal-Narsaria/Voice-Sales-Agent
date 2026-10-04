"""Deterministic checks on the customer's own words, used as a safety net around the model.

- grounded(): a field the model extracted must come with a quote that really appears in the customer's message.
- wants_callback() / refuses(): keyword cues for "call me later" and "don't call me" in English, Hinglish and Hindi.
- slot_time(): an advisor or callback slot must mention a day or a time, otherwise it is not a usable booking.
"""
import re

PUNCT = re.compile(r"[^\wऀ-ॿ]+")

CALLBACK = re.compile(  # explicit "call me later" phrases only: bare time words ("subah", "शाम को") also answer slot questions
    r"call (me )?(back|later)|\blater\b|busy|driving|in a meeting|meeting mein|baad mein|baad me|abhi busy|abhi baat nahi|"
    r"abhi nahi kar|kal (subah |shaam )?(baat|call|phone)|baat karein|baat karna|बाद में|व्यस्त|अभी बात नहीं|"
    r"कल (सुबह |शाम )?(बात|फोन|कॉल)",
    re.I,
)
REFUSE = re.compile(
    r"not interested|don'?t call|do not call|stop calling|no need|nahi chahiye|nahin chahiye|interest nahi|dobara call mat|"
    r"call mat|mat karna|ज़रूरत नहीं|जरूरत नहीं|नहीं चाहिए|दोबारा कॉल मत|कॉल न करें|रुचि नहीं",
    re.I,
)
DAY_OR_TIME = re.compile(
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|today|tomorrow|tonight|morning|afternoon|evening|"
    r"somvar|mangalvar|budhvar|guruvar|shukravar|shanivar|ravivar|itwar|aaj|kal|parso|subah|dopahar|shaam|raat|"
    r"सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार|आज|कल|परसों|सुबह|दोपहर|शाम|रात|"
    r"\d{1,2}\s*(:\d{2})?\s*(am|pm|baje|बजे)|\d{1,2}\s*(o'?clock)|noon|baje|बजे",
    re.I,
)


ENUM_CUES = {
    "property_status": re.compile(
        r"final|chosen|choose|found|select|decided|identified|booked|already (have|got|bought)|mil gay|le liya|pasand|"
        r"search|looking|dhoond|dhund|khoj|not yet|nahi mila|still|dekh rah|abhi tak|"
        r"तय|मिल गया|मिल गई|चुन|पसंद|ले लिया|फाइनल|ढूंढ|ढूँढ|खोज|नहीं मिला|देख रह|अभी तक", re.I),
    "employment": re.compile(
        r"salar|job|employ|work(ing)? (at|in|for)|company|bank|government|govt|naukri|service|staff|clerk|manager|engineer|"
        r"teacher|nurse|officer|business|shop|dukaan|dukan|own|self|freelanc|practice|studio|kaam|"
        r"नौकरी|वेतन|कर्मचारी|कंपनी|सरकारी|बैंक|व्यवसाय|व्यापार|दुकान|अपना|खुद|काम|शिक्षक|क्लर्क", re.I),
}


def supported(name: str, value, said: str) -> bool:
    """Fallback when the model gave a field without a quote: is the value plausibly in the customer's words?"""
    from .numbers import amounts
    if name in ("loan_amount_lakh", "monthly_income_k"):
        return bool(amounts(said)) or bool(re.search(r"\d", said))
    if name in ("advisor_slot", "callback_time"):
        return slot_time(said)
    if name in ENUM_CUES:
        return bool(ENUM_CUES[name].search(said))
    if name == "city":
        v = str(value).lower()
        return v in said.lower() or any(t in said.lower() for t in _tokens(v)) or bool(re.search(r"[\u0900-\u097F]", said))
    return True


def _tokens(text: str) -> list[str]:
    return [t for t in PUNCT.sub(" ", str(text).lower()).split() if t]


def grounded(quote: str, said: str) -> bool:
    """True if most words of the model's quote occur in what the customer said (tolerates small slips)."""
    q, s = _tokens(quote), set(_tokens(said))
    if not q:
        return False
    return sum(t in s for t in q) / len(q) >= 0.6


def wants_callback(text: str) -> bool:
    return bool(CALLBACK.search(text)) and not refuses(text)


def refuses(text: str) -> bool:
    return bool(REFUSE.search(text))


def slot_time(text: str) -> bool:
    return bool(DAY_OR_TIME.search(str(text)))
