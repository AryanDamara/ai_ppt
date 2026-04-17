from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
import json
import asyncio
from datetime import datetime, timezone

from core.config import get_settings
from core.logging import get_logger, job_id_var

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


@router.websocket("/ws/job/{job_id}")
async def websocket_generation_stream(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time generation streaming.

    RECONNECTION PROTOCOL:
    After accepting the connection, server waits for the client to send:
    { "type": "subscribe", "job_id": "...", "last_event_timestamp": "ISO8601 or null" }

    If last_event_timestamp is provided, server replays all events from
    the Redis list that occurred after that timestamp before subscribing
    to new events. This ensures no events are lost on reconnect.

    If the generation is already complete when the client connects,
    the server replays all events and closes cleanly.
    """
    token = job_id_var.set(job_id)
    await websocket.accept()

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()

    try:
        # ── Wait for subscribe message ────────────────────────────────────────
        try:
            subscribe_msg = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10.0  # 10 seconds to send subscribe — then close
            )
        except asyncio.TimeoutError:
            await websocket.send_json({
                "type": "error",
                "job_id": job_id,
                "error": "Did not receive subscribe message within 10 seconds"
            })
            return

        last_seen_ts = subscribe_msg.get("last_event_timestamp")

        # ── Replay missed events ──────────────────────────────────────────────
        if last_seen_ts:
            missed = await _get_events_since(redis, job_id, last_seen_ts)
            for event in missed:
                await websocket.send_json(event)

            # Check if generation is already complete after replay
            final_types = {"generation_complete", "generation_failed"}
            if any(e.get("type") in final_types for e in missed):
                await websocket.send_json({
                    "type": "replay_complete",
                    "job_id": job_id,
                    "message": "All missed events replayed. Generation was already complete.",
                })
                return

        # ── Send connection acknowledgement ───────────────────────────────────
        await websocket.send_json({
            "type": "connected",
            "job_id": job_id,
            "message": "Subscribed to generation stream",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # ── Subscribe to new events ───────────────────────────────────────────
        await pubsub.subscribe(f"ws:job:{job_id}")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                event = json.loads(message["data"])
            except json.JSONDecodeError:
                logger.warning("ws_malformed_event", job_id=job_id)
                continue

            await websocket.send_json(event)

            # Close after terminal events
            if event.get("type") in ("generation_complete", "generation_failed"):
                break

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", job_id=job_id)
    except Exception as e:
        logger.error("ws_error", job_id=job_id, error=str(e))
        try:
            await websocket.send_json({
                "type": "error",
                "job_id": job_id,
                "error": str(e)
            })
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(f"ws:job:{job_id}")
        await pubsub.close()
        await redis.aclose()
        try:
            await websocket.close()
        except Exception:
            pass
        job_id_var.reset(token)


async def _get_events_since(
    redis: aioredis.Redis,
    job_id: str,
    last_seen_ts: str
) -> list[dict]:
    """
    Retrieve WebSocket events stored in Redis list that occurred after
    last_seen_ts. Used for reconnection catch-up.
    """
    try:
        last_dt = datetime.fromisoformat(last_seen_ts.replace("Z", "+00:00"))
    except ValueError:
        return []

    # Get all stored events for this job (newest first — LPUSH order)
    raw_events = await redis.lrange(f"ws:events:{job_id}", 0, -1)

    missed = []
    for raw in reversed(raw_events):  # Oldest first
        try:
            event = json.loads(raw)
            event_ts_str = event.get("timestamp", "")
            if not event_ts_str:
                continue
            event_dt = datetime.fromisoformat(event_ts_str.replace("Z", "+00:00"))
            if event_dt > last_dt:
                missed.append(event)
        except Exception:
            continue

    return missed
