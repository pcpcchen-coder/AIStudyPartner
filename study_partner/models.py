"""Explicit model choices; unavailable selections never fall back to another model."""

from typing import Literal

ModelId = Literal["gpt-6-astra", "gpt-6-sol", "gpt-6-luna"]
DEFAULT_MODEL: ModelId = "gpt-6-astra"
MODELS = [
    {"id": "gpt-6-astra", "label": "GPT-6 Astra"},
    {"id": "gpt-6-sol", "label": "GPT-6 Sol"},
    {"id": "gpt-6-luna", "label": "GPT-6 Luna"},
]
