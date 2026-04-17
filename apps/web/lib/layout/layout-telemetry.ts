/**
 * Module 10 — Layout Telemetry
 * Frontend metrics tracking for worker pool health and solve performance.
 */

interface FrontendSolveTelemetry {
  slideId: string
  solveTimeMs: number
  relaxationTier: number
  workerIndex: number
  queueDepth: number
}

const TELEMETRY_BATCH_SIZE = 10
const TELEMETRY_FLUSH_MS = 5000

let _batch: FrontendSolveTelemetry[] = []
let _flushTimer: ReturnType<typeof setTimeout> | null = null

function flush(): void {
  if (_flushTimer) {
    clearTimeout(_flushTimer)
    _flushTimer = null
  }

  if (_batch.length === 0) return

  const payload = [..._batch]
  _batch = []

  // Fire and forget — don't await
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || ''
  fetch(`${apiUrl}/api/v1/layout/telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ events: payload }),
    keepalive: true,
  }).catch(() => {})  // Non-fatal
}

export function recordFrontendSolve(t: FrontendSolveTelemetry): void {
  _batch.push(t)

  if (_batch.length >= TELEMETRY_BATCH_SIZE) {
    flush()
  } else if (!_flushTimer) {
    _flushTimer = setTimeout(flush, TELEMETRY_FLUSH_MS)
  }
}

export function flushTelemetry(): void {
  flush()
}