"""
LLM cost monitor — tracks token usage and enforces spending limits.

PRICING (as of GPT-4o pricing, update when OpenAI changes):
  gpt-4o:           $5.00 / 1M input tokens,  $15.00 / 1M output tokens
  gpt-4o-mini:      $0.15 / 1M input tokens,   $0.60 / 1M output tokens
  text-embedding-3-small: $0.02 / 1M tokens

CIRCUIT BREAKER:
  Single call exceeds MAX_COST_PER_CALL_USD → raise CircuitBreakerError
  Prevents runaway costs from malformed requests.

PER-TENANT BUDGET:
  Daily budget stored in Redis (key: cost:daily:{tenant_id}:{date})
  TTL: 25 hours (expires after the day)
  When exceeded: block all generation, return 429 with message

PROMETHEUS METRICS:
  llm_tokens_total{model, tenant, step, direction} — counter
  llm_cost_usd_total{model, tenant, step}          — counter
  llm_call_duration_seconds{model, step}            — histogram
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Model pricing per 1M tokens (USD)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":                      {"input": 5.00,   "output": 15.00},
    "gpt-4o-2024-08-06":           {"input": 5.00,   "output": 15.00},
    "gpt-4o-mini":                 {"input": 0.15,   "output": 0.60},
    "gpt-4o-mini-2024-07-18":      {"input": 0.15,   "output": 0.60},
    "text-embedding-3-small":      {"input": 0.02,   "output": 0.0},
    "text-embedding-3-large":      {"input": 0.13,   "output": 0.0},
    "gpt-4-turbo":                 {"input": 10.00,  "output": 30.00},
}

DEFAULT_PRICING = {"input": 5.00, "output": 15.00}

# Circuit breaker thresholds
MAX_COST_PER_CALL_USD    = 5.00
DEFAULT_DAILY_BUDGET_USD = 10.00
ADMIN_DAILY_BUDGET_USD   = 100.00


class CircuitBreakerError(Exception):
    """Raised when a request would exceed cost limits."""
    def __init__(self, reason: str, estimated_cost: float):
        self.reason         = reason
        self.estimated_cost = estimated_cost
        super().__init__(f"Circuit breaker triggered: {reason} (estimated: ${estimated_cost:.4f})")


class BudgetExceededError(Exception):
    """Raised when a tenant's daily budget is exhausted."""
    def __init__(self, tenant_id: str, daily_spent: float, daily_limit: float):
        self.tenant_id   = tenant_id
        self.daily_spent = daily_spent
        self.daily_limit = daily_limit
        super().__init__(
            f"Daily budget exceeded for tenant {tenant_id[:8]}…: "
            f"${daily_spent:.4f} / ${daily_limit:.4f}"
        )


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Calculate the cost of an LLM API call in USD.

    Parameters
    ----------
    model : exact model string from OpenAI API response
    input_tokens : from response.usage.prompt_tokens
    output_tokens : from response.usage.completion_tokens

    Returns
    -------
    cost in USD (not cents)
    """
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    input_cost  = (input_tokens  / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def estimate_cost(
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> float:
    """Estimate cost before making a call (for circuit breaker pre-check)."""
    return calculate_cost(model, estimated_input_tokens, estimated_output_tokens)


def check_circuit_breaker(
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> None:
    """
    Pre-flight check before an LLM call.
    Raises CircuitBreakerError if the estimated cost exceeds MAX_COST_PER_CALL_USD.
    Call this BEFORE making the API request.
    """
    estimated = estimate_cost(model, estimated_input_tokens, estimated_output_tokens)
    if estimated > MAX_COST_PER_CALL_USD:
        raise CircuitBreakerError(
            reason=f"Estimated cost ${estimated:.4f} exceeds limit ${MAX_COST_PER_CALL_USD}",
            estimated_cost=estimated,
        )


class CostMonitor:
    """
    Records and enforces LLM spending limits.
    Uses Redis for per-tenant daily budget tracking.
    """

    def __init__(self):
        self._redis = None
        self._prom_available = False
        self._setup_prometheus()

    def _get_redis(self):
        if self._redis is None:
            import redis
            from core.config import get_settings
            self._redis = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        return self._redis

    def _setup_prometheus(self):
        """Set up Prometheus metrics for LLM cost tracking."""
        try:
            from prometheus_client import Counter, Histogram
            self._token_counter = Counter(
                "llm_tokens_total",
                "Total LLM tokens used",
                ["model", "tenant_id", "step", "direction"],
            )
            self._cost_counter = Counter(
                "llm_cost_usd_total",
                "Total LLM cost in USD",
                ["model", "tenant_id", "step"],
            )
            self._duration_hist = Histogram(
                "llm_call_duration_seconds",
                "LLM call duration",
                ["model", "step"],
                buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
            )
            self._prom_available = True
        except Exception:
            self._prom_available = False

    def record_call(
        self,
        model:         str,
        input_tokens:  int,
        output_tokens: int,
        tenant_id:     str,
        step:          str,
        duration_secs: float = 0.0,
        job_id:        str = "",
    ) -> float:
        """
        Record a completed LLM call.

        Returns
        -------
        cost_usd : the cost of this call
        """
        cost_usd = calculate_cost(model, input_tokens, output_tokens)

        # Update daily budget in Redis
        today     = date.today().isoformat()
        redis_key = f"cost:daily:{tenant_id}:{today}"
        try:
            r = self._get_redis()
            r.incrbyfloat(redis_key, cost_usd)
            r.expire(redis_key, 90_000)   # 25 hours TTL
        except Exception as e:
            logger.warning(f"Redis cost update failed: {e}")

        # Prometheus metrics
        if self._prom_available:
            try:
                self._token_counter.labels(model, tenant_id, step, "input").inc(input_tokens)
                self._token_counter.labels(model, tenant_id, step, "output").inc(output_tokens)
                self._cost_counter.labels(model, tenant_id, step).inc(cost_usd)
                if duration_secs > 0:
                    self._duration_hist.labels(model, step).observe(duration_secs)
            except Exception:
                pass

        logger.info(
            f"LLM call: model={model}, step={step}, tenant={tenant_id[:8]}…, "
            f"tokens={input_tokens}+{output_tokens}, cost=${cost_usd:.5f}, "
            f"duration={duration_secs:.1f}s"
        )

        return cost_usd

    def check_daily_budget(self, tenant_id: str, plan: str = "free") -> None:
        """
        Check if tenant has remaining daily budget.
        Raises BudgetExceededError if limit is reached.
        Call this at the START of generation, before any LLM calls.
        """
        daily_limit = ADMIN_DAILY_BUDGET_USD if plan == "admin" else DEFAULT_DAILY_BUDGET_USD
        today       = date.today().isoformat()
        redis_key   = f"cost:daily:{tenant_id}:{today}"

        try:
            r = self._get_redis()
            spent_str = r.get(redis_key)
            daily_spent = float(spent_str) if spent_str else 0.0

            if daily_spent >= daily_limit:
                raise BudgetExceededError(tenant_id, daily_spent, daily_limit)

        except BudgetExceededError:
            raise
        except Exception as e:
            logger.warning(f"Budget check failed (non-fatal): {e}")

    def get_tenant_usage(self, tenant_id: str, days: int = 30) -> list[dict]:
        """Get cost breakdown for a tenant over the last N days."""
        from datetime import timedelta
        import datetime

        r = self._get_redis()
        usage = []
        for i in range(days):
            day = (datetime.date.today() - timedelta(days=i)).isoformat()
            key = f"cost:daily:{tenant_id}:{day}"
            try:
                val = r.get(key)
                if val:
                    usage.append({"date": day, "cost_usd": float(val)})
            except Exception:
                pass
        return sorted(usage, key=lambda x: x["date"])


# Module-level singleton
_monitor: Optional[CostMonitor] = None


def get_cost_monitor() -> CostMonitor:
    global _monitor
    if _monitor is None:
        _monitor = CostMonitor()
    return _monitor
