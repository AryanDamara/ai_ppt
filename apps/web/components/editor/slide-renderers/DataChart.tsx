import type { Slide, ChartSeries } from '../../../types/deck'

interface DataChartProps {
  slide: Slide
}

export function DataChart({ slide }: DataChartProps) {
  const content = slide.content as {
    headline?: string
    chart_type?: string
    key_takeaway_callout?: string
    chart_data?: {
      series: ChartSeries[]
      categories: string[]
      global_unit?: string
      data_source?: string
    }
    chart_options?: {
      show_legend?: boolean
      show_data_labels?: boolean
    }
  }

  const { chart_data, key_takeaway_callout, chart_type } = content
  const series = chart_data?.series || []
  const categories = chart_data?.categories || []

  // Calculate max value for scaling
  const maxValue = Math.max(
    ...series.flatMap(s => s.values),
    1
  )

  return (
    <div className="py-4">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">
        {content.headline || slide.action_title}
      </h2>

      {key_takeaway_callout && (
        <p className="text-lg text-gray-600 mb-6 italic">{key_takeaway_callout}</p>
      )}

      {/* Chart Placeholder - Phase 1 uses simple bars */}
      <div className="bg-gray-50 rounded-lg p-6">
        <div className="space-y-4">
          {series.map((s, seriesIdx) => (
            <div key={seriesIdx}>
              <p className="text-sm font-medium text-gray-700 mb-2">{s.name}</p>
              <div className="grid gap-2"
              >
                {s.values.map((value, idx) => {
                  const width = maxValue > 0 ? (value / maxValue) * 100 : 0
                  return (
                    <div key={idx} className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 w-20 truncate">
                        {categories[idx] || `Item ${idx + 1}`}
                      </span>
                      <div className="flex-1 h-6 bg-gray-200 rounded overflow-hidden">
                        <div
                          className="h-full bg-blue-500 transition-all duration-300"
                          style={{ width: `${width}%`, backgroundColor: s.color || undefined }}
                        />
                      </div>
                      <span className="text-xs font-medium text-gray-700 w-16 text-right">
                        {value}{s.unit || chart_data?.global_unit || ''}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        {chart_data?.data_source && (
          <p className="text-xs text-gray-500 mt-4">
            Source: {chart_data.data_source}
          </p>
        )}
      </div>

      <div className="mt-4 text-xs text-gray-400">
        Chart type: {chart_type || 'bar'} (Phase 1: simplified visualization)
      </div>
    </div>
  )
}
