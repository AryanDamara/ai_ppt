"""
Cost router — tenant cost dashboard endpoints.

GET /api/v1/costs/usage   — get cost breakdown for the current tenant
GET /api/v1/costs/circuit — check circuit breaker status
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from services.auth.jwt_validator import get_current_user, AuthenticatedUser
from services.llmops.cost_monitor import get_cost_monitor
from services.llmops.cost_attributor import CostAttributor
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/costs/usage")
async def get_cost_usage(
    days: int = 30,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Get cost breakdown for the current tenant.
    Returns daily cost breakdown, totals, and estimated monthly spend.
    """
    attributor = CostAttributor()
    report = attributor.get_tenant_report(user.tenant_id, days=days)
    return report


@router.get("/costs/circuit")
async def get_circuit_status(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Check circuit breaker / budget status for the current tenant.
    Returns remaining daily budget and limits.
    """
    from services.llmops.cost_monitor import DEFAULT_DAILY_BUDGET_USD
    from datetime import date

    monitor = get_cost_monitor()
    try:
        monitor.check_daily_budget(user.tenant_id, user.plan)
        budget_ok = True
        message = "Budget available"
    except Exception as e:
        budget_ok = False
        message = str(e)

    usage = monitor.get_tenant_usage(user.tenant_id, days=1)
    today_spent = usage[0]["cost_usd"] if usage else 0.0

    return {
        "tenant_id":         user.tenant_id[:8] + "…",
        "plan":              user.plan,
        "budget_ok":         budget_ok,
        "message":           message,
        "daily_limit_usd":   DEFAULT_DAILY_BUDGET_USD,
        "today_spent_usd":   today_spent,
        "remaining_usd":     max(0, DEFAULT_DAILY_BUDGET_USD - today_spent),
        "date":              date.today().isoformat(),
    }
