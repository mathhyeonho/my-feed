from .base import BaseLLMProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .google_provider import GoogleProvider
from .deepseek_provider import DeepSeekProvider
from .ollama_provider import OllamaProvider

LLM_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
    "deepseek": DeepSeekProvider,
    "ollama": OllamaProvider,
}


def get_provider(config: dict) -> BaseLLMProvider:
    provider = config.get("provider", "anthropic")
    cls = LLM_REGISTRY.get(provider)
    if not cls:
        raise ValueError(
            f"알 수 없는 LLM 프로바이더: '{provider}'. "
            f"사용 가능: {list(LLM_REGISTRY)}"
        )
    return cls(config)


def register_provider(name: str, cls: type[BaseLLMProvider]):
    """새 LLM 프로바이더를 런타임에 등록한다."""
    LLM_REGISTRY[name] = cls
