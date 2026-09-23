import { useEffect, useState } from 'react'

const PAGE_SIZE = 5

export default function QueryHistory({ history, onSelect, onDelete }) {
  const [page, setPage] = useState(1)
  const totalPages = Math.max(1, Math.ceil(history.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)

  // Keep the page in range as items get deleted out from under it.
  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  if (history.length === 0) return null

  const start = (currentPage - 1) * PAGE_SIZE
  const pageItems = history.slice(start, start + PAGE_SIZE)

  return (
    <div className="query-history">
      <h4>History</h4>
      <ul>
        {pageItems.map((item) => (
          <li key={item.id}>
            <button type="button" className="history-item" onClick={() => onSelect(item)} title={item.query}>
              {item.query}
            </button>
            <button
              type="button"
              className="history-delete"
              onClick={() => onDelete(item.id)}
              aria-label={`Delete "${item.query}"`}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      {totalPages > 1 && (
        <div className="history-pagination">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              type="button"
              className={p === currentPage ? 'page-btn active' : 'page-btn'}
              onClick={() => setPage(p)}
            >
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
