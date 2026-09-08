<template>
  <main class="portfolio">
    <header class="brief-head">
      <div>
        <div class="eyebrow">ACQUISITION INTELLIGENCE / PORTFOLIO TRIAGE</div>
        <h1>Vendor risk, separated from evidence quality.</h1>
         <p>Ranked operational view of {{ loadedCount }} vendor reports for {{ missionLabel }}<span v-if="reportsLoading">, with {{ pendingCount }} still loading</span><span v-if="portfolioTotal > rows.length"> from the first {{ rows.length }} of {{ portfolioTotal }} indexed vendors</span>. Scores indicate assessed risk; evidence quality indicates how firmly that assessment can be defended.</p>
      </div>
      <div class="readout" aria-live="polite">
        <span>REPORT COVERAGE</span>
        <strong>{{ coverage }}%</strong>
         <small>{{ reportsLoading ? `${pendingCount} loading` : failedCount ? `${failedCount} unavailable` : 'all reports available' }}</small>
      </div>
    </header>

    <section class="primary-controls" aria-label="Portfolio triage controls">
      <v-text-field v-model="search" label="Vendor search" prepend-inner-icon="mdi-magnify" clearable hide-details density="compact" />
      <v-select v-model="tier" :items="tierOptions" label="Tier" clearable hide-details density="compact" />
      <v-select v-model="category" :items="categoryOptions" label="Risk category" clearable hide-details density="compact" />
      <v-select v-model="sort" :items="sortOptions" item-title="title" item-value="value" label="Rank by" hide-details density="compact" />
      <v-btn variant="outlined" class="advanced-toggle" prepend-icon="mdi-tune-variant" @click="advancedOpen = !advancedOpen">Advanced<span v-if="advancedCount"> · {{ advancedCount }}</span></v-btn>
    </section>
    <section v-if="advancedOpen" class="advanced-controls" aria-label="Advanced evidence filters">
      <v-select v-model="severity" :items="severityOptions" label="Severity / band" clearable hide-details density="compact" />
      <v-select v-model="simulation" :items="simulationOptions" item-title="title" item-value="value" label="Data status" hide-details density="compact" />
      <div class="range">
        <label>Confidence ≥ <b>{{ confidenceFloor }}%</b></label>
         <v-slider v-model="confidenceFloor" :min="0" :max="100" :step="5" :aria-label="`Minimum confidence ${confidenceFloor} percent`" hide-details density="compact" />
      </div>
      <div class="range">
        <label>Completeness ≥ <b>{{ completenessFloor }}%</b></label>
         <v-slider v-model="completenessFloor" :min="0" :max="100" :step="5" :aria-label="`Minimum completeness ${completenessFloor} percent`" hide-details density="compact" />
      </div>
      <v-select v-model="freshness" :items="freshnessOptions" item-title="title" item-value="value" label="Freshness" hide-details density="compact" />
    </section>
    <div v-if="activeConstraints.length" class="constraint-strip" aria-label="Active constraints">
      <span>ACTIVE</span>
      <button v-for="constraint in activeConstraints" :key="constraint.key" type="button" @click="constraint.clear">{{ constraint.label }} <b>×</b></button>
      <button type="button" class="clear-all" @click="resetFilters">Clear all</button>
    </div>

    <section v-if="loading" class="state-panel">
      <div class="state-kicker">ASSEMBLING BRIEF</div>
      <h2>Retrieving individual risk contracts</h2>
      <p>Vendor identities are available first. Risk ranking becomes available as report contracts resolve.</p>
      <v-progress-linear indeterminate color="secondary" class="mt-5" />
    </section>

    <section v-else-if="fatalError" class="state-panel failure">
      <div class="state-kicker">PORTFOLIO INDEX UNAVAILABLE</div>
      <h2>No vendor identities could be retrieved.</h2>
      <p>{{ fatalError }} No risk or evidence-quality comparison is available until the index responds.</p>
      <v-btn color="secondary" variant="flat" prepend-icon="mdi-refresh" @click="load">Retry retrieval</v-btn>
    </section>

    <template v-else>
      <aside v-if="failedCount || staleCount || portfolioTotal > rows.length" class="advisory">
        <v-icon icon="mdi-alert-outline" />
        <div><strong>{{ failedCount || portfolioTotal > rows.length ? 'Partial portfolio.' : 'Freshness warning.' }}</strong>
          {{ portfolioTotal > rows.length ? `The index contains ${portfolioTotal} vendors; this view shows the API maximum of ${rows.length}.` : '' }}
           {{ failedCount ? `${failedCount} report ${failedCount === 1 ? 'contract is' : 'contracts are'} unavailable; successful assessments are preserved.` : '' }}
           {{ staleCount ? `${staleCount} loaded ${staleCount === 1 ? 'report contains' : 'reports contain'} stale category evidence.` : '' }}
            <v-btn v-if="failedCount" size="x-small" variant="outlined" class="ml-2" :loading="retrying" @click="retryFailed">Retry unavailable</v-btn>
        </div>
      </aside>

      <div class="table-meta">
        <span><b>{{ filtered.length }}</b> shown / {{ rows.length }} vendors</span>
        <span>Risk drives the decision; evidence quality shows how defensible it is.</span>
      </div>

      <div v-if="!rows.length" class="state-panel">
        <div class="state-kicker">NO VENDORS IN SCOPE</div>
        <h2>The organization index returned no records.</h2>
        <p>There is no real portfolio data available to assess. Filters are not suppressing results.</p>
      </div>
      <div v-else-if="!filtered.length" class="state-panel">
        <div class="state-kicker">NO FILTER MATCH</div>
        <h2>No vendor meets this evidence threshold.</h2>
        <p>Broaden tier, category, severity, quality, freshness, or simulation constraints. The underlying {{ rows.length }} identities remain available.</p>
        <v-btn variant="outlined" color="secondary" @click="resetFilters">Clear constraints</v-btn>
      </div>

      <div v-else class="table-shell">
        <table>
          <thead><tr>
            <th>#</th><th>Vendor / availability</th><th>Tier</th><th>Risk decision</th><th>Key categories</th><th>Evidence quality</th><th>Next step</th>
          </tr></thead>
          <tbody>
            <tr v-for="(row, index) in filtered" :key="row.entity.id" :class="[profileClass(row), { unavailable: !row.contract && !row.pending }]">
              <td class="rank">{{ String(index + 1).padStart(2, '0') }}</td>
              <td class="vendor"><router-link :to="vendorDestination(row.entity.id)">{{ row.entity.name }}</router-link>
                <small class="identity">{{ identityLine(row.entity) }}</small>
                <div><span v-if="isAmbiguous(row.entity)" class="tag ambiguous">SAME-NAME — VERIFY IDENTITY</span><span v-if="row.entity.simulated" class="tag sim">SIMULATED</span><span v-if="row.pending" class="tag pending">ASSESSING</span><span v-else-if="!row.contract" class="tag missing">REPORT UNAVAILABLE</span><span v-else class="version">{{ row.contract.contract_version || 'unversioned contract' }}</span></div>
              </td>
              <td class="mono">{{ row.entity.tier ?? '—' }}</td>
              <td class="decision"><div class="score" :class="riskClass(row)">{{ number(row.contract?.score) }}</div><div><b>{{ row.contract?.band || 'Not assessed' }}</b><small>{{ row.contract?.disposition || 'No disposition available' }}</small></div></td>
              <td><div class="cats"><span v-for="cat in categoryNames(row).slice(0, 3)" :key="cat">{{ cat }}</span><small v-if="categoryNames(row).length > 3">+{{ categoryNames(row).length - 3 }}</small></div></td>
              <td><div class="evidence-summary"><span>Confidence <QualityBar :value="percent(row.contract?.confidence)" /></span><span>Complete <QualityBar :value="percent(row.contract?.completeness)" /></span><small><span :class="['fresh', freshnessClass(row)]">{{ freshnessLabel(row) }}</span> · {{ row.contract?.diligence_flags?.length ?? '—' }} diligence flags</small></div></td>
              <td><div class="row-next"><v-btn v-if="!row.contract && !row.pending" color="primary" size="small" :loading="row.retrying" @click="loadReport(row)">Retry assessment</v-btn><v-btn v-else color="primary" size="small" :to="vendorDestination(row.entity.id, 'risk')" :disabled="row.pending">Review vendor</v-btn><v-menu><template #activator="{ props: menuProps }"><v-btn v-bind="menuProps" icon="mdi-dots-vertical" size="small" variant="text" :aria-label="`More options for ${row.entity.name}`" /></template><v-list density="compact"><v-list-item :to="vendorDestination(row.entity.id, 'risk')" title="Risk report" prepend-icon="mdi-shield-search" /><v-list-item :to="vendorDestination(row.entity.id, 'artifacts')" title="Supporting evidence" prepend-icon="mdi-file-document-multiple" /><v-list-item :to="comparisonDestination(row.entity.id)" title="Compare vendor" prepend-icon="mdi-compare-horizontal" /></v-list></v-menu></div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, qs, type EntityListResponse, type EntityReportContract, type EntityRiskContract, type EntitySummary } from '../api/client'
import { compareTrustworthy } from '../lib/portfolioTriage'
import { identityLine } from '../lib/vendorIdentity'
import { missionRootFromQuery } from '../navigationState'
import { useGraph } from '../stores/graph'
import { ScopedRowRequests } from '../lib/latestRequest'

type Row = { entity: EntitySummary; contract: EntityRiskContract | null; pending?: boolean; retrying?: boolean; error?: string }
const REPORT_BATCH_SIZE = 8
const route = useRoute()
const graph = useGraph()
const rows = ref<Row[]>([]); const portfolioTotal = ref(0); const loading = ref(true); const reportsLoading = ref(false); const fatalError = ref('')
const advancedOpen = ref(false); const retrying = ref(false)
const portfolioRequests = new ScopedRowRequests<string>()
const search = ref(''); const tier = ref<string | number | null>(null); const category = ref<string | null>(null); const severity = ref<string | null>(null)
const simulation = ref(String(route.query.simulation || 'all')); const sort = ref(String(route.query.sort || 'risk')); const confidenceFloor = ref(Number(route.query.confidence || 0)); const completenessFloor = ref(Number(route.query.completeness || 0)); const freshness = ref(String(route.query.freshness || 'all'))
const simulationOptions = [{ title: 'All data', value: 'all' }, { title: 'Observed only', value: 'observed' }, { title: 'Simulated only', value: 'simulated' }]
const sortOptions = [{ title: 'Highest risk', value: 'risk' }, { title: 'Strongest evidence', value: 'trustworthy' }, { title: 'Lowest confidence', value: 'confidence' }, { title: 'Least complete', value: 'completeness' }, { title: 'Stalest evidence', value: 'freshness' }, { title: 'Vendor name', value: 'name' }]
const freshnessOptions = [{ title: 'Any freshness', value: 'all' }, { title: 'Current evidence', value: 'current' }, { title: 'Diligence required', value: 'diligence_required' }, { title: 'Contains stale evidence', value: 'stale' }, { title: 'Contains missing evidence', value: 'missing' }]
const severityOptions = [{ title: 'Critical', value: 'critical' }, { title: 'High', value: 'high' }, { title: 'Moderate', value: 'moderate' }, { title: 'Medium category', value: 'medium' }, { title: 'Low', value: 'low' }, { title: 'Clear category', value: 'clear' }, { title: 'Not assessed', value: 'not_assessed' }]
const loadedCount = computed(() => rows.value.filter(r => r.contract).length)
const pendingCount = computed(() => rows.value.filter(r => r.pending).length)
const failedCount = computed(() => rows.value.filter(r => !r.pending && !r.contract).length)
const coverage = computed(() => rows.value.length ? Math.round(loadedCount.value / rows.value.length * 100) : 0)
const tierOptions = computed(() => [...new Set(rows.value.map(r => r.entity.tier).filter(v => v != null))].sort())
const categoryOptions = computed(() => [...new Set(rows.value.flatMap(categoryNames))].sort())
const staleCount = computed(() => rows.value.filter(hasStaleEvidence).length)
const missionRoot = computed(() => missionRootFromQuery(route.query, graph.focusId))
const missionLabel = computed(() => !missionRoot.value
  ? 'the full workspace'
  : graph.focusId === missionRoot.value && graph.focusLabel
    ? graph.focusLabel
    : missionRoot.value)
const duplicateNames = computed(() => {
  const counts = new Map<string, number>()
  for (const row of rows.value) {
    const name = row.entity.name.toLocaleLowerCase()
    counts.set(name, (counts.get(name) || 0) + 1)
  }
  return counts
})
const advancedCount = computed(() => Number(Boolean(severity.value)) + Number(simulation.value !== 'all') + Number(freshness.value !== 'all') + Number(confidenceFloor.value > 0) + Number(completenessFloor.value > 0))
const activeConstraints = computed(() => [
  search.value && { key: 'search', label: `Search: ${search.value}`, clear: () => { search.value = '' } },
  tier.value != null && { key: 'tier', label: `Tier: ${tier.value}`, clear: () => { tier.value = null } },
  category.value && { key: 'category', label: `Category: ${category.value}`, clear: () => { category.value = null } },
  severity.value && { key: 'severity', label: `Severity: ${severity.value}`, clear: () => { severity.value = null } },
  simulation.value !== 'all' && { key: 'simulation', label: `Data: ${simulationOptions.find(x => x.value === simulation.value)?.title}`, clear: () => { simulation.value = 'all' } },
  freshness.value !== 'all' && { key: 'freshness', label: `Freshness: ${freshnessOptions.find(x => x.value === freshness.value)?.title}`, clear: () => { freshness.value = 'all' } },
  confidenceFloor.value > 0 && { key: 'confidence', label: `Confidence ≥ ${confidenceFloor.value}%`, clear: () => { confidenceFloor.value = 0 } },
  completenessFloor.value > 0 && { key: 'completeness', label: `Complete ≥ ${completenessFloor.value}%`, clear: () => { completenessFloor.value = 0 } },
].filter(Boolean) as Array<{ key: string; label: string; clear: () => void }>)
const QualityBar = defineComponent({ props: { value: Number }, setup: p => () => h('div', { class: 'quality' }, [h('span', { style: { width: `${p.value ?? 0}%` } }), h('b', p.value == null ? '—' : `${p.value}%`)]) })

function contractOf(report: EntityReportContract): EntityRiskContract | null {
  const raw = report.risk_contract || report.risk
  if (!raw || raw.contract_version !== 'uc11.vendor-risk.v1') return null
  return { contract_version: raw.contract_version || '', score: raw.score ?? null, band: raw.band ?? null, disposition: raw.disposition ?? null, confidence: raw.confidence ?? null, completeness: raw.completeness ?? null, freshness: raw.freshness ?? null, categories: raw.categories || [], diligence_flags: raw.diligence_flags || [] }
}
async function load() {
  const generation = portfolioRequests.beginScope()
  const rootId = missionRoot.value
  loading.value = true; reportsLoading.value = false; retrying.value = false; fatalError.value = ''; rows.value = []; portfolioTotal.value = 0
  try {
    const list = await api.get<EntityListResponse>(`/api/entities?${qs({ kind: 'organization', root_id: rootId, limit: 1000 })}`)
    if (portfolioRequests.currentScope() !== generation) return
    while (list.items.length < list.total) {
      const page = await api.get<EntityListResponse>(`/api/entities?${qs({ kind: 'organization', root_id: rootId, limit: 1000, offset: list.items.length })}`)
      if (portfolioRequests.currentScope() !== generation) return
      if (!page.items.length) throw new Error(`The organization index stopped after ${list.items.length} of ${list.total} vendors.`)
      list.items.push(...page.items)
    }
    if (portfolioRequests.currentScope() !== generation) return
    portfolioTotal.value = list.total
    rows.value = list.items.map(entity => ({ entity, contract: null, pending: true }))
    loading.value = false; reportsLoading.value = Boolean(rows.value.length)
    for (let offset = 0; offset < rows.value.length; offset += REPORT_BATCH_SIZE) {
      await Promise.all(rows.value.slice(offset, offset + REPORT_BATCH_SIZE).map(row => loadReport(row, generation, rootId)))
      if (portfolioRequests.currentScope() !== generation) return
    }
  } catch (e) {
    if (portfolioRequests.currentScope() === generation) fatalError.value = e instanceof Error ? e.message : 'Unknown retrieval failure.'
  } finally {
    if (portfolioRequests.currentScope() === generation) {
      loading.value = false; reportsLoading.value = false
    }
  }
}
async function loadReport(row: Row, generation = portfolioRequests.currentScope(), rootId = missionRoot.value) {
  const request = portfolioRequests.beginRow(row.entity.id, generation)
  row.pending = true; row.retrying = Boolean(row.error); row.error = undefined
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 15000)
  try {
    const contract = contractOf(await api.get<EntityReportContract>(`/api/entities/${encodeURIComponent(row.entity.id)}/report?${qs({ root_id: rootId })}`, { signal: controller.signal }))
    if (!portfolioRequests.isCurrent(row.entity.id, request)) return
    row.contract = contract
    if (!row.contract) row.error = 'The report did not include the supported uc11.vendor-risk.v1 contract.'
  } catch (e) {
    if (portfolioRequests.isCurrent(row.entity.id, request)) row.error = e instanceof DOMException && e.name === 'AbortError' ? 'The report timed out after 15 seconds.' : e instanceof Error ? e.message : 'Unknown report failure.'
  } finally {
    window.clearTimeout(timeout)
    if (portfolioRequests.isCurrent(row.entity.id, request)) {
      row.pending = false; row.retrying = false
    }
  }
}
async function retryFailed() {
  const generation = portfolioRequests.currentScope()
  const rootId = missionRoot.value
  retrying.value = true
  try {
    const failed = rows.value.filter(row => !row.contract && !row.pending)
    for (let offset = 0; offset < failed.length; offset += REPORT_BATCH_SIZE) {
      if (portfolioRequests.currentScope() !== generation) return
      await Promise.all(failed.slice(offset, offset + REPORT_BATCH_SIZE).map(row => loadReport(row, generation, rootId)))
    }
  } finally { if (portfolioRequests.currentScope() === generation) retrying.value = false }
}
function vendorDestination(id: string, tab?: 'risk' | 'artifacts') { return { path: `/entities/${id}`, query: { ...route.query, tab, root_id: missionRoot.value || undefined, vendor: id } } }
function comparisonDestination(id: string) { return { path: '/compare/vendors', query: { ...route.query, left: id, root_id: missionRoot.value || undefined, vendor: id } } }
function isAmbiguous(entity: EntitySummary) { return (duplicateNames.value.get(entity.name.toLocaleLowerCase()) || 0) > 1 }
function percent(v: number | null | undefined) { if (v == null) return null; return Math.round(v <= 1 ? v * 100 : v) }
function meetsFloor(v: number | null | undefined, floor: number) { const p = percent(v); return p == null ? floor === 0 : p >= floor }
function number(v: number | null | undefined) { return v == null ? '—' : Number(v).toFixed(Number(v) % 1 ? 1 : 0) }
function categoryNames(row: Row) { return (row.contract?.categories || []).map(c => typeof c === 'string' ? c : String(c.id || c.category || c.name || 'uncategorized')) }
function categorySeverity(row: Row) { return (row.contract?.categories || []).map(c => typeof c === 'object' ? String(c.severity || '').toLowerCase() : '') }
function selectedCategorySeverity(row: Row) {
  const selected = category.value
  if (!selected) return categorySeverity(row)
  return (row.contract?.categories || []).filter(c => typeof c === 'object' && String(c.id || c.category || c.name) === selected).map(c => String(typeof c === 'object' ? c.severity || '' : '').toLowerCase())
}
function riskClass(row: Row) { const b = (row.contract?.band || '').toLowerCase(); return b.includes('critical') || b.includes('high') ? 'hot' : b.includes('moderate') || b.includes('medium') ? 'warm' : 'cool' }
function categoryFreshness(row: Row) { return (row.contract?.categories || []).map(c => typeof c === 'object' ? String(c.freshness || '').toLowerCase() : '') }
function hasStaleEvidence(row: Row) { return categoryFreshness(row).includes('stale') }
function hasMissingEvidence(row: Row) { return categoryFreshness(row).includes('missing') }
function freshnessLabel(row: Row) { return String(row.contract?.freshness || 'unknown').replaceAll('_', ' ').toUpperCase() }
function freshnessClass(row: Row) { return hasStaleEvidence(row) ? 'stale' : row.contract?.freshness === 'current' ? 'current' : 'aging' }
function matchesFreshness(row: Row) {
  if (freshness.value === 'all') return true
  if (freshness.value === 'stale') return hasStaleEvidence(row)
  if (freshness.value === 'missing') return hasMissingEvidence(row)
  return row.contract?.freshness === freshness.value
}
function profileClass(row: Row) {
  if (row.pending) return 'profile-loading'
  if (!row.contract || hasMissingEvidence(row)) return 'profile-incomplete'
  if (hasStaleEvidence(row)) return 'profile-stale'
  if (['critical', 'high'].includes(String(row.contract.band))) return 'profile-risky'
  return 'profile-trustworthy'
}
const filtered = computed(() => rows.value.filter(r => {
  const band = (r.contract?.band || 'unknown').toLowerCase()
  return (!search.value || r.entity.name.toLowerCase().includes(search.value.toLowerCase())) && (tier.value == null || r.entity.tier === tier.value)
    && (!category.value || categoryNames(r).includes(category.value)) && (!severity.value || (!category.value && band.includes(severity.value)) || selectedCategorySeverity(r).includes(severity.value))
    && (simulation.value === 'all' || r.entity.simulated === (simulation.value === 'simulated'))
    && meetsFloor(r.contract?.confidence, confidenceFloor.value) && meetsFloor(r.contract?.completeness, completenessFloor.value)
    && matchesFreshness(r)
}).sort((a, b) => sort.value === 'name' ? a.entity.name.localeCompare(b.entity.name) : sort.value === 'trustworthy' ? compareTrustworthy(a.contract || {}, b.contract || {}) : sort.value === 'confidence' ? (percent(a.contract?.confidence) ?? -1) - (percent(b.contract?.confidence) ?? -1) : sort.value === 'completeness' ? (percent(a.contract?.completeness) ?? -1) - (percent(b.contract?.completeness) ?? -1) : sort.value === 'freshness' ? Number(hasStaleEvidence(b)) - Number(hasStaleEvidence(a)) || Number(hasMissingEvidence(b)) - Number(hasMissingEvidence(a)) : (b.contract?.score ?? -1) - (a.contract?.score ?? -1)))
function resetFilters() { search.value = ''; tier.value = null; category.value = null; severity.value = null; simulation.value = 'all'; confidenceFloor.value = 0; completenessFloor.value = 0; freshness.value = 'all' }
watch(missionRoot, load, { immediate: true })
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;600;700;800&display=swap');
.portfolio{--ink:#172724;--muted:#65756f;--paper:#f1f0e7;--line:#c8cec2;--teal:#075f58;--signal:#dd5a35;--control:#e7e9df;--advisory:#fae6d8;--panel:#f8f7ef;--header:#dfe4da;--header-ink:#45554f;--row-line:#d5d9cf;--hover:#e8eee6;--tag-sim:#f0d79c;--tag-missing:#efd3c7;--tag-pending:#dbe4e5;--category-line:#bac4b8;--quality:#dfe2d8;--quality-fill:#84aca1;--fresh:#d3e4db;--fresh-ink:#164e43;--aging:#eee0b7;--stale:#efd3c7;--stale-ink:#8e321f;--state:#e5e8df;min-height:100dvh;background:var(--paper);color:var(--ink);padding:28px 32px 56px;font-family:Manrope,sans-serif}.brief-head{display:grid;grid-template-columns:minmax(0,1fr) 180px;gap:32px;border-top:6px solid var(--teal);border-bottom:1px solid var(--ink);padding:22px 0 20px}.eyebrow,.state-kicker{font:500 10px 'DM Mono',monospace;letter-spacing:.13em;color:var(--teal)}h1{font-size:clamp(26px,3.2vw,47px);line-height:1.02;letter-spacing:-.045em;max-width:840px;margin:9px 0 12px}.brief-head p{font-size:13px;max-width:790px;color:var(--muted);margin:0}.readout{border-left:1px solid var(--line);padding-left:22px;display:flex;flex-direction:column}.readout span,.readout small{font:10px 'DM Mono',monospace}.readout strong{font:800 49px Manrope;letter-spacing:-.06em;color:var(--teal);line-height:1.1}.controls{display:grid;grid-template-columns:1.4fr repeat(4,minmax(115px,1fr));gap:8px;padding:14px 0 12px;border-bottom:1px solid var(--line)}.range{grid-column:span 2;border:1px solid var(--line);padding:6px 12px 0;background:var(--control)}.range label{font:10px 'DM Mono';letter-spacing:.03em}.advisory{display:flex;gap:10px;align-items:flex-start;background:var(--advisory);border-left:4px solid var(--signal);padding:10px 14px;font-size:12px;margin-top:12px}.table-meta{display:flex;justify-content:space-between;padding:13px 2px 8px;font:10px 'DM Mono';letter-spacing:.05em}.legend i{display:inline-block;width:7px;height:7px;margin:0 5px 0 15px}.risk-dot{background:var(--signal)}.evidence-dot{background:var(--teal)}.table-shell{overflow:auto;border-top:2px solid var(--ink);box-shadow:0 12px 30px rgba(33,52,46,.08)}table{border-collapse:collapse;width:100%;min-width:1280px;background:var(--panel);font-size:11px}th{text-align:left;background:var(--header);color:var(--header-ink);font:500 9px 'DM Mono';letter-spacing:.08em;text-transform:uppercase;padding:9px 8px;border-bottom:1px solid var(--ink);position:sticky;top:0;z-index:1}td{padding:8px;border-bottom:1px solid var(--row-line);vertical-align:middle}tbody tr{transition:transform .16s ease,background-color .16s ease}tbody tr:hover{background:var(--hover);transform:translateX(2px)}tbody tr td:first-child{box-shadow:inset 3px 0 transparent}.profile-trustworthy td:first-child{box-shadow:inset 3px 0 #2b7b66}.profile-risky td:first-child{box-shadow:inset 3px 0 var(--signal)}.profile-incomplete td:first-child{box-shadow:inset 3px 0 #c59529}.profile-stale td:first-child{box-shadow:inset 3px 0 #8d5c9c}.profile-loading td:first-child{box-shadow:inset 3px 0 #78909c}.unavailable{opacity:.7}.rank,.mono,.version{font-family:'DM Mono',monospace}.rank{color:var(--muted)}.vendor{min-width:190px}.vendor>a{font-weight:800;color:var(--ink);font-size:12px;text-decoration:none}.vendor>a:hover,.vendor>a:focus-visible{color:var(--teal);text-decoration:underline}.tag{font:500 8px 'DM Mono';padding:2px 4px;margin-right:4px}.sim{background:var(--tag-sim)}.missing{background:var(--tag-missing)}.pending{background:var(--tag-pending)}.version{font-size:8px;color:var(--muted)}.score{font:800 20px Manrope;border-left:4px solid var(--line);padding-left:7px}.score.hot{border-color:var(--signal)}.score.warm{border-color:#c59529}.score.cool{border-color:var(--teal)}td b{display:block;font-size:10px;text-transform:uppercase}td small{display:block;color:var(--muted);font-size:9px}.cats{display:flex;gap:3px;flex-wrap:wrap;max-width:230px}.cats span{border:1px solid var(--category-line);padding:2px 4px;font-size:9px}.quality{position:relative;width:82px;height:19px;background:var(--quality);overflow:hidden}.quality span{position:absolute;inset:0 auto 0 0;background:var(--quality-fill)}.quality b{position:relative;padding:3px 5px;font:500 9px 'DM Mono';color:var(--ink)}.fresh{font:500 9px 'DM Mono';padding:3px 5px}.current{background:var(--fresh);color:var(--fresh-ink)}.aging{background:var(--aging)}.stale{background:var(--stale);color:var(--stale-ink)}.actions{display:flex;gap:4px}.actions a{font:500 8px 'DM Mono';letter-spacing:.04em;color:var(--teal);border:1px solid var(--teal);padding:5px;text-decoration:none;transition:background .15s,color .15s}.actions a:hover,.actions a:focus-visible{background:var(--teal);color:var(--paper);outline:2px solid #d4a746;outline-offset:2px}.state-panel{max-width:760px;margin:60px auto;padding:32px;border-left:6px solid var(--teal);background:var(--state)}.state-panel h2{font-size:25px;margin:8px 0}.state-panel p{color:var(--muted);font-size:13px}.state-panel.failure{border-color:var(--signal)}
:global(.v-theme--dark .portfolio){--ink:#d9e6e1;--muted:#9eb2aa;--paper:#101715;--line:#394943;--teal:#66c6b7;--signal:#ff8a66;--control:#19221f;--advisory:#36241e;--panel:#141d1a;--header:#202c28;--header-ink:#b7cac2;--row-line:#2d3b36;--hover:#1d2b26;--tag-sim:#624d1d;--tag-missing:#532f27;--tag-pending:#26383a;--category-line:#496159;--quality:#2a3934;--quality-fill:#578f83;--fresh:#25483d;--fresh-ink:#b8f4df;--aging:#4d4222;--stale:#512d28;--stale-ink:#ffc4b8;--state:#182420}
table{min-width:1160px;font-size:12px}th{font-size:10px;letter-spacing:.06em;padding:10px 7px}td{padding:9px 7px}.eyebrow,.state-kicker,.readout span,.readout small,.range label,.table-meta{font-size:11px}.brief-head p{font-size:14px}.advisory{font-size:13px}.vendor{min-width:175px}.vendor>a{font-size:13px}.actions a{font-size:10px;padding:6px 5px}
.primary-controls{display:grid;grid-template-columns:1.5fr repeat(3,minmax(130px,1fr)) auto;gap:8px;padding:14px 0 12px}.advanced-controls{display:grid;grid-template-columns:repeat(3,minmax(130px,1fr)) 1.5fr 1.5fr;gap:8px;padding:12px;background:var(--control);border:1px solid var(--line)}.advanced-toggle{height:40px!important}.constraint-strip{display:flex;align-items:center;flex-wrap:wrap;gap:6px;padding:10px 0;border-bottom:1px solid var(--line);font:10px 'DM Mono'}.constraint-strip>span{color:var(--muted);letter-spacing:.08em}.constraint-strip button{border:1px solid var(--teal);color:var(--teal);padding:5px 7px;background:transparent;cursor:pointer}.constraint-strip .clear-all{border-color:transparent;text-decoration:underline}.advanced-controls .range{grid-column:auto;background:var(--panel)}.decision{display:flex;align-items:center;gap:9px;min-width:180px}.evidence-summary{display:grid;gap:4px;min-width:190px}.evidence-summary>span{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:9px}
.row-next{display:flex;align-items:center;white-space:nowrap}
.vendor .identity{font:9px 'DM Mono',monospace;color:var(--muted);margin:2px 0 4px;max-width:270px}.tag.ambiguous{background:var(--tag-missing);color:var(--stale-ink)}
@media(max-width:900px){.primary-controls,.advanced-controls{grid-template-columns:1fr 1fr}}@media(max-width:600px){.primary-controls,.advanced-controls{grid-template-columns:1fr}}
@media(max-width:900px){.portfolio{padding:18px 14px 40px}.brief-head{grid-template-columns:1fr}.readout{border-left:0;border-top:1px solid var(--line);padding:12px 0 0}.controls{grid-template-columns:1fr 1fr}.range{grid-column:span 1}.table-meta{gap:10px}.legend{display:none}}@media(max-width:600px){.portfolio{padding:12px 10px 32px}.controls{grid-template-columns:1fr}.range{grid-column:span 1}.brief-head{gap:18px}.table-meta{align-items:flex-start;flex-direction:column}.state-panel{margin:28px auto;padding:22px 18px}.advisory{overflow-wrap:anywhere}}
</style>