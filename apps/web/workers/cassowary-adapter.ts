/**
 * Cassowary Adapter — Web Worker interface for layout solving.
 * Uses cassowary-ts for constraint solving in the browser.
 */

import type { Slide, FrontendLayoutSolution, LayoutElement } from '../lib/layout/types'
import { getSlideMetrics, unitsToCssPx } from '../lib/layout/unit-converter'
import { getProfile, shouldMirrorElement, flipXCoordinate } from '../lib/layout/i18n-profiles'

// Import cassowary-ts (dynamically loaded in worker)
let cassowary: typeof import('cassowary-ts') | null = null

export async function initCassowary(): Promise<void> {
  if (!cassowary) {
    cassowary = await import('cassowary-ts')
  }
}

interface ElementVariables {
  x: import('cassowary-ts').Variable
  y: import('cassowary-ts').Variable
  width: import('cassowary-ts').Variable
  height: import('cassowary-ts').Variable
}

interface ZoneBounds {
  x: number
  y: number
  width: number
  height: number
  z_index: number
  text_align: 'left' | 'center' | 'right'
}

const SLIDE_W = 1000
const SLIDE_H = 562

const SAFE_TOP = 72
const SAFE_LEFT = 60
const SAFE_RIGHT = 940

// Template zones for different slide types
const TEMPLATES: Record<string, Record<string, ZoneBounds>> = {
  content_bullets: {
    title: { x: SAFE_LEFT, y: SAFE_TOP, width: 880, height: 80, z_index: 300, text_align: 'left' },
    body: { x: SAFE_LEFT, y: 180, width: 880, height: 480, z_index: 200, text_align: 'left' },
    footer: { x: SAFE_LEFT, y: 710, width: 880, height: 40, z_index: 100, text_align: 'left' },
  },
  visual_split: {
    title: { x: SAFE_LEFT, y: SAFE_TOP, width: 880, height: 80, z_index: 300, text_align: 'left' },
    body: { x: SAFE_LEFT, y: 180, width: 450, height: 480, z_index: 200, text_align: 'left' },
    image: { x: 530, y: 180, width: 410, height: 480, z_index: 150, text_align: 'left' },
    footer: { x: SAFE_LEFT, y: 710, width: 880, height: 40, z_index: 100, text_align: 'left' },
  },
  title_slide: {
    title: { x: SAFE_LEFT, y: 200, width: 880, height: 100, z_index: 300, text_align: 'center' },
    subtitle: { x: SAFE_LEFT, y: 320, width: 880, height: 80, z_index: 200, text_align: 'center' },
    footer: { x: SAFE_LEFT, y: 710, width: 880, height: 40, z_index: 100, text_align: 'left' },
  },
}

export async function solveSlideLayout(
  slide: Slide,
  canvasPxW = 1280,
  canvasPxH = 720,
): Promise<FrontendLayoutSolution> {
  await initCassowary()

  if (!cassowary) {
    throw new Error('Cassowary not initialized')
  }

  const startTime = performance.now()
  const profile = getProfile(slide.layout_hints?.language || 'en')
  const slideType = slide.slide_type
  const template = TEMPLATES[slideType] || TEMPLATES.content_bullets

  const solver = new cassowary.SimplexSolver()
  const elementVars: Record<string, ElementVariables> = {}
  const elements: Record<string, LayoutElement> = {}

  // Create variables for each zone
  for (const [zoneId, bounds] of Object.entries(template)) {
    const effectiveX = shouldMirrorElement(profile, zoneId)
      ? flipXCoordinate(bounds.x, bounds.width, SLIDE_W)
      : bounds.x

    const ev: ElementVariables = {
      x: new cassowary.Variable(`${zoneId}_x`),
      y: new cassowary.Variable(`${zoneId}_y`),
      width: new cassowary.Variable(`${zoneId}_w`),
      height: new cassowary.Variable(`${zoneId}_h`),
    }
    elementVars[zoneId] = ev

    // Suggest values
    solver.addEditVar(ev.x, cassowary.Strength.weak)
    solver.addEditVar(ev.y, cassowary.Strength.weak)
    solver.addEditVar(ev.width, cassowary.Strength.weak)
    solver.addEditVar(ev.height, cassowary.Strength.weak)

    solver.beginEdit()
    solver.suggestValue(ev.x, effectiveX)
    solver.suggestValue(ev.y, bounds.y)
    solver.suggestValue(ev.width, bounds.width)
    solver.suggestValue(ev.height, bounds.height)
    solver.endEdit()
  }

  // Add constraints
  addRequiredConstraints(solver, elementVars, profile)
  addStrongConstraints(solver, elementVars, slide)
  addWeakConstraints(solver, elementVars, slide)

  solver.resolve()

  // Extract results
  for (const [zoneId, ev] of Object.entries(elementVars)) {
    const bounds = template[zoneId]
    const x = Math.round(ev.x.value)
    const y = Math.round(ev.y.value)
    const w = Math.max(20, Math.round(ev.width.value))
    const h = Math.max(10, Math.round(ev.height.value))

    elements[zoneId] = {
      x: Math.max(0, Math.min(x, SLIDE_W - w)),
      y: Math.max(0, Math.min(y, SLIDE_H - h)),
      width: w,
      height: h,
      font_size_px: 18,
      font_size_units: 24,
      z_index: bounds.z_index,
      text_align: bounds.text_align,
    }
  }

  // Layout content elements (bullets)
  if (slide.content?.bullets) {
    const bodyZone = elements.body || elements.body_left
    if (bodyZone) {
      let yCursor = bodyZone.y
      const bulletHeight = 44
      const gap = 12

      for (const bullet of slide.content.bullets) {
        const indent = (bullet.indent_level || 0) * 30
        elements[bullet.element_id] = {
          x: bodyZone.x + indent,
          y: yCursor,
          width: bodyZone.width - indent,
          height: bulletHeight,
          font_size_px: 18,
          font_size_units: 24,
          z_index: 200,
          text_align: profile.text_align(),
        }
        yCursor += bulletHeight + gap
      }
    }
  }

  const solveTime = performance.now() - startTime

  return {
    slide_id: slide.slide_id,
    relaxation_tier: 1,
    solve_time_ms: solveTime,
    warnings: [],
    elements,
  }
}

function addRequiredConstraints(
  solver: import('cassowary-ts').SimplexSolver,
  evars: Record<string, ElementVariables>,
  profile: import('../lib/layout/types').TypographyProfile,
): void {
  if (!cassowary) return

  if (evars.title) {
    solver.addConstraint(
      new cassowary.Constraint(evars.title.y, cassowary.Operators.GEQ, SAFE_TOP, cassowary.Strength.required)
    )
  }

  if (evars.image) {
    solver.addConstraint(
      new cassowary.Constraint(evars.image.width, cassowary.Operators.LEQ, SLIDE_W * 0.45, cassowary.Strength.required)
    )
  }

  for (const ev of Object.values(evars)) {
    solver.addConstraint(
      new cassowary.Constraint(ev.width, cassowary.Operators.GEQ, 20, cassowary.Strength.required)
    )
    solver.addConstraint(
      new cassowary.Constraint(ev.height, cassowary.Operators.GEQ, 10, cassowary.Strength.required)
    )
  }
}

function addStrongConstraints(
  solver: import('cassowary-ts').SimplexSolver,
  evars: Record<string, ElementVariables>,
  slide: Slide,
): void {
  if (!cassowary) return

  // Add text measurement constraints
  if (slide.action_title && evars.title) {
    // Suggest minimum height based on title length
    const minHeight = Math.min(80, 20 + slide.action_title.length / 10)
    solver.addConstraint(
      new cassowary.Constraint(evars.title.height, cassowary.Operators.GEQ, minHeight, cassowary.Strength.strong)
    )
  }
}

function addWeakConstraints(
  solver: import('cassowary-ts').SimplexSolver,
  evars: Record<string, ElementVariables>,
  slide: Slide,
): void {
  if (!cassowary) return

  // Aesthetic preferences
  if (evars.title && evars.body) {
    solver.addConstraint(
      new cassowary.Constraint(evars.body.y, cassowary.Operators.GEQ, evars.title.y.plus(evars.title.height).plus(24), cassowary.Strength.weak)
    )
  }
}