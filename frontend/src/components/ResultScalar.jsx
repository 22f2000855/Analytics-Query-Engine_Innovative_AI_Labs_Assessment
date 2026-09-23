export default function ResultScalar({ row }) {
  const entries = Object.entries(row)
  return (
    <div className="result-scalar">
      {entries.map(([key, value]) => (
        <div key={key} className="stat-tile">
          <div className="stat-value">{String(value)}</div>
          <div className="stat-label">{key}</div>
        </div>
      ))}
    </div>
  )
}
