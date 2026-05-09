from openai import OpenAI
from .base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, config: dict):
        super().__init__(config)
        self.model = self.model or self.DEFAULT_MODEL
        self.client = OpenAI()  # OPENAI_API_KEY 환경변수 자동 참조

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
