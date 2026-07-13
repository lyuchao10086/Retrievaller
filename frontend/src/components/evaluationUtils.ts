import type { Evaluation } from "@/types/evaluation"

type ScoreKey = keyof Pick<
  Evaluation,
  "faithfulness_score" | "relevance_score" | "citation_score" | "completeness_score" | "overall_score"
>

type EvaluationMetric = {
  label: string
  value: number
  key: string
}

type EvaluationDimension = {
  label: string
  value: number
}

const metrics: Array<Omit<EvaluationMetric, "value"> & { scoreKey: ScoreKey }> = [
  { label: "忠实度", key: "Faithfulness", scoreKey: "faithfulness_score" },
  { label: "回答相关性", key: "Answer Relevance", scoreKey: "relevance_score" },
  { label: "完整性", key: "Completeness", scoreKey: "completeness_score" },
  { label: "引用准确率", key: "Citation Accuracy", scoreKey: "citation_score" }
]

const dimensions: Array<Omit<EvaluationMetric, "value"> & { scoreKey: ScoreKey }> = [
  { label: "Faithfulness", key: "Faithfulness", scoreKey: "faithfulness_score" },
  { label: "Answer Relevance", key: "Answer Relevance", scoreKey: "relevance_score" },
  { label: "Citation Accuracy", key: "Citation Accuracy", scoreKey: "citation_score" },
  { label: "Completeness", key: "Completeness", scoreKey: "completeness_score" },
  { label: "Overall", key: "Overall", scoreKey: "overall_score" }
]

export function buildEvaluationMetrics(evaluations: Evaluation[]): EvaluationMetric[] {
  return metrics.map(({ scoreKey, ...metric }) => ({
    ...metric,
    value: averageScore(evaluations, scoreKey)
  }))
}

export function buildEvaluationDimensions(evaluations: Evaluation[]): EvaluationDimension[] {
  return dimensions.map(({ scoreKey, key: _key, ...dimension }) => ({
    ...dimension,
    value: averageScore(evaluations, scoreKey)
  }))
}

function averageScore(evaluations: Evaluation[], scoreKey: ScoreKey): number {
  if (evaluations.length === 0) return 0
  const total = evaluations.reduce((sum, evaluation) => sum + evaluation[scoreKey], 0)
  return Math.round((total / evaluations.length) * 20)
}
