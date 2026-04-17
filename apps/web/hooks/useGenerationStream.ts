'use client'

import { useEffect, useRef, useCallback } from 'react'
import { useDeckStore } from './useDeckStore'
import { validateSlide } from '../lib/schema-validator'
import type { Slide, PresentationDeck } from '../types/deck'

export function useGenerationStream(jobId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const lastEventTimestampRef = useRef<string | null>(null)
  const MAX_RECONNECT = 3

  const {
    addSlide, markSlideAsFailed, setGenerationStatus,
    setDeck, setError,
  } = useDeckStore()

  const connect = useCallback(() => {
    if (!jobId) return

    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL}/ws/job/${jobId}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0
      setGenerationStatus('generating')

      // Send subscribe message with last seen timestamp (for reconnection catch-up)
      ws.send(JSON.stringify({
        type: 'subscribe',
        job_id: jobId,
        last_event_timestamp: lastEventTimestampRef.current,
      }))
    }

    ws.onmessage = (event) => {
      let data: { type: string; job_id: string; timestamp?: string; [key: string]: unknown }
      try {
        data = JSON.parse(event.data)
      } catch {
        console.error('[WS] Failed to parse event:', event.data)
        return
      }

      // Track latest event timestamp for reconnection
      if (data.timestamp) {
        lastEventTimestampRef.current = data.timestamp
      }

      switch (data.type) {
        case 'generation_started':
          setGenerationStatus('generating')
          break

        case 'slide_ready': {
          const rawSlide = data.slide as unknown
          const validation = validateSlide(rawSlide)

          if (validation.success) {
            addSlide(validation.data)     // Store sorts by slide_index automatically
          } else {
            console.error('[WS] Slide validation failed:', validation.errors)
            // Add with validation errors marked — don't silently drop
            addSlide({
              ...(rawSlide as Slide),
              validation_state: {
                schema_compliant: false,
                blocking_errors: validation.errors,
                layout_warnings: [],
              },
            })
          }
          break
        }

        case 'slide_failed':
          markSlideAsFailed({
            slideIndex: data.slide_index as number,
            slideType: data.slide_type as string,
            error: data.error as string,
            retryId: data.retry_id as string,
          })
          break

        case 'generation_complete': {
          const deck = data.deck as PresentationDeck
          setDeck(deck)
          setGenerationStatus('complete')
          ws.close(1000, 'Generation complete')
          break
        }

        case 'generation_failed':
          setGenerationStatus(data.status as 'failed' | 'partial_failure')
          setError(data.error as string)
          ws.close(1000, 'Generation failed')
          break

        case 'error':
          setError(data.error as string)
          break

        default:
          // pipeline_step events — use for progress UI if desired
          break
      }
    }

    ws.onclose = (event) => {
      if (event.code === 1000) return  // Normal close

      // Abnormal close — exponential backoff reconnect
      if (reconnectAttemptsRef.current < MAX_RECONNECT) {
        reconnectAttemptsRef.current++
        const delay = 1000 * Math.pow(2, reconnectAttemptsRef.current)
        console.info(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`)
        setTimeout(connect, delay)
      } else {
        setError('Connection lost after 3 attempts. Please refresh and try again.')
        setGenerationStatus('failed')
      }
    }

    ws.onerror = () => {
      // onerror always followed by onclose — let onclose handle reconnect
    }
  }, [jobId, addSlide, markSlideAsFailed, setGenerationStatus, setDeck, setError])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close(1000, 'Component unmounted')
      }
    }
  }, [connect])
}
