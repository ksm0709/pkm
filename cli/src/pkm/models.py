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
        "gpt-5.4-nano",
        "OpenAI",
        "400K",
        "$0.20",
        "$1.25",
        96,
        "Best OpenAI value for PKM: note extraction, ranking, summarization, and cheap RAG.",
    ),
    ModelInfo(
        "gpt-5-mini",
        "OpenAI",
        "400K",
        "$0.25",
        "$2.00",
        93,
        "Higher-quality OpenAI fallback for well-defined note synthesis with strong cost control.",
    ),
    ModelInfo(
        "gpt-5-nano",
        "OpenAI",
        "400K",
        "$0.05",
        "$0.40",
        91,
        "Cheapest OpenAI reasoning fallback for simple summaries, tagging, and classification.",
    ),
    ModelInfo(
        "gpt-5.4-mini",
        "OpenAI",
        "400K",
        "$0.75",
        "$4.50",
        89,
        "Premium OpenAI mini for harder vault synthesis and tool-heavy workflows.",
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


def validate_model_environment(model_id: str) -> dict:
    """Validate model API keys while treating blank *_API_KEY values as absent."""
    blank_api_keys = {
        k: v
        for k, v in os.environ.items()
        if k.endswith("_API_KEY") and not v.strip()
    }
    try:
        for key in blank_api_keys:
            os.environ.pop(key, None)

        import litellm

        return litellm.validate_environment(model_id)
    except Exception:
        return {"keys_in_environment": False, "missing_keys": []}
    finally:
        os.environ.update(blank_api_keys)


def _is_valid(model_id: str) -> bool:
    try:
        return validate_model_environment(model_id).get("keys_in_environment", True)
    except Exception:
        return False
