import { z } from 'zod'

// Client-side validation — mirrors backend Pydantic models
// Runs BEFORE sending to API (prevents known-bad requests)
// AND on each slide received from WebSocket (prevents rendering broken slides)

export const GenerateRequestSchema = z.object({
  prompt: z.string().min(10, "Prompt must be at least 10 characters").max(2000),
  theme: z.enum([
    'corporate_dark', 'modern_light', 'startup_minimal',
    'healthcare_clinical', 'financial_formal'
  ]),
  narrative_framework: z.enum([
    'pyramid_principle', 'hero_journey', 'chronological',
    'problem_solution', 'compare_contrast'
  ]).optional(),
  industry_vertical: z.enum([
    'general', 'healthcare', 'financial_services',
    'government', 'technology', 'legal'
  ]).optional(),
  language: z.string().optional(),
  audience: z.string().max(500).optional(),
  client_request_id: z.string().uuid().optional(),
})

export const SlideSchema = z.object({
  slide_id: z.string().uuid(),
  slide_type: z.enum([
    'title_slide', 'content_bullets', 'data_chart',
    'visual_split', 'table', 'section_divider'
  ]),
  slide_index: z.number().int().min(0),
  action_title: z.string().max(60),
  content: z.record(z.unknown()),
  speaker_notes: z.string().optional(),
  outline_context: z.object({
    narrative_role: z.enum([
      'situation', 'complication', 'resolution',
      'action', 'appendix', 'transition'
    ]).optional(),
    hierarchy_level: z.number().int().min(1).max(3).optional(),
    parent_section_id: z.string().optional(),
  }).optional(),
  layout_hints: z.object({
    priority: z.enum(['text_primary', 'visual_primary', 'balanced']).optional(),
    density: z.enum(['minimal', 'standard', 'dense']).optional(),
    visual_anchor: z.enum(['left','right','top','bottom','center','none']).optional(),
    suggested_grid_columns: z.union([z.literal(1), z.literal(2), z.literal(3)]).optional(),
  }).optional(),
  ai_metadata: z.object({
    generation_confidence: z.number().min(0).max(1).optional(),
    alternative_generations: z.array(z.object({
      variant_id: z.string(),
      action_title: z.string(),
      confidence_score: z.number(),
    })).max(3).optional(),
    hallucination_risk_flags: z.array(z.enum([
      'numerical_unverified', 'quote_unsourced',
      'prediction_extrapolated', 'entity_inferred'
    ])).optional(),
    human_review_status: z.enum(['pending','approved','rejected','modified']).optional(),
  }).optional(),
  validation_state: z.object({
    schema_compliant: z.boolean(),
    blocking_errors: z.array(z.string()),
    layout_warnings: z.array(z.string()),
  }).optional(),
})

export type ValidatedSlide = z.infer<typeof SlideSchema>
export type ValidatedGenerateRequest = z.infer<typeof GenerateRequestSchema>

export function validateSlide(raw: unknown): { success: true; data: ValidatedSlide } | { success: false; errors: string[] } {
  const result = SlideSchema.safeParse(raw)
  if (result.success) return { success: true, data: result.data }
  return {
    success: false,
    errors: result.error.issues.map(i => `${i.path.join('.')}: ${i.message}`)
  }
}

export function validateGenerateRequest(raw: unknown): { success: true; data: ValidatedGenerateRequest } | { success: false; errors: string[] } {
  const result = GenerateRequestSchema.safeParse(raw)
  if (result.success) return { success: true, data: result.data }
  return {
    success: false,
    errors: result.error.issues.map(i => `${i.path.join('.')}: ${i.message}`)
  }
}
