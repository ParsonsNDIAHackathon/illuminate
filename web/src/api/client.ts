const USER = 'local'

export interface EntitySummary {
  id: string
  name: string
  tier: number | string | null
  simulated: boolean
}
async function request<T = any>(method: string, path: string, body?: any): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User': USER },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch {}
    throw new Error(`${method} ${path}: ${detail}`)
  }
  return r.json()
}

export const api = {
  get: <T = any>(p: string) => request<T>('GET', p),
  post: <T = any>(p: string, b?: any) => request<T>('POST', p, b ?? {}),
  put: <T = any>(p: string, b?: any) => request<T>('PUT', p, b ?? {}),
  del: <T = any>(p: string) => request<T>('DELETE', p),
}

export const qs = (o: Record<string, any>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')

export type RiskEvidence = {
  id?: string
  claim_id?: string
  evidence_ref?: string
  source?: string
  detail?: string
  retrieved_at?: string
  confidence?: number
  status?: string
  truth_status?: string
  simulated?: boolean
}

export type RiskFactor = {
  rule_id: string
  label?: string
  severity?: string | null
  contribution?: number
  confidence?: number
  freshness?: string
  truth_status?: string
  evidence_refs: string[]
  evidence?: RiskEvidence[]
  explanation?: string
  provenance?: RiskEvidence
}

export type RiskCategory = {
  id: string
  label?: string
  weight: number
  severity: string | null
  contribution: number
  confidence: number
  freshness: string
  factors: RiskFactor[]
}

export type VendorRiskProfile = {
  id: string
  name: string
  simulated: boolean
  sourceMode: 'live' | 'frozen'
  contract_version: string
  score: number | null
  band: string
  disposition: string
  confidence: number
  completeness: number
  freshness: string
  categories: RiskCategory[]
  diligence_flags: Array<{
    category?: string
    code: string
    message: string
    excluded_truth_statuses?: string[]
    excluded_evidence?: RiskEvidence[]
  }>
}

export async function getVendorRiskProfile(id: string): Promise<VendorRiskProfile> {
  const report = await api.get<any>(`/api/entities/${encodeURIComponent(id)}/report`)
  const risk = report.risk || {}
  const evidenceByRef = new Map<string, RiskEvidence>()
  for (const evidence of report.screen_evidence || []) {
    const normalized: RiskEvidence = {
      id: evidence.artifact?.id,
      claim_id: evidence.claim_id,
      source: evidence.source,
      detail: evidence.detail,
      retrieved_at: evidence.retrieved_at,
      confidence: evidence.confidence,
      status: evidence.status,
      truth_status: evidence.status,
      simulated: Boolean(evidence.simulated || evidence.artifact_simulated),
    }
    for (const ref of [evidence.claim_id, evidence.artifact?.id, ...(evidence.artifacts || []).map((a: any) => a.id)]) {
      if (ref) evidenceByRef.set(ref, normalized)
    }
  }
  const categories: RiskCategory[] = (risk.categories || []).map((category: RiskCategory) => ({
    ...category,
    factors: (() => {
      const factors = category.factors || []
      const severityPoints: Record<string, number> = { clear: 0, low: 1, medium: 2, high: 3 }
      const maxSeverity = Math.max(...factors.map(factor => severityPoints[factor.severity || ''] ?? -1), -1)
      const contributors = factors.filter(factor => (severityPoints[factor.severity || ''] ?? -1) === maxSeverity && maxSeverity > 0)
      return factors.map(factor => ({
        ...factor,
        contribution: factor.contribution ?? (contributors.includes(factor) ? category.contribution / contributors.length : 0),
        confidence: factor.confidence ?? factor.provenance?.confidence,
        freshness: factor.freshness ?? category.freshness,
        truth_status: 'derived',
        evidence: factor.evidence_refs.map(ref => evidenceByRef.get(ref)).filter(Boolean) as RiskEvidence[],
      }))
    })(),
  }))
  return {
    id: report.identity?.id || id,
    name: report.identity?.name || id,
    simulated: Boolean(report.identity?.simulated),
    sourceMode: 'live',
    contract_version: risk.contract_version || 'unavailable',
    score: risk.score ?? null,
    band: risk.band || 'not_assessed',
    disposition: risk.disposition || 'complete_diligence',
    confidence: risk.confidence ?? 0,
    completeness: risk.completeness ?? 0,
    freshness: risk.freshness || 'unknown',
    categories,
    diligence_flags: risk.diligence_flags || [],
  }
}

export interface EntityReportContract {
  identity: EntitySummary & Record<string, unknown>
  risk_contract?: EntityRiskContract
  risk?: (Partial<EntityRiskContract> & Record<string, unknown>)
  [key: string]: unknown
}

export interface EntityListResponse {
  items: EntitySummary[]
  total: number
}

export interface EntityRiskContract {
  contract_version: string
  score: number | null
  band: string | null
  disposition: string | null
  confidence: number | null
  completeness: number | null
  freshness: string | number | null
  categories: Array<RiskCategory | string>
  diligence_flags: Array<string | Record<string, unknown>>
}

export interface RiskCategory {
  id?: string
  category?: string
  name?: string
  severity?: string | number | null
  score?: number | null
  confidence?: number | null
  freshness?: string | null
  [key: string]: unknown
}
