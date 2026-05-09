import re
import logging
from datetime import datetime
from .base import BaseSource, FeedItem

logger = logging.getLogger(__name__)


class HighchartsSource(BaseSource):
    """
    Highcharts SVG가 포함된 HTML에서 차트 데이터를 추출하는 소스.

    config 예시:
      name: "NASDAQ 100 Forward PE"
      type: "highcharts"
      html_file: "data/nasdaq_pe.html"   # 브라우저에서 저장한 HTML 파일
      source_url: "https://en.macromicro.me/series/23955/nasdaq-100-pe"

      # Playwright로 자동 렌더링 (pip install playwright && playwright install)
      # url: "https://en.macromicro.me/series/23955/nasdaq-100-pe"
    """

    def fetch(self) -> list[FeedItem]:
        html = self._load_html()
        chart = self._extract(html)
        if not chart:
            return []

        today = datetime.utcnow().strftime("%Y-%m-%d")
        item = FeedItem(
            id=FeedItem.make_id(self.name + today),
            title=f"{chart['title']} ({today})",
            url=self.config.get("source_url", ""),
            content="",
            source_name=self.name,
            published_at=self._now_iso(),
        )
        item.extra = chart  # type: line_chart
        return [item]

    # ── HTML 로딩 ────────────────────────────────────────────────────────────

    def _load_html(self) -> str:
        html_file = self.config.get("html_file")
        if html_file:
            with open(html_file, "r", encoding="utf-8") as f:
                return f.read()

        url = self.config.get("url")
        if url:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    page = browser.new_page()
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    html = page.content()
                    browser.close()
                    return html
            except ImportError:
                raise ImportError(
                    "url 옵션에는 playwright가 필요합니다: "
                    "pip install playwright && playwright install chromium"
                )

        raise ValueError("html_file 또는 url 중 하나를 config에 지정해야 합니다.")

    # ── SVG 파싱 ─────────────────────────────────────────────────────────────

    def _extract(self, html: str) -> dict:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "HighchartsSource에는 beautifulsoup4가 필요합니다: pip install beautifulsoup4"
            )

        soup = BeautifulSoup(html, "html.parser")
        svg = soup.find("svg", class_="highcharts-root")
        if not svg:
            logger.error("highcharts-root SVG를 찾지 못했습니다.")
            return {}

        # ── 플롯 영역 크기 ───────────────────────────────────────────────────
        bg = svg.find("rect", class_="highcharts-plot-background")
        if not bg:
            return {}
        plot_x = float(bg.get("x", 0))
        plot_y = float(bg.get("y", 0))
        plot_w = float(bg.get("width", 0))
        plot_h = float(bg.get("height", 0))

        # ── X축 눈금 → 연도 매핑 ────────────────────────────────────────────
        x_group = svg.find("g", class_="highcharts-xaxis-labels")
        x_cal = []
        for t in (x_group.find_all("text") if x_group else []):
            try:
                x_cal.append({"svg_x": float(t["x"]), "val": float(t.get_text().strip())})
            except (ValueError, KeyError):
                pass
        x_cal.sort(key=lambda p: p["svg_x"])
        if len(x_cal) < 2:
            logger.error("X축 레이블 파싱 실패")
            return {}

        x_scale = (x_cal[-1]["svg_x"] - x_cal[0]["svg_x"]) / (x_cal[-1]["val"] - x_cal[0]["val"])
        x_ref_svg = x_cal[0]["svg_x"]
        x_ref_val = x_cal[0]["val"]

        # ── Y축 최솟값/최댓값 ────────────────────────────────────────────────
        y_group = svg.find("g", class_="highcharts-yaxis-labels")
        y_vals = []
        for t in (y_group.find_all("text") if y_group else []):
            try:
                y_vals.append(float(t.get_text().strip()))
            except ValueError:
                pass
        if not y_vals:
            return {}
        y_min, y_max = min(y_vals), max(y_vals)

        # ── path 데이터 파싱 ─────────────────────────────────────────────────
        # path 좌표는 translate(plot_x, plot_y) 기준
        # y=0 → y_max, y=plot_h → y_min
        graph = svg.find("path", class_="highcharts-graph")
        if not graph:
            return {}

        coords = re.findall(r"[ML]\s*([\d.]+)\s+([\d.]+)", graph.get("d", ""))
        data = []
        for px, py in coords:
            path_x, path_y = float(px), float(py)
            svg_x = path_x + plot_x
            x_val = x_ref_val + (svg_x - x_ref_svg) / x_scale
            y_val = y_max - (path_y / plot_h) * (y_max - y_min)
            data.append({"x": round(x_val, 3), "y": round(y_val, 2)})

        # ── 차트 제목 (legend에서 추출) ──────────────────────────────────────
        title = self.name
        legend = svg.find("g", class_="highcharts-legend-item")
        if legend:
            t = legend.find("text")
            if t:
                title = t.get_text(strip=True)

        logger.info(f"  차트 데이터 {len(data)}개 포인트 추출 완료")
        return {"type": "line_chart", "title": title, "data": data}
