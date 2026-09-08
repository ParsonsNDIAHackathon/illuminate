const USER = 'local'

export interface EntitySummary {
  id: string
  name: string
  tier: number | string | null
  simulated: boolean
}
async function request<T = any>(method: string, path: string, body?: any, headers?: Record<string, string>): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User': USER, ...headers },
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
  post: <T = any>(p: string, b?: any, headers?: Record<string, string>) => request<T>('POST', p, b ?? {}, headers),
  put: <T = any>(p: string, b?: any) => request<T>('PUT', p, b ?? {}),
  del: <T = any>(p: string) => request<T>('DELETE', p),
}

export const qs = (o: Record<string, any>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')

export interface CatalogDatasetMetadata {
  event_id: 3
  name: string
  description: string
  source_url: string
  format: 'JSON'
  size_estimate: string | null
  update_frequency: string | null
  access_requirements: string | null
  license_info: string | null
  api_documentation: string | null
  sample_data_url: string | null
  schema_description: string | null
  quality_notes: string | null
  tags: string[]
}
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
  categories: Array<EntityRiskCategoryContract | string>
  diligence_flags: Array<string | Record<string, unknown>>
}

export interface EntityRiskCategoryContract {
  id?: string
  category?: string
  name?: string
  severity?: string | number | null
  score?: number | null
  confidence?: number | null
  freshness?: string | null
  [key: string]: unknown
}

export interface EntityRiskCategoryContract {
  id?: string
  category?: string
  name?: string
  severity?: string | number | null
  score?: number | null
  confidence?: number | null
  freshness?: string | null
  [key: string]: unknown
}

export const ndiaCatalog = {
  preview: () => api.get<CatalogContributionPreview>('/api/catalog/ndia/preview'),
  submit: (confirmationToken: string, dryRun = false, operatorToken?: string) =>
    api.post<CatalogContributionResult>('/api/catalog/ndia/submit', {
      confirm: true,
      confirmation: 'PUBLISH EVENT 3',
      confirmation_token: confirmationToken,
      dry_run: dryRun,
    }, operatorToken ? { 'X-Catalog-Operator': operatorToken } : undefined),
  status: (refresh = false) =>
    api.get<CatalogContributionResult>(`/api/catalog/ndia/status?${qs({ refresh })}`),
}

export interface CatalogContributionPreview {
  export_id: string
  export_version: string
  export_watermark: string
  event: {
    id: 3
    slug: 'ndia-global-defense-hackathon-main-event-washington-dc'
    title: 'NDIA Global Defense Hackathon / Main Event: Washington, DC'
  }
  metadata: CatalogDatasetMetadata
  confirmation_token: string
  schema_valid: true
  publication_ready: boolean
  credential_configured: boolean
  operator_authorization_configured: boolean
  contribution_state: string
  remote_dataset_id: string | null
  message: string
}

export interface CatalogContributionResult {
  export_id: string
  export_version: string
  dataset_id: string | null
  contribution_state: string
  message: string
  dry_run: boolean
  idempotent: boolean
  submitted_at: string | null
  metadata: CatalogDatasetMetadata
}
