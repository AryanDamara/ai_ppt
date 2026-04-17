from sqlalchemy import Column, String, Integer, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from services.db.session import Base
import uuid


class Deck(Base):
    __tablename__ = "decks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    presentation_id = Column(UUID(as_uuid=True), unique=True, nullable=False)
    job_id = Column(String(255), unique=True)
    client_request_id = Column(String(255), unique=True, nullable=True)  # Idempotency
    generation_status = Column(String(50), nullable=False, default="draft")
    schema_version = Column(String(10), nullable=False, default="1.0.0")
    deck_json = Column(JSONB, nullable=False, default={})
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Numeric(10, 6), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    modified_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WsEvent(Base):
    """Persisted WebSocket events for reconnection catch-up."""
    __tablename__ = "ws_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    event_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
