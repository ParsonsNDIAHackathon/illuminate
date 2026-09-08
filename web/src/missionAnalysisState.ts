export type MissionAnalysisCompletion = {
  key: string
  template: string
  root: string
  elements: number
  elementIds: string[]
  affected: { id: string; name: string }[]
  hasSimulated: boolean
}

type MissionElement = { id?: string; label?: string; name?: string; props?: Record<string, unknown> }
type MissionEdge = { id?: string; props?: Record<string, unknown> }
type MissionAnalysisResult = {
  ok: boolean
  data?: { error?: string; rows?: { id?: string; name?: string }[] }
  subgraph?: { nodes?: MissionElement[]; edges?: MissionEdge[] }
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

export function extendMissionResultIds(
  current: string[],
  centerId: string,
  edges: { id: string; source: string; target: string }[],
) {
  const incident = edges.filter(edge => edge.source === centerId || edge.target === centerId)
  return [...new Set([
    ...current,
    centerId,
    ...incident.flatMap(edge => [edge.id, edge.source, edge.target]),
  ])]
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
    completion: {
      key, template, root, elements,
      elementIds: [...(result.subgraph?.nodes || []), ...(result.subgraph?.edges || [])].map(item => item.id || '').filter(Boolean),
      affected: (result.data?.rows || [])
        .filter((row, index, rows) => row.id && rows.findIndex(candidate => candidate.id === row.id) === index)
        .map(row => {
          const node = (result.subgraph?.nodes || []).find(candidate => candidate.id === row.id)
          return { id: row.id!, name: row.name || node?.name || row.id! }
        }),
      hasSimulated: [...(result.subgraph?.nodes || []), ...(result.subgraph?.edges || [])].some(item => item.props?.simulated === true),
    },
    error: '',
  }
}