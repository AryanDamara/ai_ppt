"""
Module 10 — Production Telemetry
Prometheus metrics for layout solve performance.
"""

from dataclasses import dataclass
from typing import Optional
import time

try:
    from prometheus_client import Histogram, Counter, Gauge

    SOLVE_TIME = Histogram(
        'layout_solve_time_ms',
        'Layout solve time in milliseconds',
        ['relaxation_tier', 'slide_type'],
        buckets=[5, 10, 25, 50, 100, 250, 500, 1000],
    )

    TIER_COUNTER = Counter(
        'layout_relaxation_tier_total',
        'Number of solves per relaxation tier',
        ['tier'],
    )

    FONT_CACHE_HITS = Counter('layout_font_cache_hits_total', 'Font cache hits')
    FONT_CACHE_MISSES = Counter('layout_font_cache_misses_total', 'Font cache misses')

    ACTIVE_SOLVERS = Gauge('layout_active_solvers', 'Currently solving slides')

    PROMETHEUS_AVAILABLE = True

except ImportError:
    PROMETHEUS_AVAILABLE = False


@dataclass
class LayoutTelemetry:
    slide_id: str
    solve_time_ms: float
    relaxation_tier: int
    constraint_count: int
    slide_type: str = "unknown"
    font_cache_hit: bool = True


def record_solve(telemetry: LayoutTelemetry) -> None:
    """Record layout solve metrics to Prometheus. Non-fatal if Prometheus is not available."""
    if not PROMETHEUS_AVAILABLE:
        return

    try:
        SOLVE_TIME.labels(
            relaxation_tier=str(telemetry.relaxation_tier),
            slide_type=telemetry.slide_type,
        ).observe(telemetry.solve_time_ms)

        TIER_COUNTER.labels(tier=str(telemetry.relaxation_tier)).inc()

        if telemetry.font_cache_hit:
            FONT_CACHE_HITS.inc()
        else:
            FONT_CACHE_MISSES.inc()

    except Exception:
        pass