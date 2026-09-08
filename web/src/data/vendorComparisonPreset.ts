import type { RiskCategory, VendorRiskProfile } from '../api/client'

const category = (
  id: string, label: string, weight: number, risky: boolean, source: string,
  truth_status = 'committed', freshness = 'current',
): RiskCategory => ({
  id, label, weight,
  severity: risky ? 'high' : 'clear',
  contribution: risky ? weight : 0,
  confidence: risky ? 0.91 : 0.96,
  freshness,
  factors: [{
    rule_id: `uc11.${id}.${risky ? 'high' : 'clear'}`,
    label: risky ? `${label} risk signal` : `${label} clear screen`,
    severity: risky ? 'high' : 'clear',
    contribution: risky ? weight : 0,
    confidence: risky ? 0.91 : 0.96,
    freshness,
    truth_status: 'derived',
    evidence_refs: [`evidence-${id}-${risky ? 'risky' : 'trusted'}`],
    explanation: risky
      ? `A verified high-severity ${label.toLowerCase()} signal contributes the category's full ${weight}-point weight.`
      : `A verified clear result contributes zero risk points; it still counts toward completeness.`,
    evidence: [{
      id: `evidence-${id}-${risky ? 'risky' : 'trusted'}`,
      source,
      detail: risky ? `Frozen UC-11 high-risk ${label.toLowerCase()} finding.` : `Frozen UC-11 clear ${label.toLowerCase()} finding.`,
      retrieved_at: freshness === 'stale' ? '2025-01-15' : '2026-09-01',
      confidence: risky ? 0.91 : 0.96,
      status: truth_status,
      truth_status: truth_status === 'committed' ? 'verified' : truth_status,
      simulated: true,
    }],
  }],
})

const specs: Array<[string, string, number, string]> = [
  ['ownership', 'Ownership', 15, 'GLEIF calibration fixture'],
  ['financial', 'Financial', 15, 'EDGAR calibration fixture'],
  ['legal', 'Legal', 10, 'Court-record calibration fixture'],
  ['sanctions_regulatory', 'Sanctions & regulatory', 20, 'OFAC and SAM calibration fixture'],
  ['cyber', 'Cyber', 15, 'Cyber advisory calibration fixture'],
  ['adverse_media', 'Adverse media', 10, 'GDELT calibration fixture'],
  ['supply_criticality', 'Supply criticality', 15, 'USAspending calibration fixture'],
]

const categories = (risky: boolean) => specs.map(([id, label, weight, source]) =>
  category(id, label, weight, risky, source, 'committed', risky && id === 'adverse_media' ? 'stale' : 'current'))

export const TRUSTWORTHY_RISKY_PRESET: [VendorRiskProfile, VendorRiskProfile] = [
  {
    id: 'uc11-trustworthy-fixture',
    name: 'Atlas Precision Systems',
    simulated: true,
    sourceMode: 'frozen',
    contract_version: 'uc11.vendor-risk.v1',
    score: 0,
    band: 'low',
    disposition: 'standard_monitoring',
    confidence: 0.96,
    completeness: 1,
    freshness: 'current',
    categories: categories(false),
    diligence_flags: [],
  },
  {
    id: 'uc11-risky-fixture',
    name: 'Vanguard Critical Components',
    simulated: true,
    sourceMode: 'frozen',
    contract_version: 'uc11.vendor-risk.v1',
    score: 100,
    band: 'critical',
    disposition: 'hold_and_escalate',
    confidence: 0.91,
    completeness: 1,
    freshness: 'diligence_required',
    categories: categories(true),
    diligence_flags: [{
      category: 'adverse_media',
      code: 'stale_evidence',
      message: 'Adverse media evidence is stale. Refresh before making a final decision.',
    }],
  },
]