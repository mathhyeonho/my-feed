import os
from openai import OpenAI
from .base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek은 OpenAI 호환 API를 사용한다."""

    DEFAULT_MODEL = "deepseek-chat"
    BASE_URL = "https://api.deepseek.com"

    def __init__(self, config: dict):
        super().__init__(config)
        self.model = self.model or self.DEFAULT_MODEL
        api_key = config.get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
        self.client = OpenAI(api_key=api_key, base_url=self.BASE_URL)

    def summarize(self, title: str, content: str, url: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self._user_message(title, content, url)},
            ],
        )
        return response.choices[0].message.content
