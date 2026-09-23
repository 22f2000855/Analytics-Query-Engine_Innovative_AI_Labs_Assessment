export default function QueryInput({ value, onChange, onSubmit, loading }) {
  function handleSubmit(e) {
    e.preventDefault()
    if (value.trim() && !loading) {
      onSubmit(value.trim())
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e)
    }
  }

  function handleClear() {
    onChange('')
  }

  return (
    <div className="input-card">
      <h3 className="input-card-title">Ask Your Question</h3>
      <form onSubmit={handleSubmit}>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g., What were the total sales in India for March? Show me the top 2 cities by profit..."
          rows={3}
        />
        <div className="input-card-actions">
          <button type="submit" disabled={loading || !value.trim()}>
            {loading ? 'Thinking…' : 'Ask'}
          </button>
          <button type="button" className="clear-btn" onClick={handleClear} disabled={loading || !value}>
            Clear
          </button>
        </div>
      </form>
    </div>
  )
}
