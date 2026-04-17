import type { Slide, TableCell } from '../../../types/deck'

interface TableSlideProps {
  slide: Slide
}

export function TableSlide({ slide }: TableSlideProps) {
  const content = slide.content as {
    headline?: string
    table_title?: string
    headers: Array<{
      key: string
      label: string
      width_percent: number
      align: 'left' | 'center' | 'right'
    }>
    rows: Array<{
      row_id: string
      cells: Record<string, TableCell>
    }>
    source_citation?: string
    highlight_cells?: Array<{
      row_id: string
      column_key: string
      reason: string
    }>
  }

  const { headers = [], rows = [], table_title, source_citation } = content

  const isHighlighted = (rowId: string, colKey: string) => {
    return content.highlight_cells?.some(
      h => h.row_id === rowId && h.column_key === colKey
    )
  }

  const getChangeIndicator = (indicator?: string) => {
    switch (indicator) {
      case 'up':
        return '↑'
      case 'down':
        return '↓'
      default:
        return ''
    }
  }

  return (
    <div className="py-4">
      {table_title && (
        <h3 className="text-lg font-semibold text-gray-800 mb-4">{table_title}</h3>
      )}

      <h2 className="text-2xl font-bold text-gray-900 mb-6">
        {content.headline || slide.action_title}
      </h2>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-gray-100">
              {headers.map((header) => (
                <th
                  key={header.key}
                  className={`px-4 py-3 text-sm font-semibold text-gray-700 border-b border-gray-300 ${
                    header.align === 'center' ? 'text-center' :
                    header.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                  style={{ width: `${header.width_percent}%` }}
                >
                  {header.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row_id} className="border-b border-gray-200 hover:bg-gray-50">
                {headers.map((header) => {
                  const cell = row.cells[header.key]
                  const highlighted = isHighlighted(row.row_id, header.key)
                  return (
                    <td
                      key={header.key}
                      className={`px-4 py-3 text-sm ${
                        header.align === 'center' ? 'text-center' :
                        header.align === 'right' ? 'text-right' : 'text-left'
                      } ${
                        highlighted ? 'bg-yellow-50 border-2 border-yellow-300' : ''
                      } ${cell?.emphasis ? 'font-semibold' : ''}`}
                    >
                      <span className={cell?.change_indicator === 'up' ? 'text-green-600' : cell?.change_indicator === 'down' ? 'text-red-600' : ''}>
                        {cell?.value}
                        {cell?.change_indicator && cell.change_indicator !== 'neutral' && cell.change_indicator !== 'none' && (
                          <span className="ml-1">{getChangeIndicator(cell.change_indicator)}</span>
                        )}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {source_citation && (
        <p className="text-xs text-gray-500 mt-4">Source: {source_citation}</p>
      )}
    </div>
  )
}
