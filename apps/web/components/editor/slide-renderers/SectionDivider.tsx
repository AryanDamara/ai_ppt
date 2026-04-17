import type { Slide } from '../../../types/deck'

interface SectionDividerProps {
  slide: Slide
}

export function SectionDivider({ slide }: SectionDividerProps) {
  const content = slide.content as {
    section_title: string
    section_number?: string
    transition_quote?: string
    preview_bullets?: string[]
  }

  return (
    <div className="py-16 text-center">
      {content.section_number && (
        <p className="text-6xl font-bold text-gray-200 mb-4">
          {content.section_number}
        </p>
      )}

      <h2 className="text-3xl font-bold text-gray-900 mb-6">
        {content.section_title}
      </h2>

      {content.transition_quote && (
        <blockquote className="text-xl text-gray-600 italic max-w-2xl mx-auto mb-8">
          "{content.transition_quote}"
        </blockquote>
      )}

      {content.preview_bullets && content.preview_bullets.length > 0 && (
        <div className="mt-8">
          <p className="text-sm text-gray-500 mb-3">Coming up:</p>
          <ul className="space-y-2">
            {content.preview_bullets.map((bullet, idx) => (
              <li key={idx} className="text-gray-700">
                {bullet}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action title - analyst facing */}
      <div className="mt-12 pt-8 border-t border-gray-200">
        <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Section Insight</p>
        <p className="text-sm text-gray-600 italic">{slide.action_title}</p>
      </div>
    </div>
  )
}
