import { useState } from 'react'
import { postFeedback } from '../api/client'

export default function FeedbackControls({ query, generatedSql }) {
  const [status, setStatus] = useState('idle') // idle | correcting | submitted
  const [correction, setCorrection] = useState('')
  const [notes, setNotes] = useState('')

  async function handleUp() {
    await postFeedback({ query, generated_sql: generatedSql, rating: 'up' })
    setStatus('submitted')
  }

  function handleDownClick() {
    setStatus('correcting')
  }

  async function handleSubmitCorrection() {
    await postFeedback({
      query,
      generated_sql: generatedSql,
      rating: 'down',
      corrected_sql: correction,
      notes,
    })
    setStatus('submitted')
  }

  if (status === 'submitted') {
    return <p className="feedback-thanks">Thanks for the feedback — it'll help improve future answers.</p>
  }

  if (status === 'correcting') {
    return (
      <div className="feedback-correction">
        <label>
          What should the SQL have been? (optional but helps a lot)
          <textarea
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            rows={2}
            placeholder="Corrected SQL"
          />
        </label>
        <label>
          Notes (optional)
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What went wrong?" />
        </label>
        <button type="button" onClick={handleSubmitCorrection}>
          Submit feedback
        </button>
      </div>
    )
  }

  return (
    <div className="feedback-controls">
      <button type="button" onClick={handleUp} aria-label="Thumbs up">
        👍
      </button>
      <button type="button" onClick={handleDownClick} aria-label="Thumbs down">
        👎
      </button>
    </div>
  )
}
