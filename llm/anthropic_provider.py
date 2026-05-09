import anthropic
from .base import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, config: dict):
        super().__init__(config)
        self.model = self.model or self.DEFAULT_MODEL
        self.client = anthropic.Anthropic()

    def summarize(self, title: str, content: str, url: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},  # 프롬프트 캐싱으로 비용 절감
            }],
            messages=[{"role": "user", "content": self._user_message(title, content, url)}],
        )
        return response.content[0].text
