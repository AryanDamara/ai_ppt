'use client'

interface GenerationProgressProps {
  totalSlides: number
  completedSlides: number
  failedSlides: number
}

export function GenerationProgress({
  totalSlides,
  completedSlides,
  failedSlides,
}: GenerationProgressProps) {
  const progress = totalSlides > 0 ? (completedSlides / totalSlides) * 100 : 0
  const isComplete = completedSlides + failedSlides >= totalSlides

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-5xl mx-auto px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            {!isComplete && (
              <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-900 rounded-full animate-spin" />
            )}
            <span className="text-sm font-medium text-gray-700">
              {isComplete ? 'Generation complete' : 'Generating presentation...'}
            </span>
          </div>
          <span className="text-sm text-gray-500">
            {completedSlides} / {totalSlides} slides
            {failedSlides > 0 && (
              <span className="text-red-500 ml-2">({failedSlides} failed)</span>
            )}
          </span>
        </div>

        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gray-900 transition-all duration-300 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  )
}
