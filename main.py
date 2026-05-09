import sys
import json
import yaml
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

INTERVAL_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def load_config() -> dict:
    with open(ROOT / "config.yml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_schedule(output_dir: str) -> dict:
    path = ROOT / output_dir / "source_schedule.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_schedule(schedule: dict, output_dir: str):
    path = ROOT / output_dir / "source_schedule.json"
    path.write_text(json.dumps(schedule, indent=2, default=str), encoding="utf-8")


def is_due(src_cfg: dict, schedule: dict) -> bool:
    """마지막 실행으로부터 interval 이상 지났으면 True."""
    name = src_cfg.get("name", "")
    interval = src_cfg.get("interval", "daily")
    days = INTERVAL_DAYS.get(interval, 1)
    last_run = schedule.get(name)
    if not last_run:
        return True
    elapsed = (datetime.utcnow() - datetime.fromisoformat(last_run)).total_seconds()
    return elapsed >= days * 86400


def main():
    config = load_config()
    output_dir = config.get("output", {}).get("dir", "docs")

    from sources import get_source
    from generate_site import SiteGenerator

    schedule = load_schedule(output_dir)

    # 1. 데이터 수집 (소스별 interval 체크)
    logger.info("=== 데이터 수집 시작 ===")
    all_items = []
    for src_cfg in config.get("sources", []):
        name = src_cfg.get("name", "?")
        interval = src_cfg.get("interval", "daily")

        if not is_due(src_cfg, schedule):
            logger.info(f"  [{name}] 스킵 (interval: {interval}, 아직 실행 불필요)")
            continue

        try:
            source = get_source(src_cfg)
            items = source.fetch()
            all_items.extend(items)
            schedule[name] = datetime.utcnow().isoformat()
            logger.info(f"  [{name}] {len(items)}개 수집")
        except Exception as e:
            logger.error(f"  [{name}] 수집 실패: {e}")

    save_schedule(schedule, output_dir)
    logger.info(f"총 {len(all_items)}개 수집 완료")

    # 2. LLM 요약 (선택)
    llm_cfg = config.get("llm", {})
    if llm_cfg.get("enabled", False) and all_items:
        from llm import get_provider
        provider = get_provider(llm_cfg)
        max_n = llm_cfg.get("max_items_per_run", 10)
        logger.info(f"=== LLM 요약 ({llm_cfg.get('provider')}/{provider.model}) ===")
        for i, item in enumerate(all_items[:max_n]):
            try:
                item.summary = provider.summarize(item.title, item.content, item.url)
                logger.info(f"  [{i+1}/{max_n}] {item.title[:50]}")
            except Exception as e:
                logger.error(f"  LLM 오류 '{item.title[:40]}': {e}")

    # 3. 사이트 생성
    logger.info("=== 사이트 생성 ===")
    generator = SiteGenerator(config["site"], output_dir)
    generator.generate(all_items)

    logger.info("=== 완료 ===")


if __name__ == "__main__":
    main()
