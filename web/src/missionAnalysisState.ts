export type MissionAnalysisCompletion = {
  key: string
  template: string
  root: string
  elements: number
}

type MissionAnalysisResult = {
  ok: boolean
  data?: { error?: string }
  subgraph?: { nodes?: unknown[]; edges?: unknown[] }
}

export function missionAnalysisKey(query: Record<string, unknown>) {
  return `${query.mission || ''}:${query.template || ''}:${JSON.stringify(query)}`
}

export function retainMissionCompletion(
  completion: MissionAnalysisCompletion | null,
  key: string,
  supportedTemplate: boolean,
) {
  return supportedTemplate && completion?.key === key ? completion : null
}

export function shouldRunMissionAnalysis(
  completion: MissionAnalysisCompletion | null,
  key: string,
  supportedTemplate: boolean,
) {
  return supportedTemplate && completion?.key !== key
}

export function resolveMissionAnalysis(
  result: MissionAnalysisResult,
  key: string,
  template: string,
  root: string,
  missionLabel: string,
): { completion: MissionAnalysisCompletion | null; error: string } {
  const elements = (result.subgraph?.nodes?.length || 0) + (result.subgraph?.edges?.length || 0)
  if (!result.ok) {
    return {
      completion: null,
      error: result.data?.error || `${missionLabel} analysis could not be completed.`,
    }
  }
  if (!elements) {
    return {
      completion: null,
      error: `${missionLabel} analysis returned no usable graph results.`,
    }
  }
  return {
    completion: { key, template, root, elements },
    error: '',
  }
}