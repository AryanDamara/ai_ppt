'use client'

import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { useEffect } from 'react'
import { useDeckStore } from '../../hooks/useDeckStore'
import { useGenerationStream } from '../../hooks/useGenerationStream'
import { SlideNodeExtension } from './SlideNode'
import { GenerationProgress } from '../ui/GenerationProgress'
import { EditorErrorBoundary } from '../ui/ErrorBoundary'

interface DeckCanvasProps { jobId: string }

export function DeckCanvas({ jobId }: DeckCanvasProps) {
  const { slides, generationStatus, failedSlots, error } = useDeckStore()
  useGenerationStream(jobId)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ history: false }),
      SlideNodeExtension,
    ],
    content: { type: 'doc', content: [] },
    editorProps: {
      attributes: { class: 'outline-none min-h-screen' },
    },
  })

  useEffect(() => {
    if (!editor || slides.length === 0) return
    // Slides are sorted by slide_index in the store
    const content = slides.map((slide) => ({
      type: 'slide',
      attrs: {
        slideId: slide.slide_id,       // UUID key
        slideIndex: slide.slide_index,
        slideType: slide.slide_type,
        slideData: slide,
      },
    }))
    editor.commands.setContent({ type: 'doc', content })
  }, [editor, slides])

  return (
    <EditorErrorBoundary>
      <div className="flex flex-col min-h-screen bg-gray-50">
        {generationStatus === 'generating' && (
          <GenerationProgress
            totalSlides={slides.length + failedSlots.length}
            completedSlides={slides.length}
            failedSlides={failedSlots.length}
          />
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 mx-4 mt-4 rounded-lg">
            <p className="text-sm font-medium">Generation error</p>
            <p className="text-sm">{error}</p>
          </div>
        )}

        {failedSlots.map((slot) => (
          <div
            key={`failed-${slot.slideIndex}`}
            className="border border-dashed border-red-300 rounded-lg mx-auto w-full max-w-4xl my-4 p-8 text-center bg-red-50"
          >
            <p className="text-red-600 text-sm font-medium">
              Slide {slot.slideIndex + 1} ({slot.slideType}) failed to generate
            </p>
            <p className="text-red-500 text-xs mt-1">{slot.error}</p>
          </div>
        ))}

        <div className="flex-1 mx-auto w-full max-w-5xl px-4 py-8">
          <EditorContent editor={editor} />
        </div>
      </div>
    </EditorErrorBoundary>
  )
}
