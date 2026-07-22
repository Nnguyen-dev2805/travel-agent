"""Quản lý registry các embedding model dùng cho thí nghiệm RAG."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


def configure_console_encoding() -> None:
    """Cấu hình console UTF-8 để argparse/help in tiếng Việt ổn định trên Windows."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_MODEL_FIELDS = {
    "model_id",
    "provider",
    "model_name",
    "dimension",
    "context_length_tokens",
    "access_type",
    "quality_tier",
    "source_url",
}


@dataclass(frozen=True)
class RegistryConfig:
    """Cấu hình đọc registry embedding model."""

    config_path: Path
    output_path: Path


def load_registry(path: Path) -> dict[str, Any]:
    """Đọc file registry embedding model."""

    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình embedding model: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_registry(registry: dict[str, Any]) -> list[str]:
    """Kiểm tra cấu hình embedding model và trả về danh sách lỗi."""

    errors: list[str] = []
    models = registry.get("models")
    if not isinstance(models, list) or not models:
        return ["Registry phải có danh sách models không rỗng."]

    seen_model_ids: set[str] = set()
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            errors.append(f"models[{index}] không phải object.")
            continue

        missing_fields = sorted(REQUIRED_MODEL_FIELDS - set(model.keys()))
        if missing_fields:
            errors.append(f"Model tại index {index} thiếu field: {', '.join(missing_fields)}")

        model_id = str(model.get("model_id") or "")
        if not model_id:
            errors.append(f"Model tại index {index} thiếu model_id.")
        elif model_id in seen_model_ids:
            errors.append(f"model_id bị trùng: {model_id}")
        seen_model_ids.add(model_id)

        dimension = model.get("dimension")
        if not isinstance(dimension, int) or dimension <= 0:
            errors.append(f"{model_id}: dimension phải là số nguyên dương.")

        context_length = model.get("context_length_tokens")
        if not isinstance(context_length, int) or context_length <= 0:
            errors.append(f"{model_id}: context_length_tokens phải là số nguyên dương.")

    return errors


def get_model_config(registry: dict[str, Any], model_id: str) -> dict[str, Any]:
    """Lấy cấu hình model theo model_id."""

    for model in registry.get("models", []):
        if model.get("model_id") == model_id:
            return model
    raise ValueError(f"Không tìm thấy model_id trong registry: {model_id}")


def build_comparison_plan(registry: dict[str, Any]) -> dict[str, Any]:
    """Tạo kế hoạch so sánh embedding model từ registry."""

    default_experiment = registry.get("default_experiment") or {}
    models = registry.get("models") or []
    comparison_metrics = registry.get("comparison_metrics") or []

    experiment_models = []
    for order, model in enumerate(models, 1):
        experiment_models.append(
            {
                "order": order,
                "model_id": model["model_id"],
                "provider": model["provider"],
                "model_name": model["model_name"],
                "dimension": model["dimension"],
                "context_length_tokens": model["context_length_tokens"],
                "access_type": model["access_type"],
                "quality_tier": model["quality_tier"],
                "query_prefix": model.get("query_prefix", ""),
                "document_prefix": model.get("document_prefix", ""),
                "env_vars": model.get("env_vars", []),
                "embedding_output_path": str(
                    Path(default_experiment.get("output_dir", "data/embeddings"))
                    / f"{model['model_id'].replace('/', '__')}_standard_rag_embeddings.jsonl"
                ),
                "index_output_path": str(
                    Path("data/indexes") / f"{model['model_id'].replace('/', '__')}_standard_rag"
                ),
                "notes": model.get("notes", ""),
            }
        )

    return {
        "dataset": default_experiment.get("dataset"),
        "text_field": default_experiment.get("text_field", "retrieval_text"),
        "id_field": default_experiment.get("id_field", "chunk_id"),
        "recommended_baseline": default_experiment.get("recommended_baseline"),
        "recommended_quality_model": default_experiment.get("recommended_quality_model"),
        "models": experiment_models,
        "comparison_metrics": comparison_metrics,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Ghi payload JSON UTF-8."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_embedding_comparison_plan(config: RegistryConfig) -> dict[str, Any]:
    """Đọc registry, validate và ghi kế hoạch so sánh embedding model."""

    registry = load_registry(config.config_path)
    errors = validate_registry(registry)
    if errors:
        raise ValueError("Registry embedding model không hợp lệ:\n" + "\n".join(errors))

    comparison_plan = build_comparison_plan(registry)
    write_json(config.output_path, comparison_plan)
    LOGGER.info("Đã ghi kế hoạch so sánh embedding model vào %s", config.output_path)
    return comparison_plan


def parse_args() -> argparse.Namespace:
    """Đọc tham số CLI."""

    parser = argparse.ArgumentParser(description="Tạo kế hoạch so sánh embedding model cho Standard RAG.")
    parser.add_argument(
        "--config",
        default="configs/embedding_models.json",
        help="Đường dẫn registry embedding model.",
    )
    parser.add_argument(
        "--output",
        default="data/evaluation/embedding_model_comparison_plan.json",
        help="Đường dẫn file kế hoạch so sánh embedding model.",
    )
    parser.add_argument("--log-level", default="INFO", help="Mức logging của Python.")
    return parser.parse_args()


def main() -> int:
    """Điểm vào CLI."""

    configure_console_encoding()
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s:%(message)s")
    plan = create_embedding_comparison_plan(
        RegistryConfig(config_path=Path(args.config), output_path=Path(args.output)),
    )
    print(json.dumps(plan, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
