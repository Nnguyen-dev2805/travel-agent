"""Compatibility wrapper for LLM evaluation.

Deprecated: Governed evaluation now uses `backend.rag.evaluation.judge.JudgeAdapter`
and `backend.rag.evaluation.runner.EvaluationRunner`. This module is retained for
backward compatibility without constructing hardcoded collections or synthetic fallbacks.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.rag.evaluation.judge import (
    JUDGE_DIMENSIONS,
    JUDGE_PROMPT_ID,
    JUDGE_RUBRIC_ID,
    JUDGE_SCHEMA_VERSION,
    JudgeAdapter,
    JudgeResult,
)
from backend.rag.evaluation.models import JudgeConfig

logger = logging.getLogger("llm_judge_evaluator")

# Compatibility export of criteria
CRITERIA_KEYS = list(JUDGE_DIMENSIONS)


class LLMJudgeEvaluator:
    """Thin compatibility adapter wrapping the strict single-answer JudgeAdapter."""

    def __init__(
        self,
        config: Optional[JudgeConfig] = None,
        queries_path: Optional[Path] = None,
    ) -> None:
        self.config = config or JudgeConfig(
            model="gpt-4o-mini",
            prompt_id=JUDGE_PROMPT_ID,
            rubric_id=JUDGE_RUBRIC_ID,
            schema_version=JUDGE_SCHEMA_VERSION,
            temperature=0.0,
        )
        self.queries_path = queries_path
        self.adapter = JudgeAdapter(config=self.config)

    def judge_single_answer(
        self,
        question: str,
        answer: str,
        evidence: Any,
        reference_answer: Optional[str] = None,
    ) -> JudgeResult:
        """Delegate to strict JudgeAdapter."""
        return self.adapter.score(
            question=question,
            answer=answer,
            evidence=evidence,
            reference_answer=reference_answer,
        )


def main() -> int:
    """CLI Notice: Route through backend.rag.evaluation.cli instead."""
    print(
        "Notice: Legacy llm_judge_evaluator is deprecated. "
        "Please use `python -m backend.rag.evaluation.cli run --mode full` instead."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
