# AI Presentation Generator

A production-grade AI-powered presentation platform. When a user types a prompt like "Create a pitch deck for a B2B SaaS company targeting enterprise HR teams", the system generates a complete presentation with real-time streaming.

## Phase 1 Features

- **4-Step AI Pipeline**: Intent classification → Outline generation → Content generation → Validation
- **Real-time Streaming**: WebSocket with reconnection catch-up
- **Semantic Caching**: Embedding-based cache for near-identical prompts
- **Production Hardening**: Rate limiting, idempotency, PII redaction, structured logging
- **Block-based Editor**: Tiptap-powered canvas with 6 slide types

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────────┐
│   Next.js   │────▶│   FastAPI   │────▶│           Celery Worker          │
│   (Web UI)  │◀────│   (API)     │◀────│     (4-Step AI Pipeline)        │
└─────────────┘     └─────────────┘     └─────────────────────────────────┘
      │                    │                           │
      │              ┌─────┴─────┐               ┌─────┴─────┐
      │              │   Redis   │               │  OpenAI   │
      │              │  (Queue)  │               │   API     │
      │              └───────────┘               └───────────┘
      │                    │
      │              ┌─────┴─────┐
      │              │ PostgreSQL │
      │              │  (Store)   │
      │              └────────────┘
      │
      ▼
WebSocket (/ws/job/{id})
- Reconnection with event replay
- Per-slide streaming
- Slide-level error handling
```

## Tech Stack

### Backend
- Python 3.11
- FastAPI 0.110.0
- Celery 5.3.6
- SQLAlchemy 2.0.28 (async)
- Redis 5.0.1
- OpenAI 1.14.0

### Frontend
- Next.js 14.1.0 (App Router)
- React 18.2.0
- TypeScript 5.4.2
- Tiptap 2.2.4
- Zustand 4.5.2
- Tailwind CSS 3.4.1

### Infrastructure
- Docker + docker-compose
- PostgreSQL 15
- Redis 7.2

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo>
cd ai-ppt-generator
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Start Infrastructure

```bash
cd infra
docker-compose up -d postgres redis
```

### 3. Start Backend (in new terminal)

```bash
cd apps/api
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Set environment variables from .env
export $(cat ../../.env | grep -v '^#' | xargs)

# Start API server
uvicorn main:app --reload

# In another terminal, start Celery worker:
celery -A workers.celery_app worker --loglevel=info --concurrency=4
```

### 4. Start Frontend (in new terminal)

```bash
cd apps/web
npm install
npm run dev
```

### 5. Or use Docker Compose (everything)

```bash
cd infra
docker-compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/generate` | Submit generation request |
| GET | `/api/v1/job/{job_id}` | Poll job status |
| DELETE | `/api/v1/cache` | Invalidate semantic cache |
| GET | `/health` | Deep health check |
| WS | `/ws/job/{job_id}` | Real-time streaming |

## WebSocket Event Contract

```typescript
// Client sends:
interface SubscribeMessage {
  type: "subscribe"
  job_id: string
  last_event_timestamp: string | null
}

// Server sends:
type StreamEvent =
  | { type: "connected"; job_id: string; message: string }
  | { type: "generation_started"; job_id: string }
  | { type: "pipeline_step"; step: 1|2|3|4; name: string }
  | { type: "slide_ready"; job_id: string; slide: SlideJSON; slide_index: number }
  | { type: "slide_failed"; job_id: string; slide_index: number; error: string }
  | { type: "generation_complete"; job_id: string; deck: PresentationDeck }
  | { type: "generation_failed"; job_id: string; status: "failed" | "partial_failure"; error: string }
```

## Slide Types

1. **title_slide** - Opening slide with headline, subheadline, presenter info
2. **content_bullets** - Bullet points with hierarchy and emphasis
3. **data_chart** - Bar, line, pie charts with series data
4. **visual_split** - Text + image placeholder with keyword
5. **table** - Structured data with headers, rows, highlights
6. **section_divider** - Transition between major sections

## Development

### Directory Structure

```
ai-ppt-generator/
├── apps/
│   ├── api/              # FastAPI + Celery
│   │   ├── core/         # Config, logging, security, prompts
│   │   ├── routers/      # HTTP + WebSocket routes
│   │   ├── services/
│   │   │   ├── orchestration/  # 4-step AI pipeline
│   │   │   ├── cache/          # Semantic cache
│   │   │   └── db/             # Database models
│   │   └── workers/      # Celery tasks
│   └── web/              # Next.js frontend
│       ├── app/          # App router pages
│       ├── components/   # React components
│       │   ├── editor/   # Tiptap canvas
│       │   ├── prompt/   # Input components
│       │   └── ui/       # Shared UI
│       └── hooks/        # Zustand + WebSocket
├── infra/                # Docker, postgres init, redis config
└── packages/schema/      # Shared JSON schema
```

### Running Tests

```bash
# Backend tests
cd apps/api
pytest

# Frontend tests
cd apps/web
npm test
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `RATE_LIMIT_PER_MINUTE` | Requests per minute | 10 |
| `CACHE_SIMILARITY_THRESHOLD` | Semantic cache threshold | 0.92 |
| `ENVIRONMENT` | dev/staging/prod | development |

## Security Features

- **Prompt Injection Detection**: Sanitizes input for common injection patterns
- **PII Redaction**: Automatic redaction of SSNs, emails, credit cards from logs
- **Rate Limiting**: Per-IP rate limiting with slowapi
- **Idempotency**: `client_request_id` prevents duplicate submissions
- **Schema Versioning**: Header-based negotiation prevents incompatible clients

## License

MIT
