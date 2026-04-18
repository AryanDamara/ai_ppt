"""
Human feedback collector — captures user satisfaction signals.

SIGNAL TYPES:
  thumbs_up  : User explicitly liked this slide
  thumbs_down: User explicitly disliked this slide
  edit       : User changed slide content (implicit quality signal)

CONSENT:
  Users must opt-in to telemetry in account settings.
  Edit data is anonymised (original_value → hash) by default.
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FeedbackRecord:
    user_id:        str
    tenant_id:      str
    deck_id:        str
    slide_id:       str
    feedback_type:  str          # thumbs_up | thumbs_down | edit
    edit_delta:     Optional[dict] = None
    original_value: Optional[str] = None
    new_value:      Optional[str] = None
    trace_id:       Optional[str] = None


class FeedbackCollector:
    """Stores and analyses user feedback on generated presentations."""

    async def record_feedback(
        self,
        record: FeedbackRecord,
        consent_level: str = "basic",
    ) -> str:
        """
        Persist a feedback record.

        consent_level:
          "none"  : No telemetry (user opted out)
          "basic" : Store type and anonymised delta (default)
          "full"  : Store full edit content for training dataset

        Returns feedback_id.
        """
        if consent_level == "none":
            logger.debug(f"Feedback skipped (consent=none) for {record.slide_id}")
            return ""

        # Anonymise based on consent
        original_value = record.original_value
        new_value      = record.new_value

        if consent_level == "basic" and original_value:
            original_value = hashlib.sha256(original_value.encode()).hexdigest()[:16]

        feedback_data = {
            "user_id":        record.user_id,
            "tenant_id":      record.tenant_id,
            "deck_id":        record.deck_id,
            "slide_id":       record.slide_id,
            "feedback_type":  record.feedback_type,
            "edit_delta":     record.edit_delta,
            "original_value": original_value,
            "new_value":      new_value if consent_level == "full" else None,
            "trace_id":       record.trace_id,
        }

        try:
            from services.db.session import get_raw_connection
            async with get_raw_connection() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO feedback (user_id, tenant_id, deck_id, slide_id,
                                         feedback_type, edit_delta, original_value,
                                         new_value, trace_id)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
                    RETURNING id
                    """,
                    record.user_id,
                    record.tenant_id,
                    record.deck_id,
                    record.slide_id,
                    record.feedback_type,
                    __import__("json").dumps(record.edit_delta) if record.edit_delta else None,
                    original_value,
                    new_value if consent_level == "full" else None,
                    record.trace_id,
                )
                feedback_id = str(row["id"]) if row else ""
                logger.info(f"Feedback recorded: {record.feedback_type} on slide {record.slide_id[:8]}…")
                return feedback_id

        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            return ""

    async def get_feedback_stats(
        self,
        tenant_id: str,
        deck_id:   Optional[str] = None,
        days:      int = 30,
    ) -> dict:
        """
        Get aggregated feedback statistics for a tenant.

        Returns dict with:
          total_signals, thumbs_up, thumbs_down, edits,
          thumbs_up_rate, most_edited_slides
        """
        try:
            from services.db.session import get_raw_connection
            from datetime import timedelta, datetime, timezone

            since = datetime.now(timezone.utc) - timedelta(days=days)

            async with get_raw_connection() as conn:
                query = """
                    SELECT feedback_type, COUNT(*) as count, slide_id
                    FROM feedback
                    WHERE tenant_id = $1 AND created_at > $2
                """
                params = [tenant_id, since]

                if deck_id:
                    query += " AND deck_id = $3"
                    params.append(deck_id)

                query += " GROUP BY feedback_type, slide_id"
                rows = await conn.fetch(query, *params)

            thumbs_up   = sum(r["count"] for r in rows if r["feedback_type"] == "thumbs_up")
            thumbs_down = sum(r["count"] for r in rows if r["feedback_type"] == "thumbs_down")
            edits       = sum(r["count"] for r in rows if r["feedback_type"] == "edit")
            total       = thumbs_up + thumbs_down + edits

            most_edited = sorted(
                [(r["slide_id"], r["count"]) for r in rows if r["feedback_type"] == "edit"],
                key=lambda x: x[1], reverse=True,
            )[:5]

            return {
                "total_signals":      total,
                "thumbs_up":          thumbs_up,
                "thumbs_down":        thumbs_down,
                "edits":              edits,
                "thumbs_up_rate":     thumbs_up / max(1, thumbs_up + thumbs_down),
                "most_edited_slides": most_edited,
                "period_days":        days,
            }

        except Exception as e:
            logger.error(f"Failed to get feedback stats: {e}")
            return {"total_signals": 0, "thumbs_up": 0, "thumbs_down": 0, "edits": 0}
