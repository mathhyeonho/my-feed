import requests
from .base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """로컬 Ollama 서버를 사용하는 프로바이더. API 키 불필요."""

    DEFAULT_MODEL = "llama3.2"
    DEFAULT_HOST = "http://localhost:11434"

    def __init__(self, config: dict):
        super().__init__(config)
        self.model = self.model or self.DEFAULT_MODEL
        self.host = config.get("host", self.DEFAULT_HOST).rstrip("/")

    def summarize(self, title: str, content: str, url: str) -> str:
        response = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self._user_message(title, content, url)},
                ],
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
