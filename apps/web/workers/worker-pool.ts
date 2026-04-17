/"**
 * Worker Pool — Manages multiple layout worker threads.
 * Uses Comlink for transparent communication with workers.
 */

import * as Comlink from 'comlink'
import type { LayoutWorker, SolveRequest, SolveResponse } from './layout.worker'
import type { Slide, FrontendLayoutSolution } from '../lib/layout/types'
import { recordFrontendSolve } from '../lib/layout/layout-telemetry'

type WorkerWrapper = {
  worker: Worker
  proxy: Comlink.Remote<LayoutWorker>
  busy: boolean
  index: number
}

class WorkerPool {
  private workers: WorkerWrapper[] = []
  private queue: Array<{ request: SolveRequest; resolve: (r: SolveResponse) => void; reject: (e: Error) => void }> = []
  private maxWorkers: number
  private initialized = false

  constructor() {
    // Use navigator.hardwareConcurrency - 1, min 1, max 8
    this.maxWorkers = typeof navigator !== 'undefined'
      ? Math.max(1, Math.min(8, navigator.hardwareConcurrency - 1))
      : 2
  }

  async init(): Promise<void> {
    if (this.initialized) return

    const workerPromises: Promise<void>[] = []

    for (let i = 0; i < this.maxWorkers; i++) {
      workerPromises.push(this.createWorker(i))
    }

    await Promise.all(workerPromises)
    this.initialized = true
  }

  private async createWorker(index: number): Promise<void> {
    try {
      const worker = new Worker(new URL('./layout.worker.ts', import.meta.url), { type: 'module' })
      const proxy = Comlink.wrap<LayoutWorker>(worker)

      const wrapper: WorkerWrapper = {
        worker,
        proxy,
        busy: false,
        index,
      }

      await proxy.setWorkerIndex(index)
      await proxy.init()

      this.workers.push(wrapper)
    } catch (error) {
      console.error(`Failed to create worker ${index}:`, error)
    }
  }

  async solveSlide(
    slide: Slide,
    canvasPxW = 1280,
    canvasPxH = 720,
    priority: 'high' | 'low' = 'low',
  ): Promise<FrontendLayoutSolution> {
    await this.init()

    return new Promise((resolve, reject) => {
      const request: SolveRequest = {
        slide,
        canvasPxW,
        canvasPxH,
        priority,
        workerIndex: 0,
      }

      this.queue.push({
        request,
        resolve: (response) => {
          if (response.success) {
            resolve(response.solution)
          } else {
            reject(new Error(response.error || 'Unknown error'))
          }
        },
        reject,
      })

      this.processQueue()
    })
  }

  private processQueue(): void {
    if (this.queue.length === 0) return

    // Find available worker
    const availableWorker = this.workers.find(w => !w.busy)
    if (!availableWorker) return

    // Get next request (high priority first)
    const highPriorityIndex = this.queue.findIndex(item => item.request.priority === 'high')
    const queueIndex = highPriorityIndex >= 0 ? highPriorityIndex : 0
    const next = this.queue[queueIndex]

    if (!next) return

    this.queue.splice(queueIndex, 1)
    availableWorker.busy = true

    // Update worker index in request
    next.request.workerIndex = availableWorker.index

    availableWorker.proxy.solveSlide(next.request).then((response) => {
      availableWorker.busy = false
      next.resolve(response)
      this.processQueue()
    }).catch((error) => {
      availableWorker.busy = false
      next.reject(error)
      this.processQueue()
    })
  }

  getStats(): { total: number; busy: number; queueDepth: number } {
    return {
      total: this.workers.length,
      busy: this.workers.filter(w => w.busy).length,
      queueDepth: this.queue.length,
    }
  }

  terminate(): void {
    for (const wrapper of this.workers) {
      wrapper.worker.terminate()
    }
    this.workers = []
    this.queue = []
    this.initialized = false
  }
}

// Singleton pool
export const workerPool = new WorkerPool()

// Convenience function
export async function solveSlideInWorker(
  slide: Slide,
  canvasPxW = 1280,
  canvasPxH = 720,
  priority: 'high' | 'low' = 'low',
): Promise<FrontendLayoutSolution> {
  return workerPool.solveSlide(slide, canvasPxW, canvasPxH, priority)
}