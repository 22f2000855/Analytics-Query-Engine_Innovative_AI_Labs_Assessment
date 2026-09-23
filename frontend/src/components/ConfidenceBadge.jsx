function level(score) {
  if (score >= 0.75) return 'high'
  if (score >= 0.4) return 'medium'
  return 'low'
}

export default function ConfidenceBadge({ score, breakdown }) {
  const tooltip = breakdown
    ? [
        `LLM self-confidence: ${breakdown.llm_confidence}`,
        `Repair attempts: ${breakdown.repair_count} (penalty x${breakdown.repair_penalty.toFixed(2)})`,
        breakdown.empty_result_penalty_applied ? 'Empty-result penalty applied' : null,
        breakdown.unresolved_entity_penalty_applied
          ? `Unresolved entities: ${breakdown.unresolved_entities}`
          : null,
      ]
        .filter(Boolean)
        .join('\n')
    : ''

  return (
    <span className={`confidence-badge confidence-${level(score)}`} title={tooltip}>
      Confidence: {score.toFixed(2)}
    </span>
  )
}
