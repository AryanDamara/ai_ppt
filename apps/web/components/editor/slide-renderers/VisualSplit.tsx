import type { Slide } from '../../../types/deck'

interface VisualSplitProps {
  slide: Slide
}

export function VisualSplit({ slide }: VisualSplitProps) {
  const content = slide.content as {
    headline?: string
    supporting_text: string
    image_keyword?: string
    alt_text?: string
    text_position?: 'left' | 'right' | 'overlay'
    image_treatment?: 'original' | 'monochrome' | 'duotone' | 'gradient_overlay'
  }

  const textPosition = content.text_position || 'left'

  return (
    <div className="py-4">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">
        {content.headline || slide.action_title}
      </h2>

      <div className={`grid gap-6 ${
        textPosition === 'overlay' ? 'grid-cols-1' : 'grid-cols-2'
      }`}>
        {/* Text Content */}
        <div className={textPosition === 'right' ? 'order-2' : 'order-1'}>
          <p className="text-gray-700 leading-relaxed">
            {content.supporting_text}
          </p>
        </div>

        {/* Image Placeholder */}
        <div className={textPosition === 'right' ? 'order-1' : 'order-2'}>
          <div
            className={`
              bg-gray-200 rounded-lg h-64 flex items-center justify-center
              ${content.image_treatment === 'monochrome' ? 'grayscale' : ''}
              ${content.image_treatment === 'duotone' ? 'sepia' : ''}
            `}
          >
            <div className="text-center p-8">
              <div className="text-4xl mb-2">🖼️</div>
              <p className="text-sm text-gray-500 font-medium">
                {content.image_keyword || 'Image placeholder'}
              </p>
              {content.alt_text && (
                <p className="text-xs text-gray-400 mt-1">Alt: {content.alt_text}</p>
              )}
              <p className="text-xs text-gray-400 mt-2">
                (Phase 1: keyword stored for Phase 2 image fetching)
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
