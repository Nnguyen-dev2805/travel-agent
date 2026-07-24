"""Document Loader module for JSONL travel datasets."""

import json
import logging
from pathlib import Path
from typing import Any, List, Dict

logger = logging.getLogger("travel_agent_loader")


def load_jsonl_dataset(file_path: Path) -> List[Dict[str, Any]]:
    """Load and validate documents from a JSONL file.

    Args:
        file_path: Path to the JSONL dataset file.

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
    line_number = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_number += 1
            line = line.strip()
            if not line:
                continue

            try:
                doc = json.loads(line)
                # Validate mandatory fields
                if not isinstance(doc, dict):
                    logger.warning(f"Line {line_number} is not a valid JSON object. Skipping.")
                    continue

                text = doc.get("text", "").strip()
                title = doc.get("title", "").strip()
                url = doc.get("url", "").strip()

                if not text:
                    logger.warning(f"Line {line_number} has empty text content. Skipping.")
                    continue

                # Ensure document_id exists
                document_id = doc.get("document_id") or f"doc_{line_number}"

                validated_doc = {
                    "document_id": str(document_id),
                    "url": url,
                    "title": title or "Untitled Travel Guide",
                    "text": text,
                    "meta_description": doc.get("meta_description", ""),
                    "language": doc.get("language", "en"),
                    "source": doc.get("source", "Vietnam Travel"),
                    "source_domain": doc.get("source_domain", "vietnam.travel"),
                }
                documents.append(validated_doc)

            except json.JSONDecodeError as e:
                logger.warning(f"Line {line_number} JSON decode error: {str(e)}. Skipping.")
                continue

    logger.info(f"Successfully loaded {len(documents)} valid documents from {file_path}")
    if not documents:
        raise ValueError(f"No valid document records found in {file_path}")

    return documents
