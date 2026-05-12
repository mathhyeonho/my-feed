from .base import BaseSource, FeedItem
from .rss import RSSSource
from .rest_api import RestAPISource
from .scraper import ScraperSource
from .highcharts import HighchartsSource
from .ipo_tracker import IPOTrackerSource

SOURCE_REGISTRY: dict[str, type[BaseSource]] = {
    "rss": RSSSource,
    "api": RestAPISource,
    "scraper": ScraperSource,
    "highcharts": HighchartsSource,
    "ipo_tracker": IPOTrackerSource,
}


def get_source(config: dict) -> BaseSource:
    source_type = config.get("type", "rss")
    cls = SOURCE_REGISTRY.get(source_type)
    if not cls:
        raise ValueError(
            f"알 수 없는 소스 타입: '{source_type}'. "
            f"사용 가능: {list(SOURCE_REGISTRY)}"
        )
    return cls(config)


def register_source(name: str, cls: type[BaseSource]):
    """새 소스 타입을 런타임에 등록한다."""
    SOURCE_REGISTRY[name] = cls
