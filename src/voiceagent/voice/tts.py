"""Text-to-speech with gTTS, cached on disk by a hash of (text, voice).

Hindi in Devanagari uses the Hindi voice; English and romanised Hinglish use the Indian-English voice, which reads
Roman-script Hindi far better than the Hindi voice does.
"""
import hashlib
import time
from pathlib import Path

from gtts import gTTS

VOICES = {"hi": ("hi", "co.in"), "en": ("en", "co.in"), "hinglish": ("en", "co.in"), "en-us": ("en", "com")}


def speak(text: str, lang: str, out_dir: Path) -> tuple[Path, float]:
    """Synthesize `text`; return (mp3 path, seconds spent; 0 when cached)."""
    voice, tld = VOICES.get(lang, VOICES["en"])
    key = hashlib.sha1(f"{voice}|{tld}|{text}".encode()).hexdigest()[:16]
    path = out_dir / f"{key}.mp3"
    if path.exists():
        return path, 0.0
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    for attempt in range(3):
        try:
            gTTS(text=text, lang=voice, tld=tld).save(str(path))
            break
        except Exception:  # network hiccup: retry
            if attempt == 2:
                raise
            time.sleep(2)
    return path, time.perf_counter() - start
