import { Node, mergeAttributes } from '@tiptap/core'
import { ReactNodeViewRenderer, NodeViewWrapper } from '@tiptap/react'
import { TitleSlide } from './slide-renderers/TitleSlide'
import { ContentBullets } from './slide-renderers/ContentBullets'
import { DataChart } from './slide-renderers/DataChart'
import { VisualSplit } from './slide-renderers/VisualSplit'
import { TableSlide } from './slide-renderers/TableSlide'
import { SectionDivider } from './slide-renderers/SectionDivider'
import type { Slide } from '../../types/deck'

const SlideView = ({ node }: { node: { attrs: { slideData: Slide } } }) => {
  const slide = node.attrs.slideData

  const renderSlideContent = () => {
    switch (slide.slide_type) {
      case 'title_slide':
        return <TitleSlide slide={slide} />
      case 'content_bullets':
        return <ContentBullets slide={slide} />
      case 'data_chart':
        return <DataChart slide={slide} />
      case 'visual_split':
        return <VisualSplit slide={slide} />
      case 'table':
        return <TableSlide slide={slide} />
      case 'section_divider':
        return <SectionDivider slide={slide} />
      default:
        return <div className="p-4 text-gray-500">Unknown slide type: {slide.slide_type}</div>
    }
  }

  return (
    <NodeViewWrapper className="slide-node mb-8">
      <div
        className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
        data-slide-id={slide.slide_id}
        data-slide-index={slide.slide_index}
      >
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
          <span className="text-xs font-medium text-gray-500">
            Slide {slide.slide_index + 1}
          </span>
          <span className="text-xs text-gray-400">{slide.slide_type}</span>
        </div>

        <div className="p-6">
          {renderSlideContent()}
        </div>

        {slide.validation_state?.blocking_errors.length > 0 && (
          <div className="px-4 py-2 bg-red-50 border-t border-red-100">
            <p className="text-xs text-red-600 font-medium">Validation errors:</p>
            <ul className="mt-1 text-xs text-red-500">
              {slide.validation_state.blocking_errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </NodeViewWrapper>
  )
}

export const SlideNodeExtension = Node.create({
  name: 'slide',
  group: 'block',
  atom: true,

  addAttributes() {
    return {
      slideId: { default: null },
      slideIndex: { default: 0 },
      slideType: { default: 'content_bullets' },
      slideData: { default: {} },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-slide-id]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-slide-id': HTMLAttributes.slideId })]
  },

  addNodeView() {
    return ReactNodeViewRenderer(SlideView)
  },
})
