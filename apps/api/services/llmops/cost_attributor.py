"""
Cost attributor — per-tenant cost attribution with breakdown by model, step, and day.

Wraps CostMonitor to provide higher-level attribution reports:
  - Per-tenant daily/weekly/monthly cost reports
  - Per-step cost breakdown (which pipeline step costs most?)
  - Model efficiency tracking (how much would gpt-4o-mini save?)
"""
from __future__ import annotations
import logging
from typing import Optional
from datetime import date, timedelta

from services.llmops.cost_monitor import get_cost_monitor, calculate_cost

logger = logging.getLogger(__name__)


class CostAttributor:
    """Generates cost attribution reports for tenants and pipeline steps."""

    def __init__(self):
        self._monitor = get_cost_monitor()

    def get_tenant_report(self, tenant_id: str, days: int = 30) -> dict:
        """
        Comprehensive cost report for a tenant.

        Returns
        -------
        dict with: total_cost_usd, daily_breakdown, estimated_monthly,
                   budget_remaining_today, plan_recommendation
        """
        usage = self._monitor.get_tenant_usage(tenant_id, days)
        total = sum(u["cost_usd"] for u in usage)

        # Calculate daily average for monthly estimate
        active_days = max(1, len(usage))
        daily_avg = total / active_days
        estimated_monthly = daily_avg * 30

        # Today's remaining budget
        from services.llmops.cost_monitor import DEFAULT_DAILY_BUDGET_USD
        today_usage = [u for u in usage if u["date"] == date.today().isoformat()]
        today_spent = today_usage[0]["cost_usd"] if today_usage else 0.0

        return {
            "tenant_id":           tenant_id,
            "period_days":         days,
            "total_cost_usd":      round(total, 4),
            "daily_average_usd":   round(daily_avg, 4),
            "estimated_monthly_usd": round(estimated_monthly, 2),
            "budget_remaining_today": round(max(0, DEFAULT_DAILY_BUDGET_USD - today_spent), 4),
            "daily_breakdown":     usage,
            "active_days":         active_days,
        }

    @staticmethod
    def estimate_savings_from_routing(
        current_model: str,
        alternative_model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> dict:
        """
        Calculate potential savings from model routing.
        E.g., "If Step 1 used gpt-4o-mini instead of gpt-4o, you'd save X."
        """
        current_cost = calculate_cost(current_model, input_tokens, output_tokens)
        alt_cost     = calculate_cost(alternative_model, input_tokens, output_tokens)
        savings      = current_cost - alt_cost

        return {
            "current_model":      current_model,
            "current_cost_usd":   round(current_cost, 6),
            "alternative_model":  alternative_model,
            "alternative_cost_usd": round(alt_cost, 6),
            "savings_usd":        round(savings, 6),
            "savings_percent":    round((savings / max(current_cost, 0.000001)) * 100, 1),
        }
