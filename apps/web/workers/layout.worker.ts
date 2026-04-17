/**
 * Layout Web Worker
 * Runs Cassowary layout solving off the main thread.
 */

import * as Comlink from 'comlink'
import { initCassowary, solveSlideLayout } from './cassowary-adapter'
import type { Slide, FrontendLayoutSolution } from '../lib/layout/types'
import { recordFrontendSolve } from '../lib/layout/layout-telemetry'

interface SolveRequest {
  slide: Slide
  canvasPxW: number
  canvasPxH: number
  priority: 'high' | 'low'
  workerIndex: number
}

interface SolveResponse {
  solution: FrontendLayoutSolution
  success: boolean
  error?: string
}

class LayoutWorker {
  private initialized = false
  private workerIndex: number

  constructor(index = 0) {
    this.workerIndex = index
  }

  async init(): Promise<void> {
    if (!this.initialized) {
      await initCassowary()
      this.initialized = true
    }
  }

  async solveSlide(request: SolveRequest): Promise<SolveResponse> {
    try {
      await this.init()

      const startTime = performance.now()
      const solution = await solveSlideLayout(
        request.slide,
        request.canvasPxW,
        request.canvasPxH,
      )
      const solveTimeMs = performance.now() - startTime

      // Record telemetry
      recordFrontendSolve({
        slideId: request.slide.slide_id,
        solveTimeMs,
        relaxationTier: solution.relaxation_tier,
        workerIndex: this.workerIndex,
        queueDepth: 0,
      })

      return {
        solution,
        success: true,
      }
    } catch (error) {
      return {
        solution: null as any,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      }
    }
  }

  isInitialized(): boolean {
    return this.initialized
  }

  setWorkerIndex(index: number): void {
    this.workerIndex = index
  }
}

// Expose to Comlink
Comlink.expose(LayoutWorker)

export type { LayoutWorker, SolveRequest, SolveResponse }