from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib


@dataclass
class FeedItem:
    id: str
    title: str
    url: str
    content: str
    source_name: str
    published_at: str          # ISO 8601
    summary: Optional[str] = None
    tags: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # 차트 데이터 등 추가 페이로드

    @staticmethod
    def make_id(key: str) -> str:
        return hashlib.md5(key.encode("utf-8")).hexdigest()


class BaseSource(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name", "Unknown Source")

    @abstractmethod
    def fetch(self) -> list[FeedItem]:
        """소스에서 아이템을 가져온다. FeedItem 리스트를 반환."""
        pass

    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat()
