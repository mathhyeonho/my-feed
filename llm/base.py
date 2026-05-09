from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "")
        self.language = config.get("language", "ko")
        self.system_prompt = config.get("system_prompt") or self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        return (
            f"당신은 콘텐츠 요약 전문가입니다. "
            f"주어진 기사의 핵심 내용을 {self.language}로 정리합니다.\n"
            "- 첫 줄: 한 줄 요약\n"
            "- 핵심 포인트 3~5개를 불릿 포인트(- )로 정리\n"
            "- 마크다운 형식 사용"
        )

    @abstractmethod
    def summarize(self, title: str, content: str, url: str) -> str:
        pass

    def _user_message(self, title: str, content: str, url: str) -> str:
        return f"제목: {title}\nURL: {url}\n\n내용:\n{content[:3000]}"
