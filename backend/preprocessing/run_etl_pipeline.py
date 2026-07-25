"""End-to-End Data Preprocessing & ETL Pipeline Orchestrator.

Sequentially executes:
1. Crawling step: Discovers and crawls raw articles from vietnam.travel.
2. Semantic Cleaning step: Strips CTA noise, demotes paragraph headings, outputs clean JSON.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.preprocessing.semantic_cleaner import clean_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("run_etl_pipeline")


def run_pipeline(
    raw_input_path: Path,
    clean_output_path: Path,
    run_crawler_step: bool = False,
    max_pages: int | None = None,
) -> dict:
    """Run full ETL Preprocessing Pipeline."""
    logger.info("==================================================")
    logger.info("🚀 STARTING VIETNAM TRAVEL DATA PREPROCESSING ETL")
    logger.info("==================================================")

    # Step 1: Crawler Execution (Optional/If Requested)
    if run_crawler_step or not raw_input_path.exists():
        logger.info("STEP 1/2: Running Vietnam Travel Crawler...")
        try:
            from backend.preprocessing.run_crawler import main as run_crawler_main
            # Run crawler CLI
            run_crawler_main()
            logger.info("Step 1 Complete: Raw dataset updated.")
        except Exception as err:
            logger.warning(f"Step 1 Warning: Crawler run encountered note ({err}). Proceeding with available dataset.")

    else:
        logger.info(f"STEP 1/2: Raw dataset exists at '{raw_input_path}'. Skipping crawl.")

    # Step 2: Semantic Structure Cleaning
    logger.info(f"STEP 2/2: Cleaning document structure & removing CTA noise...")
    clean_report = clean_file(raw_input_path, clean_output_path)
    
    logger.info("==================================================")
    logger.info("✅ PREPROCESSING ETL PIPELINE COMPLETE!")
    logger.info(f"   • Input Raw File : {clean_report['input']}")
    logger.info(f"   • Output Clean File: {clean_report['output']}")
    logger.info(f"   • Clean Documents : {clean_report['documents']} articles processed")
    logger.info("==================================================")

    return clean_report


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="End-to-End Data Preprocessing & ETL Pipeline.")
    parser.add_argument(
        "--raw-input",
        default=str(ROOT_DIR / "data" / "processed" / "vietnam_travel_raw.jsonl"),
        help="Path to input raw JSONL dataset.",
    )
    parser.add_argument(
        "--clean-output",
        default=str(ROOT_DIR / "data" / "processed" / "vietnam_travel_cleaned.json"),
        help="Path to output cleaned JSON dataset.",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="Force re-crawling web pages before cleaning.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum pages to request during crawl.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI Entry point."""
    args = parse_args()
    report = run_pipeline(
        raw_input_path=Path(args.raw_input),
        clean_output_path=Path(args.clean_output),
        run_crawler_step=args.crawl,
        max_pages=args.max_pages,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
