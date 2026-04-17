export type GenerationStatus =
  | 'draft' | 'generating' | 'complete'
  | 'partial_failure' | 'failed' | 'archived'

export type SlideType =
  | 'title_slide' | 'content_bullets' | 'data_chart'
  | 'visual_split' | 'table' | 'section_divider'

export type NarrativeRole =
  | 'situation' | 'complication' | 'resolution'
  | 'action' | 'appendix' | 'transition'

export type HallucinationFlag =
  | 'numerical_unverified' | 'quote_unsourced'
  | 'prediction_extrapolated' | 'entity_inferred'

export type HumanReviewStatus = 'pending' | 'approved' | 'rejected' | 'modified'

export type Theme =
  | 'corporate_dark' | 'modern_light' | 'startup_minimal'
  | 'healthcare_clinical' | 'financial_formal'

export type IndustryVertical =
  | 'general' | 'healthcare' | 'financial_services'
  | 'government' | 'technology' | 'legal'

export interface Bullet {
  element_id: string   // UUID — use as React key, NEVER use text or index
  text: string
  indent_level: 0 | 1 | 2
  emphasis?: 'none' | 'highlight' | 'bold' | 'critical' | 'subtle'
  supporting_data?: string
}

export interface ChartSeries {
  name: string
  values: number[]     // Numbers only — never strings
  color?: string
  unit?: string
}

export interface TableCell {
  value: string
  numeric_value?: number
  emphasis?: boolean
  change_indicator?: 'up' | 'down' | 'neutral' | 'none'
}

export interface Slide {
  slide_id: string     // UUID — ALWAYS use as React key
  slide_type: SlideType
  slide_index: number  // ALWAYS sort by this — slides arrive out of order
  action_title: string // Max 60 chars — analyst So What?, NOT shown to audience
  content: Record<string, unknown>
  speaker_notes?: string
  outline_context?: {
    hierarchy_level?: 1 | 2 | 3
    narrative_role?: NarrativeRole
    parent_section_id?: string
    estimated_duration_seconds?: number
  }
  layout_hints?: {
    priority?: 'text_primary' | 'visual_primary' | 'balanced'
    density?: 'minimal' | 'standard' | 'dense'
    visual_anchor?: 'left' | 'right' | 'top' | 'bottom' | 'center' | 'none'
    suggested_grid_columns?: 1 | 2 | 3
  }
  ai_metadata?: {
    generation_confidence?: number
    alternative_generations?: Array<{
      variant_id: string
      action_title: string
      confidence_score: number
    }>
    hallucination_risk_flags?: HallucinationFlag[]
    human_review_status?: HumanReviewStatus
  }
  validation_state?: {
    schema_compliant: boolean
    blocking_errors: string[]
    layout_warnings: string[]
  }
}

export interface PresentationDeck {
  schema_version: '1.0.0'
  presentation_id: string
  metadata: {
    title: string
    subtitle?: string
    audience?: string
    theme: Theme
    industry_vertical?: IndustryVertical
    language?: string
  }
  generation_metadata: {
    created_at: string
    model_version: string
    generation_status: GenerationStatus
    pipeline_version?: string
    job_id?: string
  }
  outline_context?: {
    narrative_framework?: string
    total_slides_projected?: number
  }
  validation_state?: {
    schema_compliant: boolean
    blocking_errors: string[]
    layout_warnings: string[]
  }
  slides: Slide[]
}
