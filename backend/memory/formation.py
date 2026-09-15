"""Background semantic memory formation engine (ADR 0038 / Plan v0.18).

Consumes positive source handling events, performs pre-model secret scans,
extracts closed registry-v2 candidates via the model adapter, assigns retention
via RetentionAssignmentPolicy, and validates lifecycle eligibility at LifecycleStage.FORMATION.
Emits immutable MemoryEvidence and MemoryCandidate pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from backend.memory.lifecycle import (
    LifecycleFacts,
    LifecycleStage,
    MemoryLifecyclePolicy,
    RetentionAssignmentPolicy,
)
from backend.memory.source_handling import (
    SourceHandlingRecord,
    allows_background_formation,
)
from backend.memory.write_pipeline.model_adapter import MemoryExtractionModel
from backend.memory.write_pipeline.models import (
    SENSITIVITY_RANK,
    Authority,
    MemoryCandidate,
    MemoryEvidence,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    SourceValidity,
    new_candidate_id,
    new_evidence_id,
)
from backend.memory.write_pipeline.registry import (
    get_key_definition,
    is_known_key,
)
from backend.memory.write_pipeline.secrets import detect_prohibited_content


@dataclass(frozen=True)
class FormedMemoryItem:
    """One immutable formed candidate with its bound evidence and assigned retention."""

    evidence: MemoryEvidence
    candidate: MemoryCandidate
    retention_mode: RetentionMode


class MemoryFormationEngine:
    """Orchestrates background candidate formation from released outbox sources."""

    def __init__(
        self,
        *,
        model_adapter: Any | None = None,
        lifecycle_policy: MemoryLifecyclePolicy | None = None,
        retention_policy: RetentionAssignmentPolicy | None = None,
    ) -> None:
        self._model_adapter = model_adapter or MemoryExtractionModel()
        self._lifecycle_policy = lifecycle_policy or MemoryLifecyclePolicy()
        self._retention_policy = retention_policy or RetentionAssignmentPolicy()

    def form_memory(
        self,
        *,
        source_outbox_id: str,
        source_message_id: str,
        owner_user_id: str,
        conversation_id: str,
        user_text: str,
        source_handling_record: SourceHandlingRecord | None,
        stamped_generation: int = 1,
        current_generation: int = 1,
        source_validity: SourceValidity = SourceValidity.VALID,
        observed_at: datetime | None = None,
    ) -> tuple[FormedMemoryItem, ...]:
        """Form memory evidence and candidates if positive source handling allows it."""
        # 1. Check positive source handling authority gate
        if not allows_background_formation(source_handling_record):
            return ()

        # 2. Pre-model secret scan: reject prohibited content before model exposure
        if detect_prohibited_content(user_text) is not None:
            return ()

        obs_time = observed_at or datetime.now(timezone.utc)
        evidence = MemoryEvidence(
            evidence_id=new_evidence_id(),
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            display_text=user_text,
            authority=Authority.REPEATED_INFERENCE,
            observed_at=obs_time,
        )

        # 3. Model extraction
        messages = [{"role": "user", "content": user_text}]
        raw_candidates = self._model_adapter.extract(
            messages=messages,
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            evidence_ids=(evidence.evidence_id,),
        )

        formed: list[FormedMemoryItem] = []
        for cand in raw_candidates:
            # 4. Registry v2 validation
            if not is_known_key(cand.canonical_key):
                continue
            key_def = get_key_definition(cand.canonical_key)

            cand_scope = MemoryScope(cand.scope) if isinstance(cand.scope, str) else cand.scope
            if cand_scope not in key_def.allowed_scopes:
                continue

            cand_sensitivity = (
                SensitivityBand(cand.sensitivity)
                if isinstance(cand.sensitivity, str)
                else cand.sensitivity
            )
            min_sens = (
                SensitivityBand(key_def.minimum_sensitivity)
                if isinstance(key_def.minimum_sensitivity, str)
                else key_def.minimum_sensitivity
            )
            if SENSITIVITY_RANK[cand_sensitivity] < SENSITIVITY_RANK[min_sens]:
                continue

            # 5. Assign retention via RetentionAssignmentPolicy
            cand_authority = (
                Authority(cand.authority)
                if isinstance(cand.authority, str)
                else cand.authority
            )
            try:
                retention_mode = self._retention_policy.assign(
                    scope=cand_scope,
                    authority=cand_authority,
                )
            except ValueError:
                continue

            # 6. Validate lifecycle eligibility at FORMATION stage
            lifecycle_facts = LifecycleFacts(
                retention_mode=retention_mode,
                stamped_generation=stamped_generation,
                current_generation=current_generation,
                scope=cand_scope,
                sensitivity=cand_sensitivity,
                source_validity=source_validity,
                allowed_scopes=key_def.allowed_scopes,
                minimum_sensitivity=min_sens,
            )
            decision = self._lifecycle_policy.evaluate(
                stage=LifecycleStage.FORMATION,
                facts=lifecycle_facts,
            )
            if not decision.eligible:
                continue

            # Ensure candidate references the formed evidence_id
            if evidence.evidence_id not in cand.evidence_ids:
                cand = MemoryCandidate(
                    candidate_id=cand.candidate_id,
                    evidence_ids=(evidence.evidence_id,),
                    owner_user_id=cand.owner_user_id,
                    scope=cand.scope,
                    conversation_id=cand.conversation_id,
                    canonical_key=cand.canonical_key,
                    normalized_value=cand.normalized_value,
                    display_text=cand.display_text,
                    authority=cand.authority,
                    sensitivity=cand.sensitivity,
                    condition=cand.condition,
                    subject_key=cand.subject_key,
                    observed_at=cand.observed_at or obs_time,
                    confidence=cand.confidence,
                    suppression_generation=cand.suppression_generation,
                )

            formed.append(
                FormedMemoryItem(
                    evidence=evidence,
                    candidate=cand,
                    retention_mode=retention_mode,
                )
            )

        return tuple(formed)
