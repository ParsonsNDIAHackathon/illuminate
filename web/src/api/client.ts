const USER = 'local'

export interface EntitySummary {
  id: string
  name: string
  tier: number | string | null
  simulated: boolean
  uei?: string | null
  cage?: string | null
  lei?: string | null
  kind?: string
  source?: string | null
}

export interface OwnershipArtifact {
  id: string
  title?: string
  url?: string
  kind?: string
  source?: string
  retrieved_at?: string
  source_status?: string
  simulated?: boolean
  evidence_id?: string
  evidence_simulated?: boolean
}
async function request<T = any>(method: string, path: string, body?: any, headers?: Record<string, string>, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User': USER, ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch {}
    const safePath = path.split('?')[0]
    const safeDetail = String(detail).replace(/https?:\/\/\S+/gi, '[remote service]').slice(0, 300)
    throw new Error(`${method} ${safePath}: ${safeDetail}`)
  }
  return r.json()
}

export const api = {
  get: <T = any>(p: string, options?: { signal?: AbortSignal }) => request<T>('GET', p, undefined, undefined, options?.signal),
  post: <T = any>(p: string, b?: any, headers?: Record<string, string>) => request<T>('POST', p, b ?? {}, headers),
  put: <T = any>(p: string, b?: any) => request<T>('PUT', p, b ?? {}),
  del: <T = any>(p: string) => request<T>('DELETE', p),
}

export interface ConnectorTestResult {
  ok: boolean
  status: 'available' | 'missing_credentials' | 'authentication' | 'rate_limited' | 'timeout' | 'unavailable'
  detail: string
  diagnostics?: Record<string, boolean | number | string>
}

export type SourceRefreshState = 'connected' | 'refreshing' | 'current' | 'stale-fallback' | 'unavailable' | 'not-applicable' | 'credential-required'
export interface ReadinessContract {
  ok: boolean
  status: 'ready' | 'degraded' | 'unavailable'
  primary_workflow_ready: boolean
  message: string
  graph_counts: { nodes: number; relationships: number }
  required: {
    seed: {
      status: string
      action: string | null
      coverage: { status: string; root_exists: boolean; primes: number; subcontractors: number }
    }
  }
  source_coverage: Array<{ source: string; nodes: number; relationships: number; records: number; latest_retrieved_at: string | null }>
  freshness: { status: 'current' | 'stale' | 'unknown' | 'empty'; latest_retrieved_at: string | null; age_hours: number | null; action?: string | null }
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
  source_url?: string
  method?: string
  detail?: string
  retrieved_at?: string
  first_retrieved_at?: string
  latest_retrieved_at?: string
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
  claim_status?: string
  evidence_refs: string[]
  evidence?: RiskEvidence[]
  explanation?: string
  provenance?: RiskEvidence
  graph_path?: {
    relationship_id?: string
    supplier_id?: string
    consumer_id?: string
  }
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

export type RiskDiligenceFlag = {
  category?: string
  code: string
  message: string
  excluded_truth_statuses?: string[]
  excluded_evidence?: RiskEvidence[]
}
export type VendorRiskProfile = {
  id: string
  name: string
  simulated: boolean
  uei?: string | null
  cage?: string | null
  lei?: string | null
  tier?: number | string | null
  sourceMode: 'live' | 'frozen'
  contract_version: string
  score: number | null
  band: string
  disposition: string
  confidence: number
  completeness: number
  freshness: string
  categories: RiskCategory[]
  diligence_flags: RiskDiligenceFlag[]
}

export type AnalystDispositionAction =
  | 'investigate'
  | 'monitor'
  | 'seek_alternate_source'
  | 'accept_with_rationale'
  | 'close_no_action'

export interface AnalystDecisionEvent {
  id: string
  kind: 'analyst_decision'
  entity_id: string
  disposition: AnalystDispositionAction
  rationale: string
  owner: string
  due_date?: string | null
  actor: string
  decided_at: string
  program_id?: string | null
  finding_ids: string[]
  evidence_refs: string[]
  version: number
  simulated: boolean
}

export interface ClaimReviewEvent {
  id: string
  kind: 'claim_review'
  claim_id: string
  from_status: 'staged'
  to_status: 'committed' | 'rejected'
  rationale?: string | null
  actor: string
  decided_at: string
  version: number
  simulated: boolean
}

export interface DecisionHistory {
  current: AnalystDecisionEvent | null
  events: Array<AnalystDecisionEvent | ClaimReviewEvent>
}

export interface AnalystDecisionInput {
  disposition: AnalystDispositionAction
  rationale: string
  owner: string
  due_date?: string | null
  program_id?: string | null
  finding_ids: string[]
  evidence_refs: string[]
  expected_version: number
}

export function supportedDecisionEvidenceRefs(refs: string[]): string[] {
  return [...new Set(refs.filter(ref => ref.startsWith('clm_') || ref.startsWith('art_')))].sort()
}

function safeEvidenceUrl(value?: string): string | undefined {
  if (!value) return undefined
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? url.toString() : undefined
  } catch {
    return undefined
  }
}

export async function getVendorRiskProfile(id: string, suppliedReport?: any, rootId?: string): Promise<VendorRiskProfile> {
  const report = suppliedReport || await api.get<any>(`/api/entities/${encodeURIComponent(id)}/report?${qs({ root_id: rootId })}`)
  const risk = report.risk || {}
  const evidenceByRef = new Map<string, RiskEvidence>()
  for (const evidence of report.screen_evidence || []) {
    const normalized: RiskEvidence = {
      id: evidence.artifact?.id,
      claim_id: evidence.claim_id,
      source: evidence.source,
      detail: evidence.detail,
      method: evidence.method,
      source_url: safeEvidenceUrl(evidence.source_url || evidence.artifact?.url),
      retrieved_at: evidence.latest_retrieved_at || evidence.retrieved_at,
      confidence: evidence.confidence,
      status: evidence.status,
      truth_status: evidence.status,
      simulated: Boolean(evidence.simulated || evidence.artifact_simulated),
    }
    for (const ref of [evidence.claim_id, evidence.artifact?.id, ...(evidence.artifacts || []).map((a: any) => a.id)]) {
      if (ref) evidenceByRef.set(ref, normalized)
    }
  }
  for (const evidence of report.supply?.risk_evidence || []) {
    for (const artifact of evidence.artifacts || []) {
      const normalized: RiskEvidence = {
        id: artifact.id,
        claim_id: evidence.claim_id,
        source: artifact.source || evidence.source,
        detail: evidence.contract_ref ? `Award ${evidence.contract_ref}` : undefined,
        method: artifact.method || evidence.method,
        source_url: safeEvidenceUrl(artifact.url),
        retrieved_at: artifact.latest_retrieved_at || artifact.retrieved_at || evidence.latest_retrieved_at || evidence.retrieved_at,
        confidence: artifact.confidence ?? evidence.confidence,
        status: evidence.claim_status,
        truth_status: evidence.claim_status,
        simulated: Boolean(evidence.simulated || evidence.claim_simulated || artifact.simulated || artifact.evidence_simulated),
      }
      for (const ref of [evidence.claim_id, evidence.evidence_id, artifact.id]) {
        if (ref) evidenceByRef.set(ref, normalized)
      }
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
        claim_status: factor.claim_status,
        truth_status: 'derived',
        freshness: factor.freshness || 'unavailable',
        evidence: factor.evidence_refs.map(ref => evidenceByRef.get(ref)).filter(Boolean) as RiskEvidence[],
      }))
    })(),
  }))
  return {
    id: report.identity?.id || id,
    name: report.identity?.name || id,
    simulated: Boolean(report.identity?.simulated),
    uei: report.identity?.uei,
    cage: report.identity?.cage,
    lei: report.identity?.lei,
    tier: report.identity?.tier,
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
  control?: {
    direct_parents?: Record<string, unknown>[]
    ultimate_parents?: Record<string, unknown>[]
    ownership?: OwnershipRecord[]
  }
  risk_contract?: EntityRiskContract
  risk?: (Partial<EntityRiskContract> & Record<string, unknown>)
  [key: string]: unknown
}

export interface EntityListResponse {
  items: EntitySummary[]
  total: number
}

export interface Program {
  id: string
  name: string
  agency: string | null
  program_code: string | null
  description: string | null
  source: string
  created_at: string | null
  created_by: string | null
}

export interface ProgramListResponse {
  items: Program[]
  total: number
  limit: number
  offset: number
}

export interface ProgramCreate {
  name: string
  agency?: string
  program_code?: string
  description?: string
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

export interface EnrichmentJob {
  id: string
  entity_id: string
  entity_name?: string | null
  status: string
  created_at: number
  results: Record<string, ConnectorRefreshResult | string>
}
export interface OwnershipRecord {
  owner: { id?: string; name: string; kind: string }
  relationship_type: 'direct' | 'ultimate_parent' | 'beneficial_owner' | 'unknown'
  predicate: string
  percentage: number | null
  effective_date: string | null
  as_of_date: string | null
  relationship: { id?: string; present: boolean }
  claim: {
    id: string
    status: string
    source?: string
    retrieved_at?: string
    method?: string
    confidence?: number
  } | null
  artifacts: OwnershipArtifact[]
  truth_status: string
  freshness: 'current' | 'stale' | 'unavailable'
  conflicting: boolean
  current: boolean
  evidence_present: boolean
  simulated: boolean
}

export interface ConnectorRefreshResult {
  status: SourceRefreshState | 'succeeded' | 'empty' | 'partial' | 'failed' | 'timed_out'
  queried: boolean
  applicable: boolean
  availability?: SourceRefreshState
  refresh_state?: SourceRefreshState
  reason?: string | null
  action?: string | null
  last_success_at?: string | null
  facts?: number
  cache?: boolean
  simulated?: boolean
}
