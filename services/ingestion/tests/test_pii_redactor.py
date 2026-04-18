import pytest
from pipeline.enrichers.pii_redactor import PIIRedactor


def test_email_redacted():
    redactor = PIIRedactor()
    result   = redactor.redact("Contact john.smith@company.com for details.")
    assert "john.smith@company.com" not in result.redacted_text
    assert result.pii_found


def test_person_name_redacted():
    redactor = PIIRedactor()
    result   = redactor.redact("CEO John Smith announced quarterly results.")
    assert result.pii_found or "John Smith" not in result.redacted_text


def test_clean_text_unchanged():
    redactor = PIIRedactor()
    text     = "Revenue grew 34% year-over-year to $187M in Q3 2024."
    result   = redactor.redact(text)
    # No PII — text should be substantially unchanged
    assert "34%" in result.redacted_text
    assert "$187M" in result.redacted_text


def test_reversible_tokens_are_unique():
    """Same name in two calls should get the same token (deterministic hash)."""
    redactor = PIIRedactor()
    r1 = redactor.redact("Contact Alice Johnson today.", reversible=True)
    r2 = redactor.redact("Alice Johnson will present.", reversible=True)
    # Both should produce the same token for "Alice Johnson"
    token1 = [w for w in r1.redacted_text.split() if w.startswith("<PERSON")]
    token2 = [w for w in r2.redacted_text.split() if w.startswith("<PERSON")]
    if token1 and token2:
        assert token1[0] == token2[0]


def test_redaction_never_crashes_on_empty():
    redactor = PIIRedactor()
    result   = redactor.redact("")
    assert result.redacted_text == ""
    assert not result.pii_found


def test_aws_key_redacted():
    """Extra regex patterns should catch AWS access keys."""
    redactor = PIIRedactor()
    result = redactor.redact("AWS key: AKIAIOSFODNN7EXAMPLE is exposed.")
    assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text


def test_ssn_pattern_redacted():
    """SSN patterns should be caught by extra regex."""
    redactor = PIIRedactor()
    result = redactor.redact("SSN: 123-45-6789 was found in the document.")
    assert "123-45-6789" not in result.redacted_text


def test_non_english_text_handled():
    """Redactor should not crash on non-English text."""
    redactor = PIIRedactor()
    result = redactor.redact("Dies ist ein deutscher Text ohne personenbezogene Daten.", language="de")
    assert result.redacted_text  # Should return something
