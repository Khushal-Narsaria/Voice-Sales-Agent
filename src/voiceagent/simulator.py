"""Simulated customers: an open-source model role-plays a persona so whole calls can be tested without a phone line."""
import json
import re
from pathlib import Path

from .prompts import customer_messages

PERSONAS = Path(__file__).resolve().parents[2] / "data" / "personas.json"
ROLE_LEAK = re.compile(r"^(customer|agent|priya|me)\s*:\s*", re.I)


def load_personas(path: Path = PERSONAS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


class Customer:
    def __init__(self, persona: dict, llm, temperature: float = 0.7):
        self.persona, self.llm, self.temperature = persona, llm, temperature

    def reply(self, history: list[dict], seed: int = 0) -> tuple[str, float]:
        text, ms = self.llm.chat(customer_messages(self.persona, history), temperature=self.temperature, seed=seed, max_tokens=80)
        text = ROLE_LEAK.sub("", text.strip().strip('"').splitlines()[0] if text.strip() else "")
        return text or "Haan?", ms
