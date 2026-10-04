"""Speech-to-text with Whisper (faster-whisper, int8 on CPU), language detected automatically."""
import time

import numpy as np

_MODELS: dict = {}


def model(size: str = "small"):
    if size not in _MODELS:
        from faster_whisper import WhisperModel
        _MODELS[size] = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=4)
    return _MODELS[size]


def transcribe(samples: np.ndarray, size: str = "small", language: str | None = None) -> dict:
    """Return {"text", "language", "language_prob", "seconds"} for 16 kHz mono audio."""
    start = time.perf_counter()
    segments, info = model(size).transcribe(samples, language=language, beam_size=1, vad_filter=False)
    text = " ".join(s.text.strip() for s in segments).strip()
    return {"text": text, "language": info.language, "language_prob": round(info.language_probability, 3),
            "seconds": time.perf_counter() - start}
