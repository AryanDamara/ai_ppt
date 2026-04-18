"""
LangSmith tracing — traces every LLM call for debugging and quality monitoring.

WHY LANGSMITH:
  When a slide has wrong facts, you need to see EXACTLY what was in the prompt
  that produced it. Without tracing, debugging is guesswork.

PII PROTECTION:
  User prompts may contain sensitive information (company financials, PII).
  We redact PII from traces before sending to LangSmith.
  10% sampling rate in production (enough for debugging, minimal cost).

TRACE STRUCTURE:
  One LangSmith "run" per generation job (presentation_id)
  Child runs: step1, step2, step3 (per slide), step4
  Each child run has: input, output, start/end time, token counts
"""
from __future__ import annotations
import logging
import os
import re
import time
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Sampling: trace 10% of requests in production, 100% in development
TRACE_SAMPLE_RATE = float(os.getenv("LANGSMITH_SAMPLE_RATE", "0.10"))
LANGSMITH_ENABLED = bool(os.getenv("LANGSMITH_API_KEY", ""))

# PII patterns to redact from traces
_PII_PATTERNS = [
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b'), "[EMAIL]"),
    (re.compile(r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'), "[SSN]"),
    (re.compile(r'\b(?:\d[ -]?){13,16}\b'), "[CARD]"),
    (re.compile(r'\b\+?1?\s?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), "[PHONE]"),
]


def _redact_pii(text: str) -> str:
    """Redact PII from text before sending to external tracing service."""
    if not text:
        return text
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _should_trace() -> bool:
    """Determine if this request should be traced (sampling)."""
    if not LANGSMITH_ENABLED:
        return False
    env = os.getenv("ENVIRONMENT", "development")
    if env == "development":
        return True
    import random
    return random.random() < TRACE_SAMPLE_RATE


class LLMCallTrace:
    """Represents one LLM API call within a trace."""

    def __init__(
        self,
        run_id:      str,
        parent_id:   str,
        step_name:   str,
        prompt_name: str,
        model:       str,
        inputs:      dict,
    ):
        self.run_id      = run_id
        self.parent_id   = parent_id
        self.step_name   = step_name
        self.prompt_name = prompt_name
        self.model       = model
        self.inputs      = inputs
        self.start_time  = time.time()
        self._ls_run     = None

    def finish(
        self,
        outputs:       dict,
        input_tokens:  int = 0,
        output_tokens: int = 0,
        error:         Optional[str] = None,
    ) -> None:
        """Record the completion of an LLM call."""
        duration = time.time() - self.start_time

        if self._ls_run:
            try:
                self._ls_run.end(
                    outputs={"output": _redact_pii(str(outputs))},
                    error=error,
                )
            except Exception:
                pass

        logger.debug(
            f"Trace: {self.step_name} | model={self.model} | "
            f"tokens={input_tokens}+{output_tokens} | {duration:.1f}s"
        )


class GenerationTrace:
    """
    Trace context for one complete generation job.
    Wraps all Step 1-4 calls under a single parent trace.
    """

    def __init__(
        self,
        presentation_id: str,
        tenant_id:       str,
        user_prompt:     str,
    ):
        self.presentation_id = presentation_id
        self.tenant_id       = tenant_id
        self.user_prompt     = user_prompt
        self.trace_id        = str(uuid4())
        self._active         = _should_trace()
        self._ls_client      = None
        self._parent_run     = None

        if self._active:
            self._init_langsmith()

    def _init_langsmith(self) -> None:
        """Initialize LangSmith client and create parent run."""
        try:
            from langsmith import Client
            self._ls_client = Client(
                api_key=os.getenv("LANGSMITH_API_KEY"),
            )
            self._parent_run = self._ls_client.create_run(
                name=f"deck_generation/{self.presentation_id[:8]}",
                run_type="chain",
                inputs={
                    "user_prompt":     _redact_pii(self.user_prompt),
                    "tenant_id":       self.tenant_id[:8] + "…",
                    "presentation_id": self.presentation_id,
                },
                project_name=os.getenv("LANGSMITH_PROJECT", "aippt-production"),
            )
        except Exception as e:
            logger.warning(f"LangSmith init failed (non-fatal): {e}")
            self._active = False

    def trace_llm_call(
        self,
        step_name:   str,
        prompt_name: str,
        model:       str,
        system_msg:  str,
        user_msg:    str,
    ) -> LLMCallTrace:
        """
        Start tracing an LLM call. Returns a LLMCallTrace object.
        Call trace.finish() after the API response.
        """
        call_trace = LLMCallTrace(
            run_id=str(uuid4()),
            parent_id=self.trace_id,
            step_name=step_name,
            prompt_name=prompt_name,
            model=model,
            inputs={
                "system": _redact_pii(system_msg[:2000]),
                "user":   _redact_pii(user_msg[:2000]),
            },
        )

        if self._active and self._ls_client and self._parent_run:
            try:
                ls_run = self._ls_client.create_run(
                    name=step_name,
                    run_type="llm",
                    inputs=call_trace.inputs,
                    parent_run_id=self._parent_run.id,
                    project_name=os.getenv("LANGSMITH_PROJECT", "aippt-production"),
                )
                call_trace._ls_run = ls_run
            except Exception as e:
                logger.debug(f"LangSmith child run creation failed: {e}")

        return call_trace

    def add_feedback(self, key: str, score: float, comment: str = "") -> None:
        """
        Add user or automated feedback to the trace.
        Used to correlate human feedback (thumbs up/down) with specific traces.
        """
        if self._active and self._ls_client and self._parent_run:
            try:
                self._ls_client.create_feedback(
                    run_id=self._parent_run.id,
                    key=key,
                    score=score,
                    comment=comment[:500],
                )
            except Exception as e:
                logger.debug(f"LangSmith feedback failed: {e}")

    def finish(self, success: bool = True, error: Optional[str] = None) -> None:
        """Finalise the generation trace."""
        if self._active and self._ls_client and self._parent_run:
            try:
                self._parent_run.end(
                    outputs={"success": success},
                    error=error,
                )
            except Exception:
                pass
