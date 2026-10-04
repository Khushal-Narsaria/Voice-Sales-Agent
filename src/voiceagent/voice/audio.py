"""Audio helpers: decode to 16 kHz mono float32, mix noise at a target signal-to-noise ratio, write WAV."""
import wave
from pathlib import Path

import numpy as np

RATE = 16_000


def load(path: Path) -> np.ndarray:
    """Decode any audio file to 16 kHz mono float32 in [-1, 1]."""
    import av  # imported here so the rest of the package (and CI) does not need it

    container = av.open(str(path))
    resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    chunks = []
    for frame in container.decode(audio=0):
        for out in resampler.resample(frame):
            chunks.append(out.to_ndarray().reshape(-1))
    for out in resampler.resample(None):
        chunks.append(out.to_ndarray().reshape(-1))
    container.close()
    return (np.concatenate(chunks).astype(np.float32) / 32768.0) if chunks else np.zeros(0, np.float32)


def babble(sources: list[np.ndarray], length: int, rng: np.random.Generator) -> np.ndarray:
    """Background chatter: several other utterances overlaid at random offsets, plus a little white noise."""
    noise = np.zeros(length, np.float32)
    for src in sources:
        if len(src) == 0:
            continue
        reps = np.tile(src, int(np.ceil(length / len(src))) + 1)
        start = rng.integers(0, len(src))
        noise += reps[start:start + length]
    noise += rng.normal(0, 0.05 * (np.std(noise) or 1.0), length).astype(np.float32)
    return noise


def mix(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Scale `noise` so that speech power / noise power = snr_db, add, and keep the result in [-1, 1]."""
    p_speech = float(np.mean(speech ** 2)) or 1e-9
    p_noise = float(np.mean(noise ** 2)) or 1e-9
    scaled = noise * np.sqrt(p_speech / (p_noise * 10 ** (snr_db / 10)))
    out = speech + scaled
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.95 if peak > 1 else out).astype(np.float32)


def save_wav(samples: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
