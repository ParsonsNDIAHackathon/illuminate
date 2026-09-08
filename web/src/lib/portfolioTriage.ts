export interface TrustworthyAssessment {
  score: number | null | undefined
  confidence: number | null | undefined
  completeness: number | null | undefined
}

function percent(value: number | null | undefined) {
  if (value == null) return -1
  return Math.round(value <= 1 ? value * 100 : value)
}

export function compareTrustworthy(a: TrustworthyAssessment, b: TrustworthyAssessment) {
  return (a.score ?? Infinity) - (b.score ?? Infinity)
    || percent(b.confidence) - percent(a.confidence)
    || percent(b.completeness) - percent(a.completeness)
}