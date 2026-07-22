"""Prompt builder cho gpt-4o-mini trong pipeline RAG du lịch."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptBuilderConfig:
    """Cấu hình prompt builder."""

    prompt_config_path: Path = Path("configs/rag_generation_prompts.json")
    max_context_chars: int = 7000
    max_chunk_chars: int = 1600


def configure_console_encoding() -> None:
    """Cấu hình console UTF-8 để in tiếng Việt ổn định trên Windows."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def normalize_text(text: Any) -> str:
    """Chuẩn hóa text ngắn trước khi đưa vào prompt."""

    return " ".join(str(text or "").replace("\n", " ").split()).strip()


def load_prompt_config(path: Path) -> dict[str, Any]:
    """Đọc cấu hình prompt JSON."""

    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy prompt config: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


class TravelRAGPromptBuilder:
    """Xây prompt messages cho model chat trong RAG du lịch."""

    def __init__(self, config: PromptBuilderConfig | None = None) -> None:
        self.config = config or PromptBuilderConfig()
        self.prompt_config = load_prompt_config(self.config.prompt_config_path)

    def format_context_item(self, item: dict[str, Any], rank: int) -> str:
        """Format một retrieved chunk thành một nguồn trong CONTEXT."""

        content = str(item.get("source_text") or item.get("text") or item.get("content") or "")
        content = content[: self.config.max_chunk_chars].strip()
        template = self.prompt_config["context_item_template"]
        return template.format(
            rank=rank,
            document_title=normalize_text(item.get("document_title") or item.get("title") or "Không rõ tiêu đề"),
            source_url=normalize_text(item.get("source_url") or item.get("url") or "Không rõ URL"),
            language=normalize_text(item.get("language") or "unknown"),
            category=normalize_text(item.get("category") or "unknown"),
            heading=normalize_text(item.get("heading") or item.get("expected_heading") or "unknown"),
            content=content,
        )

    def build_context(self, retrieved_chunks: list[dict[str, Any]]) -> str:
        """Ghép các retrieved chunks thành CONTEXT có giới hạn độ dài."""

        if not retrieved_chunks:
            return ""

        parts = []
        current_length = 0
        for index, item in enumerate(retrieved_chunks, 1):
            part = self.format_context_item(item, index)
            next_length = current_length + len(part) + 2
            if next_length > self.config.max_context_chars:
                break
            parts.append(part)
            current_length = next_length
        return "\n\n".join(parts)

    def build_messages(self, question: str, retrieved_chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Build messages truyền vào chat model."""

        context = self.build_context(retrieved_chunks)
        if not context:
            context = "Không có retrieved context phù hợp."

        user_prompt = self.prompt_config["user_prompt_template"].format(
            context=context,
            question=normalize_text(question),
        )
        return [
            {"role": "system", "content": self.prompt_config["system_prompt"]},
            {"role": "developer", "content": self.prompt_config["developer_prompt"]},
            {"role": "user", "content": user_prompt},
        ]

    def build_debug_payload(self, question: str, retrieved_chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """Tạo payload debug để kiểm tra prompt trước khi gọi model."""

        return {
            "prompt_version": self.prompt_config["prompt_version"],
            "target_model": self.prompt_config["target_model"],
            "question": question,
            "messages": self.build_messages(question, retrieved_chunks),
        }


def parse_args() -> argparse.Namespace:
    """Đọc tham số CLI."""

    parser = argparse.ArgumentParser(description="Build thử prompt cho gpt-4o-mini Travel RAG.")
    parser.add_argument("--question", default="Đà Nẵng có gì chơi trong 2 ngày?", help="Câu hỏi người dùng.")
    parser.add_argument("--chunks", default=None, help="File JSON chứa list retrieved chunks để test.")
    parser.add_argument("--prompt-config", default="configs/rag_generation_prompts.json", help="File prompt config JSON.")
    return parser.parse_args()


def main() -> int:
    """Điểm vào CLI để kiểm tra prompt builder."""

    configure_console_encoding()
    args = parse_args()
    chunks: list[dict[str, Any]] = []
    if args.chunks:
        chunks = json.loads(Path(args.chunks).read_text(encoding="utf-8"))
    builder = TravelRAGPromptBuilder(PromptBuilderConfig(prompt_config_path=Path(args.prompt_config)))
    print(json.dumps(builder.build_debug_payload(args.question, chunks), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
