/**
 * useLayoutEngine — React hook for layout solving with caching and invalidation.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import type { Slide, FrontendLayoutSolution } from '../lib/layout/types'
import { solveSlideInWorker, workerPool } from '../workers/worker-pool'
import { contentHashRegistry, computeImpactRadius, getSlidesToResolve } from '../lib/layout/incremental-solver'

interface LayoutCache {
  [slideId: string]: {
    solution: FrontendLayoutSolution
    timestamp: number
  }
}

interface UseLayoutEngineOptions {
  canvasWidth?: number
  canvasHeight?: number
  debounceMs?: number
}

export function useLayoutEngine(slides: Slide[], options: UseLayoutEngineOptions = {}) {
  const { canvasWidth = 1280, canvasHeight = 720, debounceMs = 50 } = options

  const [solutions, setSolutions] = useState<Record<string, FrontendLayoutSolution>>({})
  const [isSolving, setIsSolving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cacheRef = useRef<LayoutCache>({})
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Initial solve for all slides
  useEffect(() => {
    const solveAll = async () => {
      setIsSolving(true)
      setError(null)

      try {
        const newSolutions: Record<string, FrontendLayoutSolution> = {}

        for (const slide of slides) {
          // Skip if already cached and unchanged
          if (cacheRef.current[slide.slide_id] && !contentHashRegistry.hasChanged(slide)) {
            newSolutions[slide.slide_id] = cacheRef.current[slide.slide_id].solution
            continue
          }

          const solution = await solveSlideInWorker(slide, canvasWidth, canvasHeight, 'low')
          newSolutions[slide.slide_id] = solution
          cacheRef.current[slide.slide_id] = {
            solution,
            timestamp: Date.now(),
          }
          contentHashRegistry.markSolved(slide)
        }

        setSolutions(prev => ({ ...prev, ...newSolutions }))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Layout solve failed')
      } finally {
        setIsSolving(false)
      }
    }

    solveAll()
  }, [slides, canvasWidth, canvasHeight])

  // Re-solve a specific slide
  const resolveSlide = useCallback(async (slideId: string, priority: 'high' | 'low' = 'high') => {
    const slide = slides.find(s => s.slide_id === slideId)
    if (!slide) return

    // Clear debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    debounceTimerRef.current = setTimeout(async () => {
      try {
        const solution = await solveSlideInWorker(slide, canvasWidth, canvasHeight, priority)

        setSolutions(prev => ({
          ...prev,
          [slideId]: solution,
        }))

        cacheRef.current[slideId] = {
          solution,
          timestamp: Date.now(),
        }
        contentHashRegistry.markSolved(slide)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Layout solve failed')
      }
    }, debounceMs)
  }, [slides, canvasWidth, canvasHeight, debounceMs])

  // Get solution for a slide
  const getSolution = useCallback((slideId: string): FrontendLayoutSolution | undefined => {
    return solutions[slideId]
  }, [solutions])

  // Get worker pool stats
  const getWorkerStats = useCallback(() => {
    return workerPool.getStats()
  }, [])

  // Invalidate cache for a slide
  const invalidateSlide = useCallback((slideId: string) => {
    contentHashRegistry.invalidate(slideId)
    delete cacheRef.current[slideId]
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [])

  return {
    solutions,
    isSolving,
    error,
    resolveSlide,
    getSolution,
    getWorkerStats,
    invalidateSlide,
  }
}

export default useLayoutEngine