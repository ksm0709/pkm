from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ModelInfo:
    id: str
    provider: str
    context_window: str
    input_cost_1m: str
    output_cost_1m: str
    score: int
    description: str


@dataclass(frozen=True)
class ProviderModelSource:
    provider: str
    env_key: str
    litellm_attrs: tuple[str, ...]
    normalise: Callable[[str], str]


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

_CHAT_MODEL_MODES = {"chat"}


def _identity_model_id(model_id: str) -> str:
    return model_id


def _gemini_model_id(model_id: str) -> str:
    if model_id.startswith("gemini/"):
        return model_id
    if model_id.startswith("gemini-"):
        return f"gemini/{model_id}"
    return model_id


def _anthropic_model_id(model_id: str) -> str:
    if model_id.startswith("anthropic/"):
        return model_id
    if model_id.startswith("claude-"):
        return f"anthropic/{model_id}"
    return model_id


PROVIDER_MODEL_SOURCES: tuple[ProviderModelSource, ...] = (
    ProviderModelSource(
        provider="Google",
        env_key="GEMINI_API_KEY",
        litellm_attrs=("gemini_models",),
        normalise=_gemini_model_id,
    ),
    ProviderModelSource(
        provider="OpenAI",
        env_key="OPENAI_API_KEY",
        litellm_attrs=("open_ai_chat_completion_models",),
        normalise=_identity_model_id,
    ),
    ProviderModelSource(
        provider="Anthropic",
        env_key="ANTHROPIC_API_KEY",
        litellm_attrs=("anthropic_models",),
        normalise=_anthropic_model_id,
    ),
)


def get_available_models() -> list[ModelInfo]:
    """Return best models sorted by score descending."""
    return sorted(BEST_MODELS, key=lambda m: m.score, reverse=True)


def _fallback_provider_models(provider: str) -> list[str]:
    return [model.id for model in get_available_models() if model.provider == provider]


def _litellm_model_cost(litellm: Any, model_id: str) -> dict[str, Any]:
    model_cost = getattr(litellm, "model_cost", {}) or {}
    if model_id in model_cost:
        return model_cost[model_id] or {}
    if "/" in model_id:
        provider, raw_model_id = model_id.split("/", 1)
        if raw_model_id in model_cost:
            return model_cost[raw_model_id] or {}
        provider_cost_id = f"{provider}/{raw_model_id}"
        return model_cost.get(provider_cost_id) or {}
    return {}


def _is_agent_chat_model(litellm: Any, model_id: str) -> bool:
    cost = _litellm_model_cost(litellm, model_id)
    mode = cost.get("mode")
    if mode is None:
        return True
    return mode in _CHAT_MODEL_MODES


def _provider_models_from_litellm(source: ProviderModelSource) -> list[str]:
    import litellm

    model_ids: set[str] = set()
    for attr in source.litellm_attrs:
        raw_values = getattr(litellm, attr, None)
        if not raw_values:
            continue
        for raw_model_id in raw_values:
            if not isinstance(raw_model_id, str) or not raw_model_id.strip():
                continue
            model_id = source.normalise(raw_model_id.strip())
            if _is_agent_chat_model(litellm, model_id):
                model_ids.add(model_id)
    return sorted(model_ids)


def _rank_model_ids(model_ids: list[str]) -> list[str]:
    best_rank = {model.id: index for index, model in enumerate(get_available_models())}
    return sorted(
        dict.fromkeys(model_ids),
        key=lambda model_id: (
            model_id not in best_rank,
            best_rank.get(model_id, len(best_rank)),
            model_id,
        ),
    )


def get_connected_model_options(env: dict[str, str] | None = None) -> list[str]:
    """Return all chat model IDs for API-key-connected tiny-agent providers."""
    env_keys = collect_api_keys() if env is None else env
    model_ids: list[str] = []

    for source in PROVIDER_MODEL_SOURCES:
        if not env_keys.get(source.env_key):
            continue
        try:
            provider_models = _provider_models_from_litellm(source)
        except Exception:
            provider_models = []
        model_ids.extend(provider_models or _fallback_provider_models(source.provider))

    return _rank_model_ids(model_ids)


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
