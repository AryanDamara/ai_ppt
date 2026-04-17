import type { Slide } from '../../../types/deck'

interface TitleSlideProps {
  slide: Slide
}

export function TitleSlide({ slide }: TitleSlideProps) {
  const content = slide.content as {
    headline?: string
    subheadline?: string
    presenter_name?: string
    presenter_title?: string
    date?: string
    event_name?: string
  }

  return (
    <div className="text-center py-12">
      {content.event_name && (
        <p className="text-sm uppercase tracking-wider text-gray-500 mb-4">
          {content.event_name}
        </p>
      )}

      <h1 className="text-4xl font-bold text-gray-900 mb-4">
        {content.headline || 'Untitled Presentation'}
      </h1>

      {content.subheadline && (
        <p className="text-xl text-gray-600 mb-8">
          {content.subheadline}
        </p>
      )}

      <div className="mt-12 text-gray-500">
        {content.presenter_name && (
          <p className="font-medium">{content.presenter_name}</p>
        )}
        {content.presenter_title && (
          <p className="text-sm">{content.presenter_title}</p>
        )}
        {content.date && (
          <p className="text-sm mt-2">{content.date}</p>
        )}
      </div>

      {/* Action title - analyst facing, shown in editor only */}
      <div className="mt-8 pt-8 border-t border-gray-200">
        <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">So What?</p>
        <p className="text-sm text-gray-600 italic">{slide.action_title}</p>
      </div>
    </div>
  )
}
