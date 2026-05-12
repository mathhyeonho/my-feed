"""
IPO 트래커 단독 테스트 스크립트.
Usage:
  python test_ipo.py              # 해외(AMEX)만, 캐시 사용
  python test_ipo.py --force      # 해외(AMEX)만, 캐시 무시
  python test_ipo.py --market NASD KOSPI  # 지정 시장
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sources.ipo_tracker import IPOTrackerSource

ALL_MARKETS = ["nas", "nys", "ams", "hks", "shs", "szs", "tse", "hnx", "hsx", "KOSPI", "KOSDAQ"]

parser = argparse.ArgumentParser()
parser.add_argument("--force",  action="store_true")
parser.add_argument("--all",    action="store_true", help="전체 시장 테스트")
parser.add_argument("--market", nargs="+", default=["ams"])
args = parser.parse_args()

if args.all:
    args.market = ALL_MARKETS

src = IPOTrackerSource({
    "name": "IPO Test",
    "markets": args.market,
    "ipo_days": 21,
    "cache_days": 30,
    "batch_size": 50,
    "batch_delay": 0.3,
    "_force": args.force,
})

items = src.fetch()

print(f"\n{'='*50}")
print(f"발견된 신규상장: {len(items)}종목")
for item in items:
    print(f"  {item.title}")
    print(f"    {item.content.splitlines()[2] if len(item.content.splitlines()) > 2 else ''}")
