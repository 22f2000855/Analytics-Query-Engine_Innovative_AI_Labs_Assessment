export default function ExplanationPanel({ explanation }) {
  return (
    <div className="explanation-panel">
      <h4>Explanation</h4>
      {explanation.split('\n').map((line, i) => (
        <p key={i}>{line}</p>
      ))}
    </div>
  )
}
