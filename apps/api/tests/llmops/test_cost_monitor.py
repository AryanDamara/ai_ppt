"""Tests for the cost monitor."""
import pytest


def test_calculate_cost_gpt4o():
    """Calculate cost for a GPT-4o call."""
    from services.llmops.cost_monitor import calculate_cost

    cost = calculate_cost("gpt-4o", input_tokens=1000, output_tokens=500)
    # gpt-4o: $5.00/1M input, $15.00/1M output
    expected = (1000 / 1_000_000 * 5.00) + (500 / 1_000_000 * 15.00)
    assert abs(cost - expected) < 0.0001


def test_calculate_cost_gpt4o_mini():
    """Calculate cost for a GPT-4o-mini call."""
    from services.llmops.cost_monitor import calculate_cost

    cost = calculate_cost("gpt-4o-mini", input_tokens=10000, output_tokens=2000)
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    expected = (10000 / 1_000_000 * 0.15) + (2000 / 1_000_000 * 0.60)
    assert abs(cost - expected) < 0.0001


def test_circuit_breaker_pass():
    """Circuit breaker should pass for small estimated costs."""
    from services.llmops.cost_monitor import check_circuit_breaker

    # Small call: should not raise
    check_circuit_breaker("gpt-4o-mini", estimated_input_tokens=1000, estimated_output_tokens=500)


def test_circuit_breaker_triggered():
    """Circuit breaker should raise for excessively large calls."""
    from services.llmops.cost_monitor import check_circuit_breaker, CircuitBreakerError

    with pytest.raises(CircuitBreakerError):
        # Huge call: 10M tokens on gpt-4o = ~$50
        check_circuit_breaker("gpt-4o", estimated_input_tokens=10_000_000, estimated_output_tokens=0)


def test_estimate_cost():
    """Estimate cost should return positive float."""
    from services.llmops.cost_monitor import estimate_cost

    cost = estimate_cost("gpt-4o-mini", 1000, 500)
    assert cost > 0
    assert isinstance(cost, float)


def test_unknown_model_uses_default():
    """Unknown model should use default pricing, not crash."""
    from services.llmops.cost_monitor import calculate_cost

    cost = calculate_cost("unknown-model-xyz", input_tokens=1000, output_tokens=500)
    assert cost > 0


def test_cost_monitor_singleton():
    """get_cost_monitor should return the same instance."""
    from services.llmops.cost_monitor import get_cost_monitor

    m1 = get_cost_monitor()
    m2 = get_cost_monitor()
    assert m1 is m2
