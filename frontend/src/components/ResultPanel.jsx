import ConfidenceBadge from './ConfidenceBadge'
import GeneratedLogicView from './GeneratedLogicView'
import ExplanationPanel from './ExplanationPanel'
import ResultTable from './ResultTable'
import ResultScalar from './ResultScalar'
import FeedbackControls from './FeedbackControls'

export default function ResultPanel({ data }) {
  const { query, generated_logic, result, confidence_score, explanation, meta } = data

  const isScalar = Array.isArray(result) && result.length === 1 && Object.keys(result[0]).length <= 2

  return (
    <div className="result-panel">
      <div className="result-header">
        <h3>{query}</h3>
        <ConfidenceBadge score={confidence_score} breakdown={meta?.confidence_breakdown} />
      </div>

      <GeneratedLogicView sql={generated_logic} />

      {Array.isArray(result) ? (
        isScalar ? (
          <ResultScalar row={result[0]} />
        ) : (
          <ResultTable rows={result} />
        )
      ) : (
        <p className="no-rows">No result (execution failed — see explanation below).</p>
      )}

      <ExplanationPanel explanation={explanation} meta={meta} />

      <FeedbackControls query={query} generatedSql={generated_logic} />
    </div>
  )
}
