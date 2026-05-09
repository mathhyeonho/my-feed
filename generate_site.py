import json
import re
import calendar
import logging
import markdown as md_lib
from datetime import datetime
from pathlib import Path
from email.utils import formatdate
from sources.base import FeedItem

logger = logging.getLogger(__name__)


class SiteGenerator:
    def __init__(self, site_config: dict, output_dir: str = "docs"):
        self.config = site_config
        self.out = Path(output_dir)
        self.posts_dir = self.out / "posts"
        self.db_path = self.out / "posts_db.json"

        self.out.mkdir(parents=True, exist_ok=True)
        self.posts_dir.mkdir(exist_ok=True)

    # ── DB ──────────────────────────────────────────────────────────────────

    def _load_db(self) -> dict:
        if self.db_path.exists():
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"posts": [], "seen_ids": []}

    def _save_db(self, db: dict):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2, default=str)

    # ── Entry point ──────────────────────────────────────────────────────────

    def generate(self, new_items: list[FeedItem]):
        db = self._load_db()
        seen = set(db.get("seen_ids", []))

        # 차트 아이템은 매번 재생성 (데이터가 계속 갱신됨)
        chart_items = [it for it in new_items if it.extra.get("type") == "line_chart"]
        regular_items = [it for it in new_items if not it.extra.get("type") == "line_chart"]
        truly_new = [it for it in regular_items if it.id not in seen]

        added = 0

        # 일반 아이템: 새 것만 추가
        for item in truly_new:
            slug = self._make_slug(item)
            self._write_post(item, slug)
            db["posts"].insert(0, self._post_record(item, slug))
            seen.add(item.id)
            added += 1

        # 차트 아이템: 항상 HTML 재생성, DB는 upsert
        for item in chart_items:
            slug = self._chart_slug(item)
            self._write_post(item, slug)
            record = self._post_record(item, slug)
            existing = next((p for p in db["posts"] if p["id"] == item.id), None)
            if existing:
                existing.update(record)
            else:
                db["posts"].insert(0, record)
                seen.add(item.id)
                added += 1

        if added:
            db["seen_ids"] = list(seen)
            max_posts = self.config.get("max_posts", 500)
            db["posts"] = db["posts"][:max_posts]
            logger.info(f"{added}개 추가/갱신. 총 {len(db['posts'])}개")
        else:
            logger.info("새 아이템 없음.")

        self._write_index(db["posts"])
        self._write_rss(db["posts"])
        self._save_db(db)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @property
    def _site_url(self) -> str:
        return self.config["url"].rstrip("/")

    def _post_url(self, post: dict) -> str:
        return f"{self._site_url}/posts/{post['slug']}.html"

    def _post_record(self, item: FeedItem, slug: str) -> dict:
        return {
            "id": item.id,
            "slug": slug,
            "title": item.title,
            "url": item.url,
            "content": item.content,
            "summary": item.summary or "",
            "source_name": item.source_name,
            "published_at": item.published_at,
            "added_at": datetime.utcnow().isoformat(),
            "extra": item.extra,
        }

    def _chart_slug(self, item: FeedItem) -> str:
        """차트는 URL이 바뀌지 않도록 날짜 없이 고정 슬러그 사용."""
        safe = re.sub(r"[^\w\s-]", "", item.title.lower())
        safe = re.sub(r"[\s_]+", "-", safe).strip("-")[:50]
        return f"chart-{safe}-{item.id[:6]}"

    def _make_slug(self, item: FeedItem) -> str:
        date = item.published_at[:10] if item.published_at else datetime.utcnow().strftime("%Y-%m-%d")
        safe = re.sub(r"[^\w\s-]", "", item.title.lower())
        safe = re.sub(r"[\s_]+", "-", safe).strip("-")[:50]
        return f"{date}-{safe}-{item.id[:6]}"

    def _fmt_date(self, iso: str) -> str:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%Y년 %m월 %d일")
        except Exception:
            return iso[:10]

    def _rfc2822(self, iso: str) -> str:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return formatdate(calendar.timegm(dt.timetuple()))
        except Exception:
            return formatdate()

    @staticmethod
    def _esc(text: str) -> str:
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    # ── Writers ──────────────────────────────────────────────────────────────

    def _write_post(self, item: FeedItem, slug: str):
        summary_html = md_lib.markdown(item.summary) if item.summary else ""
        (self.posts_dir / f"{slug}.html").write_text(
            self._post_html(item, summary_html, item.extra), encoding="utf-8"
        )

    def _write_index(self, posts: list[dict]):
        (self.out / "index.html").write_text(
            self._index_html(posts[:100]), encoding="utf-8"
        )

    def _write_rss(self, posts: list[dict]):
        (self.out / "feed.xml").write_text(
            self._rss_xml(posts[:50]), encoding="utf-8"
        )

    # ── CSS (공통) ────────────────────────────────────────────────────────────

    def _css(self) -> str:
        return """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
       background: #f4f4f5; color: #18181b; line-height: 1.75; }
a { color: inherit; }
.wrap { max-width: 800px; margin: 0 auto; padding: 0 20px; }
.site-header { background: #09090b; color: #fff; padding: 26px 0; }
.site-header .inner { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.site-header h1 { font-size: 1.4rem; font-weight: 700; }
.site-header p  { color: #a1a1aa; font-size: .88rem; margin-top: 3px; }
.rss-btn { flex-shrink: 0; color: #f97316; border: 1px solid #f97316;
           padding: 5px 14px; border-radius: 6px; text-decoration: none; font-size: .82rem; }
.feed { padding: 28px 0; }
.card { background: #fff; border-radius: 10px; padding: 22px 24px;
        margin-bottom: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.meta { display: flex; gap: 8px; align-items: center; font-size: .78rem; margin-bottom: 9px; }
.tag  { background: #eff6ff; color: #2563eb; padding: 2px 9px; border-radius: 20px; font-weight: 600; }
.date { color: #a1a1aa; }
.card h2 { font-size: 1.05rem; line-height: 1.5; margin-bottom: 9px; }
.card h2 a { text-decoration: none; color: #18181b; }
.card h2 a:hover { color: #2563eb; }
.excerpt { color: #52525b; font-size: .9rem; margin-bottom: 13px; }
.actions { display: flex; gap: 8px; }
.btn { padding: 5px 13px; border-radius: 6px; font-size: .8rem; text-decoration: none; display: inline-block; }
.btn-primary { background: #18181b; color: #fff; }
.btn-outline  { border: 1px solid #d4d4d8; color: #71717a; }
.btn-outline:hover { background: #f4f4f5; }
.post-wrap { padding: 28px 0; }
.back { display: inline-block; color: #71717a; text-decoration: none; margin-bottom: 18px; font-size: .88rem; }
.post-box { background: #fff; border-radius: 10px; padding: 30px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.post-box h1 { font-size: 1.4rem; line-height: 1.4; margin-bottom: 14px; }
.orig-link { display: inline-block; color: #2563eb; text-decoration: none; font-size: .88rem; margin-bottom: 22px; }
.orig-link:hover { text-decoration: underline; }
.summary-box { background: #f0f9ff; border-left: 4px solid #0ea5e9;
               border-radius: 0 8px 8px 0; padding: 16px 20px; }
.summary-box h2 { color: #0369a1; font-size: .9rem; margin-bottom: 10px; font-weight: 600; }
.summary-box ul { padding-left: 18px; }
.summary-box li { margin-bottom: 5px; font-size: .93rem; }
.summary-box p  { font-size: .93rem; margin-bottom: 7px; }
.site-footer { text-align: center; color: #a1a1aa; font-size: .8rem; padding: 28px 0; }
.site-footer a { color: #71717a; }
.chart-badge { background: #f0fdf4; color: #16a34a; padding: 2px 9px;
               border-radius: 20px; font-size: .78rem; font-weight: 600; }
.chart-section { margin-top: 24px; }
.chart-section canvas { max-height: 380px; }
@media (max-width: 560px) {
    .site-header .inner { flex-direction: column; align-items: flex-start; }
}
"""

    # ── Templates ─────────────────────────────────────────────────────────────

    def _index_html(self, posts: list[dict]) -> str:
        s = self.config
        su = self._site_url

        cards = ""
        for p in posts:
            pu = self._post_url(p)
            is_chart = p.get("extra", {}).get("type") == "line_chart"

            if is_chart:
                body = '<span class="chart-badge">📈 차트</span>'
            else:
                raw = (p.get("summary") or p.get("content", ""))[:200]
                excerpt = re.sub(r"<[^>]+>", "", raw)
                body = (
                    f"<p class='excerpt'>{self._esc(excerpt)}"
                    f"{'…' if len(raw) >= 200 else ''}</p>"
                    if excerpt else ""
                )

            orig_btn = (
                f'<a href="{self._esc(p.get("url","#"))}" class="btn btn-outline" '
                f'target="_blank" rel="noopener">원문 ↗</a>'
                if p.get("url") else ""
            )

            cards += f"""
        <article class="card">
          <div class="meta">
            <span class="tag">{self._esc(p.get('source_name',''))}</span>
            <span class="date">{self._fmt_date(p.get('added_at', p.get('published_at','')))}</span>
          </div>
          <h2><a href="{pu}">{self._esc(p.get('title',''))}</a></h2>
          {body}
          <div class="actions">
            <a href="{pu}" class="btn btn-primary">자세히 보기</a>
            {orig_btn}
          </div>
        </article>"""

        if not cards:
            cards = '<p style="color:#a1a1aa;text-align:center;padding:48px 0">아직 수집된 포스트가 없습니다.</p>'

        return f"""<!DOCTYPE html>
<html lang="{s.get('language','ko')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{self._esc(s['title'])}</title>
  <link rel="alternate" type="application/rss+xml" title="{self._esc(s['title'])}" href="{su}/feed.xml">
  <style>{self._css()}</style>
</head>
<body>
  <header class="site-header">
    <div class="wrap inner">
      <div>
        <h1>{self._esc(s['title'])}</h1>
        <p>{self._esc(s.get('description',''))}</p>
      </div>
      <a href="{su}/feed.xml" class="rss-btn">RSS 구독</a>
    </div>
  </header>
  <main class="wrap feed">{cards}</main>
  <footer class="site-footer"><a href="{su}/feed.xml">RSS</a> · 자동 수집 피드</footer>
</body>
</html>"""

    def _post_html(self, item: FeedItem, summary_html: str, extra: dict = None) -> str:
        s = self.config
        su = self._site_url

        summary_block = (
            f'<div class="summary-box"><h2>AI 요약</h2>{summary_html}</div>'
            if summary_html else ""
        )

        chart_block = ""
        if extra and extra.get("type") == "line_chart":
            chart_block = self._chart_block(extra)

        orig_link = (
            f'<a href="{self._esc(item.url)}" class="orig-link" target="_blank" rel="noopener">원문 읽기 ↗</a>'
            if item.url else ""
        )

        return f"""<!DOCTYPE html>
<html lang="{s.get('language','ko')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{self._esc(item.title)} — {self._esc(s['title'])}</title>
  <style>{self._css()}</style>
</head>
<body>
  <header class="site-header">
    <div class="wrap">
      <a href="{su}" style="color:#fff;opacity:.75;text-decoration:none">← {self._esc(s['title'])}</a>
    </div>
  </header>
  <main class="wrap post-wrap">
    <a href="{su}" class="back">← 목록으로</a>
    <div class="post-box">
      <div class="meta">
        <span class="tag">{self._esc(item.source_name)}</span>
        <span class="date">{self._fmt_date(item.published_at)}</span>
      </div>
      <h1>{self._esc(item.title)}</h1>
      {orig_link}
      {summary_block}
      {chart_block}
    </div>
  </main>
  <footer class="site-footer"><a href="{su}/feed.xml">RSS</a> · 자동 수집 피드</footer>
</body>
</html>"""

    def _chart_block(self, extra: dict) -> str:
        data_json = json.dumps(extra["data"])
        title_js = extra.get("title", "").replace('"', '\\"')
        return f"""<div class="chart-section">
  <canvas id="feedChart"></canvas>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
(function() {{
  const raw = {data_json};
  function fmtX(val) {{
    const totalMonths = Math.round(val * 12);
    const yr = Math.floor(totalMonths / 12);
    const mo = (totalMonths % 12) + 1;
    return yr + "-" + String(mo).padStart(2, "0");
  }}
  new Chart(document.getElementById("feedChart"), {{
    type: "scatter",
    data: {{
      datasets: [{{
        label: "{title_js}",
        data: raw.map(p => ({{ x: p.x, y: p.y }})),
        borderColor: "#2563eb",
        backgroundColor: "rgba(37,99,235,0.07)",
        borderWidth: 2,
        pointRadius: 2,
        tension: 0.3,
        fill: true,
        showLine: true,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: true }} }},
      scales: {{
        x: {{
          type: "linear",
          ticks: {{
            maxTicksLimit: 12,
            maxRotation: 45,
            callback: fmtX,
          }}
        }},
        y: {{ beginAtZero: false }}
      }}
    }}
  }});
}})();
</script>"""

    def _rss_xml(self, posts: list[dict]) -> str:
        s = self.config
        su = self._site_url

        items = ""
        for p in posts:
            pu = self._post_url(p)
            desc = (p.get("summary") or p.get("content", ""))[:1000]
            items += f"""
  <item>
    <title>{self._esc(p.get('title',''))}</title>
    <link>{pu}</link>
    <guid isPermaLink="true">{pu}</guid>
    <pubDate>{self._rfc2822(p.get('added_at', p.get('published_at','')))}</pubDate>
    <category>{self._esc(p.get('source_name',''))}</category>
    <description><![CDATA[{desc}]]></description>
  </item>"""

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{self._esc(s['title'])}</title>
    <link>{su}</link>
    <description>{self._esc(s.get('description',''))}</description>
    <language>{s.get('language','ko')}</language>
    <lastBuildDate>{formatdate()}</lastBuildDate>
    <atom:link href="{su}/feed.xml" rel="self" type="application/rss+xml"/>
    {items}
  </channel>
</rss>"""
