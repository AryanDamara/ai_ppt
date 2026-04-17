/**
 * Module 1 — Unit Converter (DPR-Aware)
 * Frontend version: Converts between layout units and CSS pixels.
 */

export interface SlideMetrics {
  aspectRatio: '4:3' | '16:9'
  unitsW: number
  unitsH: number
  canvasPxW: number
  canvasPxH: number
  dpr: number
}

export const ASPECT_RATIO_HEIGHT: Record<string, number> = { '4:3': 750, '16:9': 562 }
export const PPTX_SLIDE_WIDTH_INCHES = 13.333
export const PPTX_SLIDE_HEIGHT_INCHES = 7.5
export const EMU_PER_INCH = 914400

export function getSlideMetrics(
  aspectRatio: '4:3' | '16:9' = '16:9',
  canvasPxW = 1280,
  canvasPxH = 720,
): SlideMetrics {
  const dpr = typeof window !== 'undefined' ? (window.devicePixelRatio || 1) : 1
  return {
    aspectRatio,
    unitsW: 1000,
    unitsH: ASPECT_RATIO_HEIGHT[aspectRatio],
    canvasPxW,
    canvasPxH,
    dpr,
  }
}

/** CSS logical pixels — use for DOM positioning. */
export function unitsToCssPx(units: number, axis: 'x' | 'y' | 'width' | 'height', m: SlideMetrics): number {
  return axis === 'x' || axis === 'width'
    ? (units / m.unitsW) * m.canvasPxW
    : (units / m.unitsH) * m.canvasPxH
}

/**
 * Physical pixels — use for Canvas API drawing and text measurement.
 * On Retina (DPR=2): 18px logical = 36px physical.
 */
export function unitsToPhysicalPx(units: number, axis: 'x' | 'y' | 'width' | 'height', m: SlideMetrics): number {
  return unitsToCssPx(units, axis, m) * m.dpr
}

/** EMU for PPTX export — NEVER call Inches() from python-pptx directly. */
export function unitsToEmu(units: number, axis: 'x' | 'y' | 'width' | 'height', aspectRatio: '4:3' | '16:9' = '16:9'): number {
  const slideHUnits = ASPECT_RATIO_HEIGHT[aspectRatio]
  const inches = axis === 'x' || axis === 'width'
    ? (units / 1000) * PPTX_SLIDE_WIDTH_INCHES
    : (units / slideHUnits) * PPTX_SLIDE_HEIGHT_INCHES
  return Math.round(inches * EMU_PER_INCH)
}

export function cssPxToUnits(px: number, axis: 'x' | 'y' | 'width' | 'height', m: SlideMetrics): number {
  return axis === 'x' || axis === 'width'
    ? (px / m.canvasPxW) * m.unitsW
    : (px / m.canvasPxH) * m.unitsH
}

/** Font sizes are always height-relative. */
export function fontPxToUnits(fontSizePx: number, m: SlideMetrics): number {
  return (fontSizePx / m.canvasPxH) * m.unitsH
}