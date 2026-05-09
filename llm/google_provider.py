import os
import google.generativeai as genai
from .base import BaseLLMProvider


class GoogleProvider(BaseLLMProvider):
    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, config: dict):
        super().__init__(config)
        self.model = self.model or self.DEFAULT_MODEL
        api_key = config.get("api_key") or os.environ.get("GOOGLE_API_KEY", "")
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=self.system_prompt,
        )

    def summarize(self, title: str, content: str, url: str) -> str:
        response = self._client.generate_content(
            self._user_message(title, content, url)
        )
        return response.text
