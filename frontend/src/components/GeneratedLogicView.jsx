import { useState } from 'react'

export default function GeneratedLogicView({ sql }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(sql).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="generated-logic">
      <div className="generated-logic-header">
        <span>Generated SQL</span>
        <button type="button" onClick={handleCopy}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre>
        <code>{sql}</code>
      </pre>
    </div>
  )
}
