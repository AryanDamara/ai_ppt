import type { Slide, Bullet } from '../../../types/deck'

interface ContentBulletsProps {
  slide: Slide
}

export function ContentBullets({ slide }: ContentBulletsProps) {
  const content = slide.content as {
    layout_variant?: 'single_column' | 'two_column' | 'three_column' | 'pyramid'
    bullets: Bullet[]
  }

  const bullets = content.bullets || []
  const layout = content.layout_variant || 'single_column'

  const getEmphasisClass = (emphasis?: string) => {
    switch (emphasis) {
      case 'highlight':
        return 'bg-yellow-50 border-l-4 border-yellow-400 pl-3'
      case 'bold':
        return 'font-bold'
      case 'critical':
        return 'text-red-600 font-semibold'
      case 'subtle':
        return 'text-gray-500 text-sm'
      default:
        return ''
    }
  }

  const getIndentClass = (level: number) => {
    switch (level) {
      case 1:
        return 'ml-4'
      case 2:
        return 'ml-8'
      default:
        return ''
    }
  }

  return (
    <div className="py-4">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">
        {(slide.content as { headline?: string }).headline || slide.action_title}
      </h2>

      <ul className={`space-y-3 ${
        layout === 'two_column' ? 'grid grid-cols-2 gap-4' :
        layout === 'three_column' ? 'grid grid-cols-3 gap-4' : ''
      }`}>
        {bullets.map((bullet) => (
          <li
            key={bullet.element_id}
            className={`flex items-start gap-2 ${getIndentClass(bullet.indent_level || 0)} ${getEmphasisClass(bullet.emphasis)}`}
          >
            <span className="text-gray-400 mt-1">•</span>
            <div className="flex-1">
              <span className="text-gray-800">{bullet.text}</span>
              {bullet.supporting_data && (
                <span className="ml-2 text-sm text-gray-500 font-medium">
                  {bullet.supporting_data}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>

      {slide.speaker_notes && (
        <div className="mt-8 p-4 bg-gray-50 rounded text-sm text-gray-600">
          <p className="font-medium text-gray-500 mb-1">Speaker Notes:</p>
          {slide.speaker_notes}
        </div>
      )}
    </div>
  )
}
