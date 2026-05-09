import feedparser
import logging
from datetime import datetime
from .base import BaseSource, FeedItem

logger = logging.getLogger(__name__)


class RSSSource(BaseSource):
    def fetch(self) -> list[FeedItem]:
        url = self.config["url"]
        count = self.config.get("count", 10)

        feed = feedparser.parse(url)
        items = []

        for entry in feed.entries[:count]:
            content = ""
            if hasattr(entry, "content"):
                content = entry.content[0].value
            elif hasattr(entry, "summary"):
                content = entry.summary

            published = self._now_iso()
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    pass

            link = entry.get("link", entry.get("id", ""))
            items.append(FeedItem(
                id=FeedItem.make_id(link),
                title=entry.get("title", "Untitled"),
                url=link,
                content=content,
                source_name=self.name,
                published_at=published,
            ))

        return items
