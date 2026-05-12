"""
IPO Tracker Source — KIS 마스터 파일 기반 신규상장주 탐지

해외: https://new.real.download.dws.co.kr/common/master/{val}mst.cod.zip
      탭 구분자, CP949, 24컬럼 (Symbol / Korea name / English name / Security type 등)
국내: KIS OpenAPI 인증 후 동일 다운로드 서버 (URL 미확정 — 실패 시 로그 안내)
"""
from __future__ import annotations

import io
import json
import logging
import os
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
import urllib3

from .base import BaseSource, FeedItem

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

# yfinance 내부 경고 억제 (delisted / no timezone 등 정상 처리되는 케이스)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# ── KIS 마켓 코드 (해외) ────────────────────────────────────────────────────────
# 다운로드: https://new.real.download.dws.co.kr/common/master/{code}mst.cod.zip
OVERSEAS_MARKETS: dict[str, dict] = {
    "nas": {"suffix": "",    "name": "NASDAQ", "region": "미국"},
    "nys": {"suffix": "",    "name": "NYSE",   "region": "미국"},
    "ams": {"suffix": "",    "name": "AMEX",   "region": "미국"},
    "hks": {"suffix": ".HK","name": "홍콩",    "region": "홍콩"},
    "shs": {"suffix": ".SS","name": "상해",    "region": "중국"},
    "szs": {"suffix": ".SZ","name": "심천",    "region": "중국"},
    "tse": {"suffix": ".T", "name": "도쿄",    "region": "일본"},
    "hnx": {"suffix": ".VN","name": "하노이",  "region": "베트남"},
    "hsx": {"suffix": ".VN","name": "호치민",  "region": "베트남"},
}

# 국내: KIS API 인증 필요
DOMESTIC_MARKETS: dict[str, dict] = {
    "KOSPI":  {"suffix": ".KS", "name": "KOSPI",  "region": "한국"},
    "KOSDAQ": {"suffix": ".KQ", "name": "KOSDAQ", "region": "한국"},
}

ALL_MARKETS: dict[str, dict] = {**OVERSEAS_MARKETS, **DOMESTIC_MARKETS}

_DOWNLOAD_BASE = "https://new.real.download.dws.co.kr/common/master"
_KIS_API_BASE  = "https://openapi.koreainvestment.com:9443"

_DOMESTIC_URLS = {
    "KOSPI":  "kospi_code.mst.zip",
    "KOSDAQ": "kosdaq_code.mst.zip",
}

# .cod 파일 컬럼 (탭 구분, 24컬럼)
_COD_COLS = [
    "national_code", "exchange_id", "exchange_code", "exchange_name",
    "symbol", "realtime_symbol", "kr_name", "en_name",
    "sec_type",       # 1:Index 2:Stock 3:ETP(ETF) 4:Warrant
    "currency", "float_pos", "data_type", "base_price",
    "bid_size", "ask_size", "mkt_start", "mkt_end",
    "dr_yn", "dr_country", "sector_code", "index_yn",
    "tick_type", "cat_code", "tick_detail",
]


class IPOTrackerSource(BaseSource):
    """KIS 마스터 파일로 종목 목록을 받아 yfinance로 신규상장 여부를 판별한다."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._force:               bool  = config.get("_force", False)
        self._ipo_days:            int   = config.get("ipo_days", 21)
        self._max_listing_age_days:int   = config.get("max_listing_age_days", 45)
        self._cache_days:          int   = config.get("cache_days", 30)
        self._markets:             list  = config.get("markets", list(ALL_MARKETS))
        self._batch_size:          int   = config.get("batch_size", 50)
        self._batch_delay:         float = config.get("batch_delay", 0.5)

        self._app_key    = config.get("kis_app_key")    or os.environ.get("KIS_APP_KEY",    "")
        self._app_secret = config.get("kis_app_secret") or os.environ.get("KIS_APP_SECRET", "")

        cache_dir = Path(__file__).parent.parent / "data"
        cache_dir.mkdir(exist_ok=True)
        self._cache_path = cache_dir / "ipo_cache.json"
        self._cache: dict[str, dict] = self._load_cache()
        self._token: Optional[str]   = None

    # ── 캐시 ──────────────────────────────────────────────────────────────────

    def _load_cache(self) -> dict:
        if self._cache_path.exists():
            try:
                return json.loads(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        self._cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _is_cached_non_ipo(self, ticker: str) -> bool:
        if self._force:
            return False
        entry = self._cache.get(ticker)
        if not entry or entry.get("is_ipo", True):
            return False
        try:
            ts = datetime.fromisoformat(entry["checked_at"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) < ts + timedelta(days=self._cache_days)
        except Exception:
            return False

    def _set_cache(self, ticker: str, *, is_ipo: bool) -> None:
        self._cache[ticker] = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "is_ipo": is_ipo,
        }

    # ── KIS 인증 ──────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        if self._token:
            return self._token
        if not self._app_key or not self._app_secret:
            raise RuntimeError(
                "KIS API 인증정보 없음. "
                "KIS_APP_KEY / KIS_APP_SECRET 환경변수를 설정하세요."
            )
        resp = requests.post(
            f"{_KIS_API_BASE}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        logger.info("KIS 인증 토큰 발급 완료")
        return self._token

    # ── 마스터 파일 다운로드 / 파싱 ───────────────────────────────────────────

    @staticmethod
    def _parse_domestic_mst(raw: bytes) -> list[dict]:
        """
        국내 .mst 고정폭 파싱 (CP949).
        바이트 0-5: 단축코드(6자리)  9-20: ISIN  21-60: 한글명
        KR7(보통주) / KR8(우선주) ISIN 만 반환.
        """
        stocks: list[dict] = []
        for line in raw.split(b"\n"):
            line = line.rstrip(b"\r")
            if len(line) < 21:
                continue
            code = line[0:6].decode("cp949", errors="replace").strip()
            isin = line[9:21].decode("cp949", errors="replace").strip()
            if not code.isdigit():          # 펀드/ETF 등 비숫자 코드 제외
                continue
            if not (isin.startswith("KR7") or isin.startswith("KR8")):
                continue                    # 한국 보통주/우선주만
            kr_name = (
                line[21:61].decode("cp949", errors="replace").strip()
                if len(line) > 21 else ""
            )
            stocks.append({"code": code, "kr_name": kr_name, "en_name": ""})
        return stocks

    @staticmethod
    def _parse_cod(raw: bytes) -> list[dict]:
        """
        KIS .cod 파일 파싱 (탭 구분, CP949).
        Security type == 2 (Stock) 만 반환.
        반환: [{"code": str, "kr_name": str, "en_name": str}]
        """
        import pandas as pd

        df = pd.read_table(
            io.BytesIO(raw),
            sep="\t",
            encoding="cp949",
            header=None,
            dtype=str,
        ).fillna("")

        # 파일 컬럼 수에 맞게 헤더 슬라이스
        df.columns = _COD_COLS[: len(df.columns)]

        # 주식(type 2)만 필터 — 인덱스(1), ETF(3), 워런트(4) 제외
        if "sec_type" in df.columns:
            df = df[df["sec_type"].str.strip() == "2"]

        return [
            {
                "code":    str(row.get("symbol", "")).strip(),
                "kr_name": str(row.get("kr_name", "")).strip(),
                "en_name": str(row.get("en_name", "")).strip(),
            }
            for row in df.to_dict("records")
            if str(row.get("symbol", "")).strip()
        ]

    def _download_overseas_master(self, market: str) -> list[dict]:
        url = f"{_DOWNLOAD_BASE}/{market}mst.cod.zip"
        logger.info(f"  마스터 다운로드: {url}")
        resp = requests.get(url, timeout=30, verify=False)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            inner = zf.namelist()[0]
            with zf.open(inner) as f:
                raw = f.read()
        stocks = self._parse_cod(raw)
        logger.info(f"  [{market}] {len(stocks)}종목 (주식)")
        return stocks

    def _download_domestic_master(self, market: str) -> list[dict]:
        filename = _DOMESTIC_URLS[market]
        url = f"{_DOWNLOAD_BASE}/{filename}"
        logger.info(f"  마스터 다운로드: {url}")
        resp = requests.get(url, timeout=30, verify=False)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                raw = f.read()
        stocks = self._parse_domestic_mst(raw)
        logger.info(f"  [{market}] {len(stocks)}종목 (보통주+우선주)")
        return stocks

    @staticmethod
    def _normalize_code(code: str) -> str:
        """KIS 종목코드 → yfinance 호환 형식. '/' → '-' (우선주/클래스 구분자)."""
        return code.replace("/", "-")

    def _download_master(self, market: str) -> list[dict]:
        if market in DOMESTIC_MARKETS:
            return self._download_domestic_master(market)
        return self._download_overseas_master(market)

    # ── yfinance OHLCV 배치 체크 ──────────────────────────────────────────────

    def _check_batch(self, codes: list[str], suffix: str) -> dict[str, Optional[dict]]:
        """
        codes 배치에 대해 yfinance 2개월 OHLCV 일괄 조회.
        반환: {full_ticker: ipo_info_or_None}
        """
        import yfinance as yf

        end   = datetime.now()
        start = end - timedelta(days=62)
        tickers = [f"{c}{suffix}" for c in codes]

        try:
            hist = yf.download(
                tickers,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            logger.debug(f"yfinance 배치 오류: {e}")
            return {t: None for t in tickers}

        results: dict[str, Optional[dict]] = {}
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    closes = hist["Close"].dropna()
                else:
                    if ticker not in hist.columns.get_level_values(0):
                        results[ticker] = None
                        continue
                    closes = hist[ticker]["Close"].dropna()

                n = len(closes)
                if n == 0:
                    results[ticker] = None
                elif n < self._ipo_days:
                    first_dt = closes.index[0].to_pydatetime().replace(tzinfo=None)
                    # 첫 거래일이 최근 max_listing_age_days 이내여야 신규상장
                    # → 상폐 종목은 first_date가 오래전이라 제외됨 (휴일 영향 없음)
                    if (datetime.now() - first_dt).days <= self._max_listing_age_days:
                        results[ticker] = {
                            "trading_days": n,
                            "first_date":   closes.index[0].strftime("%Y-%m-%d"),
                            "last_close":   float(closes.iloc[-1]),
                        }
                    else:
                        results[ticker] = None  # 오래된 종목이 상폐된 케이스
                else:
                    results[ticker] = None

            except Exception as e:
                logger.debug(f"[{ticker}] 처리 오류: {e}")
                results[ticker] = None

        return results

    # ── 피드 아이템 생성 ──────────────────────────────────────────────────────

    def _make_item(
        self, stock: dict, ticker: str, ipo: dict, mkt_name: str, region: str
    ) -> FeedItem:
        kr = stock.get("kr_name", "").strip()
        en = stock.get("en_name", "").strip()
        display = kr or en or stock["code"].strip()

        lines = [f"종목명: {display}"]
        if en and kr:
            lines.append(f"영문명: {en}")
        lines += [
            f"티커: {ticker}",
            f"시장: {mkt_name} ({region})",
            f"첫 거래일: {ipo['first_date']}",
            f"거래일수: {ipo['trading_days']}일",
            f"최근 종가: {ipo['last_close']:,.4f}",
        ]

        return FeedItem(
            id=FeedItem.make_id(ticker),
            title=f"[신규상장] {display} ({ticker}) - {mkt_name}",
            url=f"https://finance.yahoo.com/quote/{ticker}",
            content="\n".join(lines),
            source_name=self.name,
            published_at=datetime.now(timezone.utc).isoformat(),
            tags=["신규상장", "IPO", region, mkt_name],
            extra={},
        )

    # ── 메인 fetch ────────────────────────────────────────────────────────────

    def fetch(self) -> list[FeedItem]:
        try:
            from tqdm import tqdm as _tqdm
        except ImportError:
            _tqdm = None

        all_items: list[FeedItem] = []

        market_iter = (
            _tqdm(self._markets, desc="전체 시장", unit="시장", position=0)
            if _tqdm else self._markets
        )

        for market_code in market_iter:
            mkt_cfg = ALL_MARKETS.get(market_code)
            if not mkt_cfg:
                logger.warning(f"알 수 없는 시장 코드: {market_code}")
                continue

            suffix   = mkt_cfg["suffix"]
            mkt_name = mkt_cfg["name"]
            region   = mkt_cfg["region"]

            logger.info(f"[IPO] {mkt_name} ({region})")

            try:
                stocks = self._download_master(market_code)
            except Exception as e:
                logger.error(f"  [{mkt_name}] 마스터 파일 실패: {e}")
                continue

            to_check = [
                s for s in stocks
                if not self._is_cached_non_ipo(
                    f"{self._normalize_code(s['code'].strip())}{suffix}"
                )
            ]
            skipped = len(stocks) - len(to_check)
            logger.info(f"  캐시 skip: {skipped} | 확인 대상: {len(to_check)}")

            found: list[FeedItem] = []
            pbar = (
                _tqdm(
                    total=len(to_check),
                    desc=f"  {mkt_name}",
                    unit="종목",
                    leave=False,
                    position=1,
                )
                if _tqdm else None
            )

            for i in range(0, len(to_check), self._batch_size):
                batch  = to_check[i : i + self._batch_size]
                codes  = [self._normalize_code(s["code"].strip()) for s in batch]
                results = self._check_batch(codes, suffix)

                for stock, code in zip(batch, codes):
                    ticker = f"{code}{suffix}"
                    ipo    = results.get(ticker)
                    if ipo:
                        self._set_cache(ticker, is_ipo=True)
                        found.append(self._make_item(stock, ticker, ipo, mkt_name, region))
                    else:
                        self._set_cache(ticker, is_ipo=False)

                if pbar:
                    pbar.update(len(batch))
                    pbar.set_postfix(IPO=len(found))

                if self._batch_delay > 0:
                    time.sleep(self._batch_delay)

            if pbar:
                pbar.close()

            logger.info(f"  [{mkt_name}] 신규상장 {len(found)}종목")
            all_items.extend(found)
            self._save_cache()

        return all_items
