/**
 * Module 6 — Incremental Solver
 * Tracks content hashes and computes impact radius for efficient re-solving.
 */

import type { Slide } from './types'
import type { FrontendLayoutSolution } from './types'

export type ImpactRadius = 'element' | 'slide' | 'section' | 'deck'

export interface ConstraintDelta {
  operation: 'add' | 'remove' | 'edit'
  constraintId: string
  elementId: string
  affectedRadius: ImpactRadius
  previousValue?: unknown
  newValue?: unknown
}

/**
 * Compute a fast content hash for change detection.
 * Not crypto-secure, just fast change detection.
 */
export function computeContentHash(slide: Slide): string {
  const relevant = {
    action_title: slide.action_title,
    slide_type: slide.slide_type,
    content: slide.content,
    layout_hints: slide.layout_hints,
  }
  const str = JSON.stringify(relevant)
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i)
    hash |= 0
  }
  return hash.toString(16)
}

/**
 * Determine which slides need re-solving based on the changed field.
 */
export function computeImpactRadius(
  changedField: string,
  slideIndex: number,
  totalSlides: number,
): ImpactRadius {
  // Deck-level changes: all slides must re-solve
  if (changedField.startsWith('metadata.theme') ||
      changedField.startsWith('metadata.language') ||
      changedField.startsWith('outline_context.narrative_framework')) {
    return 'deck'
  }

  // Section-level: slides in the same section
  if (changedField === 'slide_type') {
    return 'section'
  }

  // Slide-level: only this slide
  if (changedField.startsWith('content.') ||
      changedField.startsWith('layout_hints.') ||
      changedField === 'action_title') {
    return 'slide'
  }

  // Element-level: only one content element within a slide
  if (changedField.match(/content\.bullets\[\d+\]\.text/)) {
    return 'element'
  }

  return 'slide'
}

export function getSlidesToResolve(
  radius: ImpactRadius,
  changedSlideId: string,
  allSlides: Slide[],
  sectionMap: Map<string, string[]>,
): string[] {
  switch (radius) {
    case 'element':
    case 'slide':
      return [changedSlideId]

    case 'section': {
      const changedSlide = allSlides.find(s => s.slide_id === changedSlideId)
      const sectionId = changedSlide?.outline_context?.parent_section_id || changedSlideId
      return sectionMap.get(sectionId) || [changedSlideId]
    }

    case 'deck':
      return allSlides.map(s => s.slide_id)

    default:
      return [changedSlideId]
  }
}

/**
 * Content hash registry — tracks last-known hashes per slide.
 */
export class ContentHashRegistry {
  private hashes = new Map<string, string>()

  hasChanged(slide: Slide): boolean {
    const currentHash = computeContentHash(slide)
    const previousHash = this.hashes.get(slide.slide_id)
    return currentHash !== previousHash
  }

  markSolved(slide: Slide): void {
    this.hashes.set(slide.slide_id, computeContentHash(slide))
  }

  invalidate(slideId: string): void {
    this.hashes.delete(slideId)
  }

  invalidateAll(): void {
    this.hashes.clear()
  }
}

// Global registry instance
export const contentHashRegistry = new ContentHashRegistry()