/**
 * Core types for the layout engine.
 */

export interface Slide {
  slide_id: string
  slide_type: string
  slide_index: number
  action_title: string
  layout_hints: LayoutHints
  content: SlideContent
  outline_context?: OutlineContext
}

export interface LayoutHints {
  priority?: 'text_primary' | 'visual_primary' | 'balanced'
  density?: 'minimal' | 'standard' | 'dense'
  visual_anchor?: 'left' | 'right' | 'center' | 'none'
  suggested_grid_columns?: number
}

export interface SlideContent {
  layout_variant?: string
  bullets?: Bullet[]
  text_position?: 'left' | 'right' | 'overlay'
}

export interface Bullet {
  element_id: string
  text: string
  indent_level?: number
}

export interface OutlineContext {
  parent_section_id?: string
  narrative_framework?: string
}

export interface LayoutElement {
  x: number
  y: number
  width: number
  height: number
  font_size_px: number
  font_size_units: number
  z_index: number
  text_align: 'left' | 'center' | 'right'
}

export interface FrontendLayoutSolution {
  slide_id: string
  relaxation_tier: number
  solve_time_ms: number
  warnings: string[]
  elements: Record<string, LayoutElement>
  font_scale_override?: number
  requires_continuation_slide?: boolean
}

export interface TypographyProfile {
  script: 'latin' | 'cjk' | 'rtl'
  line_height_multiplier: number
  title_to_body_ratio: number
  min_body_font_size_px: number
  max_body_font_size_px: number
  rtl: boolean
  mirror_horizontal: boolean
  text_align: () => 'left' | 'right' | 'center'
}