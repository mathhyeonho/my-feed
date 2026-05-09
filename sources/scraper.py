import requests
import logging
from urllib.parse import urljoin
from .base import BaseSource, FeedItem

logger = logging.getLogger(__name__)


class ScraperSource(BaseSource):
    """
    CSS 셀렉터 기반 웹 스크래퍼 소스.
    beautifulsoup4 패키지가 필요합니다.

    config 예시:
      url: "https://example.com/blog"
      item_selector: "article"
      title_selector: "h2"
      link_selector: "a"
      content_selector: "p"
    """

    def fetch(self) -> list[FeedItem]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "ScraperSource에는 beautifulsoup4가 필요합니다: pip install beautifulsoup4"
            )

        url = self.config["url"]
        count = self.config.get("count", 10)
        headers = self.config.get("headers", {
            "User-Agent": "Mozilla/5.0 (compatible; FeedBot/1.0)"
        })

        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        item_sel = self.config.get("item_selector", "article")
        title_sel = self.config.get("title_selector", "h2, h3")
        link_sel = self.config.get("link_selector", "a")
        content_sel = self.config.get("content_selector", "p")

        items = []
        for el in soup.select(item_sel)[:count]:
            title_el = el.select_one(title_sel)
            link_el = el.select_one(link_sel)
            content_el = el.select_one(content_sel)

            title = title_el.get_text(strip=True) if title_el else "Untitled"
            link = link_el.get("href", "") if link_el else ""
            content = content_el.get_text(strip=True) if content_el else ""

            if link and not link.startswith("http"):
                link = urljoin(url, link)

            items.append(FeedItem(
                id=FeedItem.make_id(link or title),
                title=title,
                url=link,
                content=content,
                source_name=self.name,
                published_at=self._now_iso(),
            ))

        return items
