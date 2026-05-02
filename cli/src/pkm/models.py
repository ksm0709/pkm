import os
from dataclasses import dataclass


@dataclass
class ModelInfo:
    id: str
    provider: str
    context_window: str
    input_cost_1m: str
    output_cost_1m: str
    score: int
    description: str


BEST_MODELS: list[ModelInfo] = [
    ModelInfo(
        "gemini/gemini-3-flash-preview",
        "Google",
        "1M+",
        "$0.00",
        "$0.00",
        97,
        "Gemini 3 Flash on Google AI Studio. Supports thinking_level.",
    ),
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
        "anthropic/claude-4.5-haiku-20251022",
        "Anthropic",
        "200K",
        "$1.00",
        "$5.00",
        80,
        "Premium Lite tier. Highest quality logic but more expensive.",
    ),
    ModelInfo(
        "anthropic/claude-3-5-haiku-20241022",
        "Anthropic",
        "200K",
        "$0.80",
        "$4.00",
        75,
        "Fast legacy Anthropic model.",
    ),
]


def get_available_models() -> list[ModelInfo]:
    """Return best models sorted by score descending."""
    return sorted(BEST_MODELS, key=lambda m: m.score, reverse=True)


def resolve_auto_models() -> list[str]:
    return [m.id for m in get_available_models() if _is_valid(m.id)]


def collect_api_keys() -> dict[str, str]:
    """Return non-empty API keys from the current environment."""
    return {
        k: v
        for k, v in os.environ.items()
        if k.endswith("_API_KEY") and v.strip()
    }


def resolve_model_candidates(preferred_model: str | None = None) -> list[str]:
    """Return runtime fallback candidates for configured/default model selection."""
    auto_models = resolve_auto_models()
    if not preferred_model or preferred_model == "auto":
        return auto_models

    if not _is_valid(preferred_model):
        return auto_models

    return [preferred_model] + [m for m in auto_models if m != preferred_model]


def _is_valid(model_id: str) -> bool:
    blank_api_keys = {
        k: v
        for k, v in os.environ.items()
        if k.endswith("_API_KEY") and not v.strip()
    }
    try:
        for key in blank_api_keys:
            os.environ.pop(key, None)

        import litellm

        return litellm.validate_environment(model_id).get("keys_in_environment", True)
    except Exception:
        return False
    finally:
        os.environ.update(blank_api_keys)
