/**
 * Layout Engine v2.0 — Frontend exports
 */

// Types
export type {
  Slide,
  LayoutHints,
  SlideContent,
  Bullet,
  OutlineContext,
  LayoutElement,
  FrontendLayoutSolution,
  TypographyProfile,
} from './types'

// Unit conversion
export {
  getSlideMetrics,
  unitsToCssPx,
  unitsToPhysicalPx,
  unitsToEmu,
  cssPxToUnits,
  fontPxToUnits,
  ASPECT_RATIO_HEIGHT,
} from './unit-converter'

// i18n profiles
export {
  LATIN,
  CJK,
  RTL,
  getProfile,
  shouldMirrorElement,
  flipXCoordinate,
  flipVisualAnchor,
  NEVER_MIRROR_ELEMENT_TYPES,
  NON_DIRECTIONAL_ICONS,
  DIRECTIONAL_ICONS,
} from './i18n-profiles'

// Incremental solver
export {
  computeContentHash,
  computeImpactRadius,
  getSlidesToResolve,
  ContentHashRegistry,
  contentHashRegistry,
  type ImpactRadius,
  type ConstraintDelta,
} from './incremental-solver'

// Undo manager
export {
  UndoManager,
  MoveElementCommand,
  UpdateBulletTextCommand,
  ResizeElementCommand,
  undoManager,
  type LayoutCommand,
} from './undo-manager'

// Font loader
export {
  loadFont,
  preloadThemeFonts,
  areFontsLoaded,
  getLoadedFont,
  clearFontCache,
} from './font-loader'

// Autosave
export {
  saveLayoutSnapshot,
  recoverLayoutSnapshot,
  clearLayoutSnapshot,
  setupAutosave,
} from './autosave'

// Telemetry
export {
  recordFrontendSolve,
  flushTelemetry,
} from './layout-telemetry'
