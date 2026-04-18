from dataclasses import dataclass
from typing import List


@dataclass
class ModelInfo:
    id: str
    provider: str
    context_window: str
    input_cost_1m: str
    output_cost_1m: str
    score: int
    description: str


BEST_MODELS: List[ModelInfo] = [
    ModelInfo(
        "gemini/gemini-3.1-flash-lite-preview",
        "Google",
        "1M+",
        "$0.25",
        "$1.50",
        95,
        "Huge context, great for large vaults.",
    ),
    ModelInfo(
        "gpt-5.4-mini",
        "OpenAI",
        "400K",
        "$0.75",
        "$4.50",
        90,
        "Current OpenAI default. Stable JSON and tool calling.",
    ),
    ModelInfo(
        "gpt-4o-mini",
        "OpenAI",
        "128K",
        "$0.15",
        "$0.60",
        85,
        "Reliable fallback for OpenAI. Fast and cheapest OpenAI.",
    ),
    ModelInfo(
        "claude-4.5-haiku-20251022",
        "Anthropic",
        "200K",
        "$1.00",
        "$5.00",
        80,
        "Premium Lite tier. Highest quality logic but more expensive.",
    ),
    ModelInfo(
        "claude-3-5-haiku-20241022",
        "Anthropic",
        "200K",
        "$0.80",
        "$4.00",
        75,
        "Fast legacy Anthropic model.",
    ),
]


def get_available_models() -> List[ModelInfo]:
    """Return best models sorted by score descending."""
    return sorted(BEST_MODELS, key=lambda m: m.score, reverse=True)


def resolve_auto_models() -> List[str]:
    import litellm

    valid_models = []
    for m in get_available_models():
        try:
            val = litellm.validate_environment(m.id)
            if val.get("keys_in_environment", True):
                valid_models.append(m.id)
        except Exception:
            pass

    if not valid_models:
        valid_models.append(get_available_models()[0].id)
    return valid_models
