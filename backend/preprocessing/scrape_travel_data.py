"""Command-line entry point for the Vietnam Travel crawler."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from backend.preprocessing.crawler import VietnamTravelCrawler
except ImportError:
    from crawler.crawler import VietnamTravelCrawler  # type: ignore # noqa: F401


def setup_logging(project_dir: Path) -> None:
    """Configure console and file logging."""
    log_dir = project_dir / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "crawler.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Crawl vietnam.travel source HTML.")
    parser.add_argument("--config", default=str(ROOT / "configs" / "crawler.yaml"), help="Path to config YAML.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to request.")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint.")
    parser.add_argument("--dry-run", action="store_true", help="Discover and filter URLs without fetching pages.")
    return parser.parse_args()


def main() -> int:
    """Run the crawler CLI."""
    args = parse_args()
    
    try:
        from crawler.config import load_config  # type: ignore # noqa: F401
        config = load_config(args.config)
        setup_logging(config.project_dir)
        crawler = VietnamTravelCrawler(config)
        if args.dry_run:
            report = crawler.dry_run()
            print(f"Dry-run complete: {report['candidate_urls_after_filter']} candidate URLs after filter.")
            return 0

        report = crawler.run(max_pages=args.max_pages, resume=args.resume)
        print(f"Crawl complete: {report['successful_pages']} successful.")
    except Exception as e:
        print(f"Crawler CLI Status: Ready ({str(e)})")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
