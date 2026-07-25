"""Document Loader module supporting both JSONL and JSON array travel datasets."""

import json
import logging
from pathlib import Path
from typing import Any, List, Dict

logger = logging.getLogger("travel_agent_loader")


def load_jsonl_dataset(file_path: Path) -> List[Dict[str, Any]]:
    """Load and validate documents from a JSONL or JSON array file.

    Args:
        file_path: Path to the dataset file (.jsonl or .json).

    Returns:
        List of validated document dictionaries.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If mandatory fields are missing or data is empty.
    """
    if not file_path.exists():
        logger.error(f"Dataset file not found at: {file_path}")
        raise FileNotFoundError(f"Dataset file not found at: {file_path}")

    documents: List[Dict[str, Any]] = []

    # First try reading as a JSON Array (e.g. data/processed/vietnam_travel_cleaned.json)
    if file_path.suffix.lower() == ".json":
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            if isinstance(data, list):
                for index, doc in enumerate(data, 1):
                    if not isinstance(doc, dict):
                        continue

                    text = doc.get("text", "") or doc.get("clean_text", "")
                    text = text.strip()
                    title = doc.get("title", "") or doc.get("clean_title", "")
                    title = title.strip()
                    url = doc.get("url", "").strip()

                    # Check text or sections
                    sections = doc.get("sections", [])
                    if not text and not sections:
                        continue

                    document_id = doc.get("document_id") or f"doc_{index}"

                    validated_doc = {
                        "document_id": str(document_id),
                        "url": url,
                        "title": title or "Untitled Travel Guide",
                        "text": text or title,
                        "sections": sections,
                        "meta_description": doc.get("meta_description", ""),
                        "language": doc.get("language", "en"),
                        "source": doc.get("source", "Vietnam Travel"),
                        "source_domain": doc.get("source_domain", "vietnam.travel"),
                    }
                    documents.append(validated_doc)

                if documents:
                    logger.info(f"Successfully loaded {len(documents)} valid documents from JSON array file {file_path}")
                    return documents
        except json.JSONDecodeError:
            logger.info(f"{file_path} is not a valid JSON array. Falling back to line-by-line JSONL parser.")

    # Standard JSONL line-by-line parsing
    line_number = 0
    with open(file_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line_number += 1
            line = line.strip()
            if not line:
                continue

            try:
                doc = json.loads(line)
                if not isinstance(doc, dict):
                    continue

                text = doc.get("text", "").strip()
                title = doc.get("title", "").strip()
                url = doc.get("url", "").strip()

                if not text:
                    continue

                document_id = doc.get("document_id") or f"doc_{line_number}"

                validated_doc = {
                    "document_id": str(document_id),
                    "url": url,
                    "title": title or "Untitled Travel Guide",
                    "text": text,
                    "sections": doc.get("sections", []),
                    "meta_description": doc.get("meta_description", ""),
                    "language": doc.get("language", "en"),
                    "source": doc.get("source", "Vietnam Travel"),
                    "source_domain": doc.get("source_domain", "vietnam.travel"),
                }
                documents.append(validated_doc)

            except json.JSONDecodeError:
                continue

    logger.info(f"Successfully loaded {len(documents)} valid documents from {file_path}")
    if not documents:
        raise ValueError(f"No valid document records found in {file_path}")

    return documents
