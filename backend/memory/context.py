"""Prompt-safe structured Memory context composer.

Governed by Plan v0.15, Spec v0.7 (lines 859-872), and ADR 0039:
- Emits only governed structured key/value/scope/influence data.
- Never injects raw source or evidence text into the prompt.
- Labeled as soft preferences / user-state context.
- Empty selection returns an empty string.
"""

from __future__ import annotations

import json
from typing import Any

from backend.memory.read_models import MemorySelection, SelectedMemory


class MemoryContextComposer:
    """Composes prompt-safe structured memory context from governed MemorySelection."""

    HEADER: str = "=== THÔNG TIN SỞ THÍCH NGƯỜI DÙNG (THAM KHẢO) ==="

    def compose(self, selection: MemorySelection) -> str:
        """Render a MemorySelection into safe, structured prompt context text.

        Returns an empty string if there are no selected memories.
        """
        if not selection.selected:
            return ""

        preferences_data: list[dict[str, Any]] = []
        for item in selection.selected:
            # Reconstruct tuples/sets as lists for clean JSON serialization
            val = list(item.normalized_value) if isinstance(item.normalized_value, (tuple, set, list)) else item.normalized_value
            preferences_data.append(
                {
                    "key": item.canonical_key,
                    "value": val,
                    "scope": item.scope.value if hasattr(item.scope, "value") else str(item.scope),
                    "influence": "soft_preference",
                }
            )

        payload = {"preferences": preferences_data}
        json_str = json.dumps(payload, ensure_ascii=False, indent=2)
        return f"{self.HEADER}\n{json_str}"
