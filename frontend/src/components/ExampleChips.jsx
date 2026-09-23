import { useEffect, useState } from 'react'
import { getExamples } from '../api/client'

export default function ExampleChips({ onPick, disabled }) {
  const [examples, setExamples] = useState([])

  useEffect(() => {
    getExamples()
      .then((data) => setExamples(data.map((d) => d.query)))
      .catch(() => setExamples([]))
  }, [])

  if (examples.length === 0) return null

  return (
    <div className="example-chips">
      {examples.map((q) => (
        <button key={q} type="button" className="chip" disabled={disabled} onClick={() => onPick(q)}>
          {q}
        </button>
      ))}
    </div>
  )
}
