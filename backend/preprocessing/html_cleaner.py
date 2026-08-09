"""Clean crawled travel HTML into structured documents before chunking."""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag, UnicodeDammit


NOISE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "form",
    "input",
    "button",
    "select",
    "textarea",
    "nav",
    "footer",
    "header",
}

NOISE_PATTERNS = (
    "advert",
    "banner",
    "breadcrumb",
    "cookie",
    "footer",
    "gallery",
    "header",
    "login",
    "modal",
    "nav",
    "newsletter",
    "popup",
    "read-more",
    "related",
    "search",
    "share",
    "sidebar",
    "signup",
    "social",
    "subscribe",
    "you-may-also",
)

STOP_HEADINGS = {
    "read more",
    "you may also like",
    "nearby places",
    "gallery",
    "tin mới",
    "danh mục",
    "kết nối với chúng tôi",
    "liên hệ",
    "login",
    "oops",
}

BOILERPLATE_TEXTS = {
    "close",
    "sign up",
    "read more",
    "tin mới",
    "danh mục",
    "kết nối với chúng tôi",
    "liên hệ",
    "login",
}

CONTENT_GUARD_SELECTORS = (
    ".elementor-widget-theme-post-content",
)

MOJIBAKE_REPLACEMENTS = {
    "â€™": "’",
    "â€˜": "‘",
    "â€œ": "“",
    "â€": "”",
    "â€": "”",
    "â€“": "–",
    "â€”": "—",
    "Â": "",
    "Ä": "Đ",
}


@dataclass(frozen=True)
class InputDocument:
    """One source row from the input JSONL."""

    document_id: str
    url: str
    title: str | None
    meta_description: str | None
    language: str | None
    raw_html_path: str
    source_domain: str | None = None

# chuẩn hóa test
def normalize_text(value: str | None) -> str:
    """Normalize Unicode, entities, mojibake, and whitespace."""

    if not value:
        return ""
    text = html.unescape(value)
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def normalized_key(value: str) -> str:
    """Return a lowercase key for duplicate detection."""

    return re.sub(r"\s+", " ", normalize_text(value).casefold()).strip()


def load_jsonl(path: Path) -> list[InputDocument]:
    """Read input JSONL rows."""

    rows: list[InputDocument] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            rows.append(
                InputDocument(
                    document_id=str(raw["document_id"]),
                    url=str(raw.get("url") or raw.get("canonical_url") or raw.get("final_url")),
                    title=raw.get("title") or raw.get("raw_title"),
                    meta_description=raw.get("meta_description"),
                    language=raw.get("language"),
                    raw_html_path=str(raw["raw_html_path"]),
                    source_domain=raw.get("source_domain"),
                )
            )
    return rows


def decode_html(content: bytes) -> str:
    """Decode HTML bytes, preferring UTF-8 when possible."""

    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        decoded = UnicodeDammit(content).unicode_markup
        return decoded or content.decode("utf-8", errors="replace")


def resolve_html_path(raw_html_path: str, input_path: Path, project_root: Path) -> Path | None:
    """Resolve raw_html_path from common project locations."""

    raw_path = Path(raw_html_path)
    candidates = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.extend(
            [
                project_root / raw_path,
                input_path.parent / raw_path,
                project_root.parent.parent / "vietnam_travel_crawler" / raw_path,
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def text_from_meta(soup: BeautifulSoup, name: str) -> str:
    """Read a meta tag content value."""

    tag = soup.find("meta", attrs={"name": lambda value: value and str(value).lower() == name.lower()})
    if tag and tag.get("content"):
        return normalize_text(str(tag["content"]))
    return ""


def extract_raw_title(soup: BeautifulSoup) -> str:
    """Extract raw title from title tag."""

    if soup.title:
        return normalize_text(soup.title.get_text(" ", strip=True))
    return ""


def clean_title(raw_title: str) -> str:
    """Remove common site suffixes from a title."""

    title = normalize_text(raw_title)
    suffixes = [
        " | Vietnam Tourism",
        " - Chuyên trang Kích cầu du lịch năm 2025",
        " | Chuyên trang Kích cầu du lịch năm 2025",
    ]
    for suffix in suffixes:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title


def node_signature(tag: Tag) -> str:
    """Return lowercase class/id/role text for noise checks."""

    values: list[str] = [tag.name.lower()]
    for attr in ("class", "id", "role", "aria-label"):
        value = tag.get(attr)
        if isinstance(value, list):
            values.extend(str(item).lower() for item in value)
        elif value:
            values.append(str(value).lower())
    return " ".join(values)


def remove_noise(soup: BeautifulSoup) -> None:
    """Remove common non-content nodes."""

    for tag in list(soup.find_all(NOISE_TAGS)):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.parent is None or tag.attrs is None:
            continue
        if any(tag.select_one(selector) for selector in CONTENT_GUARD_SELECTORS):
            continue
        signature = node_signature(tag)
        if any(pattern in signature for pattern in NOISE_PATTERNS):
            tag.decompose()


def remove_stop_sections(root: Tag) -> None:
    """Remove related/newsletter sections starting at stop headings."""

    for heading in list(root.find_all(["h1", "h2", "h3", "h4"])):
        text = normalized_key(heading.get_text(" ", strip=True))
        if text not in STOP_HEADINGS:
            continue
        container = heading
        for parent in heading.parents:
            if parent is root:
                break
            if isinstance(parent, Tag) and parent.name in {"section", "div", "article", "aside"}:
                container = parent
                break
        container.decompose()


def choose_vietnam_travel_root(soup: BeautifulSoup) -> Tag | None:
    """Choose content root for vietnam.travel pages."""

    domain_roots = [
        "div.page-article.detail",
        "div.page-place-to-go-detail",
        "div.page-plan-your-trip-recommeneded-trip-details",
        "div.page-plan-your-trip-recommended-trip-details",
        "div.page-things-to-do-detail",
    ]
    for selector in domain_roots:
        node = soup.select_one(selector)
        if node and len(node.get_text(" ", strip=True)) > 100:
            return node

    h1 = soup.find("h1", class_=lambda value: value and "title" in value)
    if isinstance(h1, Tag):
        best = None
        for parent in h1.parents:
            if not isinstance(parent, Tag):
                continue
            text_len = len(parent.get_text(" ", strip=True))
            if 500 <= text_len <= 60000:
                best = parent
                break
        if best:
            return best
    return None


def choose_2025_root(soup: BeautifulSoup) -> Tag | None:
    """Choose content root for 2025.vietnam.travel WordPress/Elementor pages."""

    selectors = [
        ".elementor-widget-theme-post-content",
        ".entry-content",
        "article .elementor",
        "article",
    ]
    for selector in selectors:
        candidates = soup.select(selector)
        candidates = [node for node in candidates if len(node.get_text(" ", strip=True)) > 300]
        if candidates:
            return max(candidates, key=lambda node: len(node.get_text(" ", strip=True)))
    return None


def choose_generic_root(soup: BeautifulSoup) -> Tag:
    """Generic fallback that chooses the densest content-like node."""

    selectors = ["main", "article", "[role='main']", ".content", ".main-content", ".entry-content", "body"]
    candidates: list[Tag] = []
    for selector in selectors:
        candidates.extend(node for node in soup.select(selector) if isinstance(node, Tag))
    if soup.body:
        candidates.append(soup.body)
    candidates = candidates or [soup]
    return max(candidates, key=lambda node: len(node.get_text(" ", strip=True)))


def choose_content_root(soup: BeautifulSoup, url: str, source_domain: str | None) -> tuple[Tag, str]:
    """Pick the best content root, preferring domain-specific extractors."""

    domain = source_domain or urlparse(url).netloc
    if domain == "vietnam.travel":
        root = choose_vietnam_travel_root(soup)
        if root:
            return root, "vietnam.travel"
    if domain == "2025.vietnam.travel":
        root = choose_2025_root(soup)
        if root:
            return root, "2025.vietnam.travel"
    return choose_generic_root(soup), "generic"


def iter_content_blocks(root: Tag) -> Iterable[Tag]:
    """Yield heading, paragraph, and list nodes in DOM order without parent duplication."""

    wanted = {"h1", "h2", "h3", "p", "ul", "ol"}

    def walk(node: Tag) -> Iterable[Tag]:
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            if child.name in {"ul", "ol"} and child.find(["h1", "h2", "h3"]):
                yield from walk(child)
                continue
            if child.name in wanted:
                yield child
                continue
            yield from walk(child)

    yield from walk(root)


def block_text(tag: Tag) -> str:
    """Extract clean text for one content block."""

    return normalize_text(tag.get_text(" ", strip=True))


def is_boilerplate(text: str) -> bool:
    """Return true when text is a known boilerplate string."""

    key = normalized_key(text)
    if key in BOILERPLATE_TEXTS or key in STOP_HEADINGS:
        return True
    if len(key) < 3:
        return True
    return False


def heading_path(stack: list[tuple[int, str]]) -> list[str]:
    """Return heading path labels."""

    return [heading for _, heading in stack]


def build_sections(root: Tag, clean_doc_title: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Build ordered sections from headings and text blocks."""

    warnings: list[str] = []
    sections: list[dict[str, Any]] = []
    heading_stack: list[tuple[int, str]] = []
    current: dict[str, Any] | None = None
    seen_blocks: set[str] = set()
    seen_headings: set[str] = set()
    order = 1

    def start_section(heading: str, level: int) -> dict[str, Any]:
        nonlocal current
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))
        current = {
            "heading": heading,
            "heading_level": level,
            "heading_path": heading_path(heading_stack),
            "blocks": [],
        }
        sections.append(current)
        return current

    def ensure_section() -> dict[str, Any]:
        nonlocal current
        if current is None:
            heading = clean_doc_title or "Untitled"
            current = start_section(heading, 1)
        return current

    for tag in iter_content_blocks(root):
        text = block_text(tag)
        if not text or is_boilerplate(text):
            continue

        if tag.name in {"h1", "h2", "h3"}:
            key = normalized_key(text)
            if key in seen_headings:
                warnings.append(f"duplicate_heading_skipped:{text[:80]}")
                continue
            seen_headings.add(key)
            start_section(text, int(tag.name[1]))
            continue

        if tag.name in {"ul", "ol"}:
            items = [block_text(item) for item in tag.find_all("li", recursive=False)]
            items = [item for item in items if item and not is_boilerplate(item)]
            if not items:
                continue
            text = "\n".join(f"- {item}" for item in items)
            key = normalized_key(text)
            if key in seen_blocks:
                warnings.append("duplicate_list_skipped")
                continue
            seen_blocks.add(key)
            section = ensure_section()
            section["blocks"].append(
                {
                    "type": "list",
                    "text": text,
                    "items": items,
                    "order": order,
                }
            )
            order += 1
            continue

        key = normalized_key(text)
        if key in seen_blocks:
            warnings.append(f"duplicate_paragraph_skipped:{text[:80]}")
            continue
        seen_blocks.add(key)
        section = ensure_section()
        section["blocks"].append(
            {
                "type": "paragraph",
                "text": text,
                "order": order,
            }
        )
        order += 1

    plain_parts: list[str] = []
    for section in sections:
        if section["heading"]:
            plain_parts.append(section["heading"])
        plain_parts.extend(block["text"] for block in section["blocks"])
    plain_text = "\n\n".join(part for part in plain_parts if part)

    if not sections:
        warnings.append("no_sections_extracted")
    if not plain_text:
        warnings.append("empty_plain_text")
    return sections, plain_text, warnings


def preprocess_document(row: InputDocument, html_path: Path) -> dict[str, Any]:
    """Preprocess one input document."""

    decoded_html = decode_html(html_path.read_bytes())
    soup = BeautifulSoup(decoded_html, "lxml")
    raw_title = extract_raw_title(soup) or normalize_text(row.title)
    doc_title = clean_title(raw_title)
    meta_description = text_from_meta(soup, "description") or normalize_text(row.meta_description)
    language = row.language
    html_tag = soup.find("html")
    if not language and html_tag and html_tag.get("lang"):
        language = normalize_text(str(html_tag["lang"]))

    working_soup = BeautifulSoup(decoded_html, "lxml")
    remove_noise(working_soup)
    root, extractor = choose_content_root(working_soup, row.url, row.source_domain)
    remove_stop_sections(root)
    sections, plain_text, warnings = build_sections(root, doc_title)

    if extractor == "generic":
        warnings.append("generic_extractor_used")
    if len(plain_text.split()) < 80:
        warnings.append("short_text")

    return {
        "document_id": row.document_id,
        "url": row.url,
        "raw_title": raw_title,
        "clean_title": doc_title,
        "meta_description": meta_description or None,
        "language": language,
        "sections": sections,
        "plain_text": plain_text,
        "quality": {
            "status": "valid" if plain_text and sections else "invalid",
            "warnings": warnings,
            "extractor": extractor,
        },
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Write compact JSONL."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def preprocess_file(input_path: Path, output_path: Path, project_root: Path | None = None) -> dict[str, Any]:
    """Preprocess all rows from an input JSONL file."""

    project_root = (project_root or input_path.parent.parent).resolve()
    documents = load_jsonl(input_path)
    cleaned: list[dict[str, Any]] = []
    missing_html: list[str] = []

    for row in documents:
        html_path = resolve_html_path(row.raw_html_path, input_path, project_root)
        if not html_path:
            missing_html.append(row.document_id)
            cleaned.append(
                {
                    "document_id": row.document_id,
                    "url": row.url,
                    "raw_title": normalize_text(row.title),
                    "clean_title": clean_title(normalize_text(row.title)),
                    "meta_description": normalize_text(row.meta_description) or None,
                    "language": row.language,
                    "sections": [],
                    "plain_text": "",
                    "quality": {
                        "status": "invalid",
                        "warnings": ["raw_html_missing"],
                    },
                }
            )
            continue
        cleaned.append(preprocess_document(row, html_path))

    written = write_jsonl(output_path, cleaned)
    valid_count = sum(1 for row in cleaned if row["quality"]["status"] == "valid")
    warning_count = sum(1 for row in cleaned if row["quality"]["warnings"])
    return {
        "input_documents": len(documents),
        "output_documents": written,
        "valid_documents": valid_count,
        "documents_with_warnings": warning_count,
        "missing_html": len(missing_html),
        "output_path": str(output_path),
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Clean crawled HTML into structured JSONL documents.")
    parser.add_argument("--input", required=True, help="Input JSONL file containing raw_html_path.")
    parser.add_argument("--output", required=True, help="Output clean JSONL file.")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root for resolving relative raw_html_path values.",
    )
    parser.add_argument("--preview", type=int, default=3, help="Print first N cleaned document previews.")
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""

    args = parse_args()
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        data_input_path = Path.cwd() / "data" / args.input
        if data_input_path.exists():
            input_path = data_input_path.resolve()
    output_path = Path(args.output).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else input_path.parent.parent.resolve()
    summary = preprocess_file(input_path, output_path, project_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.preview:
        print("\nPreview:")
        for index, line in enumerate(output_path.open("r", encoding="utf-8"), 1):
            if index > args.preview:
                break
            row = json.loads(line)
            print(
                json.dumps(
                    {
                        "document_id": row["document_id"],
                        "clean_title": row["clean_title"],
                        "sections": len(row["sections"]),
                        "plain_text_words": len(row["plain_text"].split()),
                        "quality": row["quality"],
                        "first_section": row["sections"][0] if row["sections"] else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
