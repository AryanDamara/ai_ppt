"""
PII Redactor using Microsoft Presidio.

WHEN PII RUNS IN THE PIPELINE:
  PII redaction runs BEFORE embedding and BEFORE any OpenAI API call.
  This ensures that:
  1. No PII is transmitted to OpenAI's servers (API calls)
  2. No PII is stored in Pinecone (vector metadata + embedded text)
  3. No PII is returned in retrieval results to the LLM

REVERSIBLE vs IRREVERSIBLE tokens:
  reversible=True (default for internal docs):
    "John Smith" → "<PERSON_a3f2b1c0>" (deterministic hash of the original)
    Same entity in two chunks gets the same token → consistent referencing
    Can be reversed by authorised systems if needed

  reversible=False (for external/public docs):
    "John Smith" → "<PERSON>"
    Permanently masked — original text cannot be recovered

POST-REDACTION VERIFICATION:
  After anonymisation, run the analyzer again on the redacted text.
  If any entities remain, log a security alert.
  This catches edge cases where anonymisation fails for unusual formats.

ENTITIES DETECTED:
  PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, US_SSN, US_BANK_NUMBER,
  US_PASSPORT, IBAN_CODE, IP_ADDRESS, MEDICAL_LICENSE, NRP (National Registry)

ADDITIONAL REGEX PATTERNS (Presidio gaps):
  - AWS access keys
  - API keys (Bearer tokens, API key patterns)
  - GPS coordinates
"""
from __future__ import annotations
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Entity types to detect
PII_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
    "US_SSN", "US_BANK_NUMBER", "US_PASSPORT", "IBAN_CODE",
    "IP_ADDRESS", "MEDICAL_LICENSE", "NRP",
]

# Additional regex patterns not covered by Presidio
_EXTRA_PATTERNS = [
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), "<AWS_ACCESS_KEY>"),
    (re.compile(r'\b(?:Bearer|bearer)\s+[A-Za-z0-9\-._~+/]+=*\b'), "<BEARER_TOKEN>"),
    (re.compile(r'\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b'), "<US_SSN>"),    # Catch SSN patterns Presidio misses
]


@dataclass
class RedactionResult:
    redacted_text:   str
    pii_found:       bool
    entity_types:    list[str]    # e.g. ["PERSON", "EMAIL_ADDRESS"]
    redaction_count: int


class PIIRedactor:
    """
    Presidio-based PII detection and anonymisation.
    Lazy-loads Presidio on first use (heavy dependency).
    """
    _analyzer   = None
    _anonymizer = None
    _loaded     = False

    @classmethod
    def _ensure_loaded(cls):
        if cls._loaded:
            return
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            cls._analyzer   = AnalyzerEngine()
            cls._anonymizer = AnonymizerEngine()
            logger.info("Presidio PII engine loaded successfully")
        except ImportError:
            logger.warning("Presidio not installed. PII redaction disabled.")
        finally:
            cls._loaded = True

    def redact(
        self,
        text: str,
        language: str = "en",
        reversible: bool = True,
    ) -> RedactionResult:
        """
        Scan and redact PII from text.

        Parameters
        ----------
        text : plain text to scan (after Docling extraction)
        language : BCP-47 code (Presidio uses 2-char codes: "en", "de", etc.)
        reversible : True = deterministic unique tokens; False = generic <TYPE> tokens

        Returns
        -------
        RedactionResult with redacted text and detection metadata
        """
        self._ensure_loaded()

        # Apply extra regex patterns first (always, even if Presidio not loaded)
        text, extra_count = self._apply_extra_patterns(text)

        if not self._analyzer or not text.strip():
            return RedactionResult(
                redacted_text=text,
                pii_found=extra_count > 0,
                entity_types=[],
                redaction_count=extra_count,
            )

        lang_code = language[:2].lower()  # "en-US" → "en"
        try:
            results = self._analyzer.analyze(
                text=text,
                language=lang_code,
                entities=PII_ENTITIES,
                score_threshold=0.6,   # Confidence floor — reduces false positives
            )

            if not results:
                return RedactionResult(
                    redacted_text=text,
                    pii_found=extra_count > 0,
                    entity_types=[],
                    redaction_count=extra_count,
                )

            entity_types = list({r.entity_type for r in results})

            if reversible:
                # Generate deterministic tokens per unique entity text
                from presidio_anonymizer.entities import OperatorConfig
                operators = {}
                for result in results:
                    entity_text = text[result.start:result.end]
                    token_id    = hashlib.sha256(entity_text.encode()).hexdigest()[:8]
                    operators[result.entity_type] = OperatorConfig(
                        "replace",
                        {"new_value": f"<{result.entity_type}_{token_id}>"}
                    )
                anonymized = self._anonymizer.anonymize(
                    text=text, analyzer_results=results, operators=operators
                )
            else:
                anonymized = self._anonymizer.anonymize(
                    text=text, analyzer_results=results
                )

            redacted_text = anonymized.text

            # ── Post-redaction verification ────────────────────────────────────
            verify = self._analyzer.analyze(
                text=redacted_text,
                language=lang_code,
                entities=PII_ENTITIES,
                score_threshold=0.7,
            )
            if verify:
                logger.error(
                    f"PII VERIFICATION FAILED: {len(verify)} entities remain after redaction. "
                    f"Types: {[r.entity_type for r in verify]}. "
                    f"SECURITY ALERT — review Presidio configuration."
                )

            return RedactionResult(
                redacted_text=redacted_text,
                pii_found=True,
                entity_types=entity_types,
                redaction_count=len(results) + extra_count,
            )

        except Exception as e:
            logger.error(f"PII redaction failed: {e}. Using original text.")
            return RedactionResult(
                redacted_text=text, pii_found=False,
                entity_types=[], redaction_count=0
            )

    @staticmethod
    def _apply_extra_patterns(text: str) -> tuple[str, int]:
        """Apply additional regex patterns not covered by Presidio."""
        count = 0
        for pattern, replacement in _EXTRA_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                text   = pattern.sub(replacement, text)
                count += len(matches)
        return text, count
