import { useState } from 'react'
import QueryInput from './components/QueryInput'
import ExampleChips from './components/ExampleChips'
import ResultPanel from './components/ResultPanel'
import QueryHistory from './components/QueryHistory'
import { useQuery } from './hooks/useQuery'

const MAX_HISTORY = 20

export default function App() {
  const [text, setText] = useState('')
  const [displayed, setDisplayed] = useState(null)
  const [history, setHistory] = useState([])
  const { loading, error, submit } = useQuery()

  async function handleSubmit(question) {
    const data = await submit(question)
    if (data) {
      setDisplayed(data)
      setHistory((h) => {
        const withoutDupes = h.filter((item) => item.query !== question)
        return [{ id: `${Date.now()}-${question}`, query: question, response: data }, ...withoutDupes].slice(
          0,
          MAX_HISTORY,
        )
      })
    }
  }

  function handleExamplePick(question) {
    setText(question)
    handleSubmit(question)
  }

  function handleHistorySelect(item) {
    setText(item.query)
    setDisplayed(item.response)
  }

  function handleHistoryDelete(id) {
    setHistory((h) => h.filter((item) => item.id !== id))
  }

  return (
    <div className="app">
      <header>
        <h1>Intelligent Analytics Query Engine</h1>
        <p className="subtitle">Ask questions about the sales dataset in plain English.</p>
      </header>

      <QueryInput value={text} onChange={setText} onSubmit={handleSubmit} loading={loading} />
      <ExampleChips onPick={handleExamplePick} disabled={loading} />

      {error && <p className="error-banner">Error: {error}</p>}

      <div className="main-content">
        <div className="result-column">
          {displayed && <ResultPanel data={displayed} />}
          {!displayed && !error && !loading && (
            <p className="empty-state">Ask a question above, or pick an example to get started.</p>
          )}
        </div>
        <QueryHistory history={history} onSelect={handleHistorySelect} onDelete={handleHistoryDelete} />
      </div>
    </div>
  )
}
