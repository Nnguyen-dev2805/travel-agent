"""An OpenAI-compatible `LLMProvider` for the memory write pipeline.

`MemoryExtractionModel` consumes the `LLMProvider` protocol
(`generate(prompt, **kwargs) -> str`). No production implementation of that
protocol existed: the RAG path's `LLMGenerator.generate(user_message, context)`
has a different signature and returns a different type, and every
`MemoryExtractionModel(...)` construction site was in tests, always with a fake.
The worker therefore could not be constructed.

This module is that adapter. It takes its endpoint, credential, model and limits
from the same `.env`-backed `Settings` the chat path uses, so one deployment has
one provider configuration rather than two that can drift.

**Error classification is the part that matters.** `MemoryExtractionModel`
distinguishes `ProviderTransientError` from `ProviderPermanentError`, and that
distinction decides retry versus dead-letter. Too eager a transient mapping
retries a permanently broken request until the attempt budget is exhausted, at
cost; too eager a permanent mapping dead-letters work that would have succeeded.
The mapping lives in one place, `_classify`, so it can be argued with rather than
rediscovered.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.app.config import Settings, get_settings
from backend.memory.write_pipeline.model_adapter import (
    CostEvidence,
    ProviderPermanentError,
    ProviderTransientError,
    TokenUsage,
)

logger = logging.getLogger("travel_agent_memory_provider")

#: Status codes a retry can plausibly fix. 408 is a timeout, 409 a concurrent
#: conflict, 425 too early, 429 rate limiting. Everything else below 500 is the
#: caller's fault and will fail again identically.
_TRANSIENT_STATUS = frozenset({408, 409, 425, 429})


def _classify(error: BaseException) -> Exception:
    """Map a provider failure onto the pipeline's retry vocabulary.

    Returns the error to raise, never raises. The default is **permanent**: an
    unclassified failure is not retried, because retrying an unknown failure is
    how a broken deployment turns into a cost incident.
    """
    import openai

    if isinstance(error, (openai.APITimeoutError, openai.APIConnectionError)):
        return ProviderTransientError(
            f"provider unreachable class={type(error).__name__}"
        )
    if isinstance(error, openai.RateLimitError):
        return ProviderTransientError("provider rate limited")
    if isinstance(error, openai.APIStatusError):
        status = getattr(error, "status_code", None)
        if isinstance(status, int) and (status >= 500 or status in _TRANSIENT_STATUS):
            return ProviderTransientError(f"provider status {status}")
        return ProviderPermanentError(f"provider status {status}")
    return ProviderPermanentError(
        f"unclassified provider failure class={type(error).__name__}"
    )


def _first_message_text(response: Any) -> str:
    """Return the first choice's text, or fail as a permanent provider error.

    An empty completion is not retryable: the request was well formed and the
    provider answered with nothing, so the same request will answer the same way.
    """
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ProviderPermanentError("provider returned no choices")
    content = getattr(getattr(choices[0], "message", None), "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ProviderPermanentError("provider returned an empty completion")
    return content


class OpenAICompatibleProvider:
    """`LLMProvider` over the configured OpenAI-compatible endpoint.

    Constructed from `Settings` by default, so the endpoint, credential, model,
    timeout and retry budget all come from `.env`. A client may be injected for
    tests, in which case nothing here owns or closes it.
    """

    def __init__(
        self,
        client: Any = None,
        settings: Settings | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._client = client
        self._owned_client: Any = None
        self._model_name = model_name or self._settings.LLM_MODEL
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self._settings.LLM_REQUEST_TIMEOUT_SECONDS
        )
        self._max_retries = (
            max_retries
            if max_retries is not None
            else self._settings.LLM_MAX_RETRIES
        )
        #: Read by `MemoryOutboxWorker` after each call to record per-attempt cost.
        self.last_token_usage: TokenUsage | None = None
        self.last_cost_evidence: CostEvidence | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            from openai import OpenAI

            base_url = (self._settings.GITHUB_MODELS_URL or "").strip()
            token = (self._settings.GITHUB_TOKEN or "").strip()
            if not base_url or not token:
                # Permanent on purpose: no amount of retrying sets a variable.
                raise ProviderPermanentError(
                    "The model provider is not configured: GITHUB_MODELS_URL and "
                    "GITHUB_TOKEN must both be set."
                )
            self._owned_client = OpenAI(
                base_url=base_url,
                api_key=token,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._owned_client

    def close(self) -> None:
        """Release the owned client. An injected client belongs to the caller."""
        if self._owned_client is not None:
            self._owned_client.close()
            self._owned_client = None

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Send one prompt and return the completion text.

        Records token usage and cost evidence for the attempt before returning,
        because `MemoryOutboxWorker` reads them from the adapter and a failed
        attempt still cost money.
        """
        client = self._get_client()
        model = kwargs.pop("model", self._model_name)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
        except Exception as error:  # noqa: BLE001 - classified, never swallowed
            raise _classify(error) from error

        self._record_usage(response, model)
        return _first_message_text(response)

    def _record_usage(self, response: Any, model: str) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        self.last_token_usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(
                getattr(usage, "total_tokens", 0)
                or (prompt_tokens + completion_tokens)
            ),
        )
        self.last_cost_evidence = CostEvidence(
            estimated_cost_usd=0.0,
            model_name=model,
        )
