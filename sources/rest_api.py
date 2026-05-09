import requests
import logging
from .base import BaseSource, FeedItem

logger = logging.getLogger(__name__)


class RestAPISource(BaseSource):
    """
    REST API에서 데이터를 수집하는 소스.

    config 예시:
      url: "https://api.example.com/posts"
      method: GET
      headers: { Authorization: "Bearer TOKEN" }
      params: { page: 1, limit: 10 }
      items_path: "data.items"   # 응답 JSON에서 배열까지의 점-경로
      id_field: "id"
      title_field: "title"
      url_field: "link"
      content_field: "body"
      date_field: "created_at"   # (선택)
    """

    def fetch(self) -> list[FeedItem]:
        url = self.config["url"]
        method = self.config.get("method", "GET").upper()
        headers = self.config.get("headers", {})
        params = self.config.get("params", {})
        body = self.config.get("body")
        count = self.config.get("count", 10)

        resp = requests.request(
            method, url,
            headers=headers,
            params=params,
            json=body or None,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # 점-경로로 배열 위치 탐색
        items_path = self.config.get("items_path", "")
        for key in (items_path.split(".") if items_path else []):
            data = data[key]
        if not isinstance(data, list):
            data = [data]

        id_field = self.config.get("id_field", "id")
        title_field = self.config.get("title_field", "title")
        url_field = self.config.get("url_field", "url")
        content_field = self.config.get("content_field", "content")
        date_field = self.config.get("date_field", "")

        items = []
        for entry in data[:count]:
            raw_id = str(entry.get(id_field, entry.get("id", "")))
            link = str(entry.get(url_field, ""))
            published = self._now_iso()
            if date_field and date_field in entry:
                published = str(entry[date_field])

            items.append(FeedItem(
                id=FeedItem.make_id(raw_id or link),
                title=str(entry.get(title_field, "Untitled")),
                url=link,
                content=str(entry.get(content_field, "")),
                source_name=self.name,
                published_at=published,
            ))

        return items
