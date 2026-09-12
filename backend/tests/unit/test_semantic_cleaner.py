"""Unit tests for the semantic cleaning stage.

C13: the raw corpus carries no `sections` key, so `clean_document` iterated an
absent key, produced zero sections, and collapsed `clean_text` to the title for
all 281 documents. These tests pin the derivation and the fail-loud contract.
"""

from __future__ import annotations

import json

import pytest

from backend.preprocessing.semantic_cleaner import (
    CleaningError,
    _sections_from_text,
    clean_document,
    clean_file,
)


def _write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    return path


def test_sections_are_derived_from_raw_text_when_absent():
    """A record with no `sections` key still yields a real section."""
    cleaned, _ = clean_document(
        {"title": "Huế", "text": "Bún bò là món ăn nổi tiếng.\n\nVỹ Dạ là nơi yên tĩnh."}
    )

    assert len(cleaned["sections"]) == 1
    assert "Bún bò" in cleaned["sections"][0]["text"]
    assert "Bún bò" in cleaned["clean_text"]


def test_clean_text_is_not_just_the_title():
    """The defect being fixed: clean_text used to equal the title alone."""
    cleaned, _ = clean_document(
        {"title": "Đà Nẵng", "text": "Bãi biển Mỹ Khê rất đẹp và đông khách."}
    )

    assert cleaned["clean_text"] != cleaned["title"]
    assert cleaned["clean_text"].startswith("Đà Nẵng")


def test_markdown_headings_are_honoured_when_present():
    cleaned, _ = clean_document(
        {"title": "Huế", "text": "## Ăn gì\nBún bò.\n\n## Ở đâu\nVỹ Dạ."}
    )

    assert len(cleaned["sections"]) == 2
    assert cleaned["sections"][0]["heading"] == "Ăn gì"
    assert cleaned["sections"][1]["heading"] == "Ở đâu"


def test_existing_sections_are_left_alone():
    """A record that already carries sections must not be re-derived."""
    doc = {
        "title": "T",
        "sections": [{"heading": "H", "text": "body"}],
        "text": "ignored",
    }

    cleaned, _ = clean_document(doc)

    assert len(cleaned["sections"]) == 1
    assert "ignored" not in cleaned["clean_text"]


def test_empty_text_yields_no_sections():
    assert _sections_from_text("") == []
    assert _sections_from_text(None) == []


def test_clean_file_fails_when_no_section_is_produced(tmp_path):
    """A run that would emit an empty artifact must fail, not report success."""
    source = _write_jsonl(tmp_path / "in.jsonl", [{"title": "T", "text": ""}])
    output = tmp_path / "out.json"

    with pytest.raises(CleaningError, match="no_sections_produced"):
        clean_file(source, output)

    assert not output.exists()


def test_clean_file_writes_when_sections_exist(tmp_path):
    source = _write_jsonl(
        tmp_path / "in.jsonl", [{"title": "T", "text": "Nội dung thật của tài liệu."}]
    )
    output = tmp_path / "out.json"

    result = clean_file(source, output)

    assert result["documents"] == 1
    assert output.exists()
    assert "Nội dung thật" in json.loads(output.read_text(encoding="utf-8-sig"))[0]["clean_text"]
