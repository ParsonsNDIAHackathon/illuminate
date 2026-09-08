<template>
  <main class="portfolio">
    <header class="brief-head">
      <div>
        <div class="eyebrow">ACQUISITION INTELLIGENCE / PORTFOLIO TRIAGE</div>
        <h1>Vendor risk, separated from evidence quality.</h1>
         <p>Ranked operational view of {{ loadedCount }} vendor reports<span v-if="reportsLoading">, with {{ pendingCount }} still loading</span><span v-if="portfolioTotal > rows.length"> from the first {{ rows.length }} of {{ portfolioTotal }} indexed vendors</span>. Scores indicate assessed risk; confidence, completeness, and freshness indicate how firmly that assessment can be defended.</p>
      </div>
      <div class="readout" aria-live="polite">
        <span>REPORT COVERAGE</span>
        <strong>{{ coverage }}%</strong>
         <small>{{ reportsLoading ? `${pendingCount} loading` : failedCount ? `${failedCount} unavailable` : 'all reports available' }}</small>
      </div>
    </header>

    <section class="controls" aria-label="Portfolio filters">
      <v-text-field v-model="search" label="Vendor search" prepend-inner-icon="mdi-magnify" clearable hide-details density="compact" />
      <v-select v-model="tier" :items="tierOptions" label="Tier" clearable hide-details density="compact" />
      <v-select v-model="category" :items="categoryOptions" label="Risk category" clearable hide-details density="compact" />
      <v-select v-model="severity" :items="severityOptions" label="Severity / band" clearable hide-details density="compact" />
      <v-select v-model="simulation" :items="simulationOptions" item-title="title" item-value="value" label="Data status" hide-details density="compact" />
      <v-select v-model="sort" :items="sortOptions" item-title="title" item-value="value" label="Rank by" hide-details density="compact" />
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
          {{ failedCount ? `${failedCount} report ${failedCount === 1 ? 'contract is' : 'contracts are'} unavailable; identity rows remain visible but cannot be ranked by risk.` : '' }}
           {{ staleCount ? `${staleCount} loaded ${staleCount === 1 ? 'report contains' : 'reports contain'} stale category evidence.` : '' }}
        </div>
      </aside>

      <div class="table-meta">
        <span><b>{{ filtered.length }}</b> shown / {{ rows.length }} vendors</span>
        <span class="legend"><i class="risk-dot"></i> RISK CONTRACT <i class="evidence-dot"></i> EVIDENCE QUALITY</span>
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
            <th>#</th><th>Vendor / status</th><th>Tier</th><th>Risk score</th><th>Band / disposition</th><th>Categories</th>
            <th>Confidence</th><th>Complete</th><th>Freshness</th><th>Diligence</th><th>Open</th>
          </tr></thead>
          <tbody>
            <tr v-for="(row, index) in filtered" :key="row.entity.id" :class="[profileClass(row), { unavailable: !row.contract && !row.pending }]">
              <td class="rank">{{ String(index + 1).padStart(2, '0') }}</td>
              <td class="vendor"><router-link :to="`/entities/${row.entity.id}`">{{ row.entity.name }}</router-link>
                <div><span v-if="row.entity.simulated" class="tag sim">SIMULATED</span><span v-if="row.pending" class="tag pending">ASSESSING</span><span v-else-if="!row.contract" class="tag missing">REPORT UNAVAILABLE</span><span v-else class="version">{{ row.contract.contract_version || 'unversioned contract' }}</span></div>
              </td>
              <td class="mono">{{ row.entity.tier ?? '—' }}</td>
              <td><div class="score" :class="riskClass(row)">{{ number(row.contract?.score) }}</div></td>
              <td><b>{{ row.contract?.band || 'Not assessed' }}</b><small>{{ row.contract?.disposition || 'No disposition available' }}</small></td>
              <td><div class="cats"><span v-for="cat in categoryNames(row).slice(0, 3)" :key="cat">{{ cat }}</span><small v-if="categoryNames(row).length > 3">+{{ categoryNames(row).length - 3 }}</small></div></td>
              <td><QualityBar :value="percent(row.contract?.confidence)" /></td>
              <td><QualityBar :value="percent(row.contract?.completeness)" /></td>
              <td><span :class="['fresh', freshnessClass(row)]">{{ freshnessLabel(row) }}</span></td>
              <td class="mono">{{ row.contract?.diligence_flags?.length ?? '—' }}</td>
               <td><div class="actions"><router-link :to="`/entities/${row.entity.id}?tab=risk`" title="Open vendor risk report">REPORT</router-link><router-link :to="`/entities/${row.entity.id}?tab=artifacts`" title="Open supporting evidence">EVIDENCE</router-link></div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { api, type EntityListResponse, type EntityReportContract, type EntityRiskContract, type EntitySummary } from '../api/client'

type Row = { entity: EntitySummary; contract: EntityRiskContract | null; pending?: boolean; error?: string }
const rows = ref<Row[]>([]); const portfolioTotal = ref(0); const loading = ref(true); const reportsLoading = ref(false); const fatalError = ref('')
const search = ref(''); const tier = ref<string | number | null>(null); const category = ref<string | null>(null); const severity = ref<string | null>(null)
const simulation = ref('all'); const sort = ref('risk'); const confidenceFloor = ref(0); const completenessFloor = ref(0); const freshness = ref('all')
const simulationOptions = [{ title: 'All data', value: 'all' }, { title: 'Observed only', value: 'observed' }, { title: 'Simulated only', value: 'simulated' }]
const sortOptions = [{ title: 'Highest risk', value: 'risk' }, { title: 'Lowest confidence', value: 'confidence' }, { title: 'Least complete', value: 'completeness' }, { title: 'Stalest evidence', value: 'freshness' }, { title: 'Vendor name', value: 'name' }]
const freshnessOptions = [{ title: 'Any freshness', value: 'all' }, { title: 'Current evidence', value: 'current' }, { title: 'Diligence required', value: 'diligence_required' }, { title: 'Contains stale evidence', value: 'stale' }, { title: 'Contains missing evidence', value: 'missing' }]
const severityOptions = [{ title: 'Critical', value: 'critical' }, { title: 'High', value: 'high' }, { title: 'Moderate', value: 'moderate' }, { title: 'Medium category', value: 'medium' }, { title: 'Low', value: 'low' }, { title: 'Clear category', value: 'clear' }, { title: 'Not assessed', value: 'not_assessed' }]
const loadedCount = computed(() => rows.value.filter(r => r.contract).length)
const pendingCount = computed(() => rows.value.filter(r => r.pending).length)
const failedCount = computed(() => rows.value.filter(r => !r.pending && !r.contract).length)
const coverage = computed(() => rows.value.length ? Math.round(loadedCount.value / rows.value.length * 100) : 0)
const tierOptions = computed(() => [...new Set(rows.value.map(r => r.entity.tier).filter(v => v != null))].sort())
const categoryOptions = computed(() => [...new Set(rows.value.flatMap(categoryNames))].sort())
const staleCount = computed(() => rows.value.filter(hasStaleEvidence).length)
const QualityBar = defineComponent({ props: { value: Number }, setup: p => () => h('div', { class: 'quality' }, [h('span', { style: { width: `${p.value ?? 0}%` } }), h('b', p.value == null ? '—' : `${p.value}%`)]) })

function contractOf(report: EntityReportContract): EntityRiskContract | null {
  const raw = report.risk_contract || report.risk
  if (!raw || raw.contract_version !== 'uc11.vendor-risk.v1') return null
  return { contract_version: raw.contract_version || '', score: raw.score ?? null, band: raw.band ?? null, disposition: raw.disposition ?? null, confidence: raw.confidence ?? null, completeness: raw.completeness ?? null, freshness: raw.freshness ?? null, categories: raw.categories || [], diligence_flags: raw.diligence_flags || [] }
}
async function load() {
  loading.value = true; reportsLoading.value = false; fatalError.value = ''; rows.value = []; portfolioTotal.value = 0
  try {
    const list = await api.get<EntityListResponse>('/api/entities?kind=organization&limit=1000')
    portfolioTotal.value = list.total
    rows.value = list.items.map(entity => ({ entity, contract: null, pending: true }))
    loading.value = false; reportsLoading.value = Boolean(rows.value.length)
    await Promise.all(rows.value.map(async (row) => {
      try {
        row.contract = contractOf(await api.get<EntityReportContract>(`/api/entities/${row.entity.id}/report`))
        if (!row.contract) row.error = 'The report did not include the supported uc11.vendor-risk.v1 contract.'
      } catch (e) {
        row.error = e instanceof Error ? e.message : 'Unknown report failure.'
      } finally {
        row.pending = false
      }
    }))
  } catch (e) {
    fatalError.value = e instanceof Error ? e.message : 'Unknown retrieval failure.'
  } finally {
    loading.value = false; reportsLoading.value = false
  }
}
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
}).sort((a, b) => sort.value === 'name' ? a.entity.name.localeCompare(b.entity.name) : sort.value === 'confidence' ? (percent(a.contract?.confidence) ?? -1) - (percent(b.contract?.confidence) ?? -1) : sort.value === 'completeness' ? (percent(a.contract?.completeness) ?? -1) - (percent(b.contract?.completeness) ?? -1) : sort.value === 'freshness' ? Number(hasStaleEvidence(b)) - Number(hasStaleEvidence(a)) || Number(hasMissingEvidence(b)) - Number(hasMissingEvidence(a)) : (b.contract?.score ?? -1) - (a.contract?.score ?? -1)))
function resetFilters() { search.value = ''; tier.value = null; category.value = null; severity.value = null; simulation.value = 'all'; confidenceFloor.value = 0; completenessFloor.value = 0; freshness.value = 'all' }
onMounted(load)
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;600;700;800&display=swap');
.portfolio{--ink:#172724;--muted:#65756f;--paper:#f1f0e7;--line:#c8cec2;--teal:#075f58;--signal:#dd5a35;min-height:100dvh;background:var(--paper);color:var(--ink);padding:28px 32px 56px;font-family:Manrope,sans-serif}.brief-head{display:grid;grid-template-columns:minmax(0,1fr) 180px;gap:32px;border-top:6px solid var(--teal);border-bottom:1px solid var(--ink);padding:22px 0 20px}.eyebrow,.state-kicker{font:500 10px 'DM Mono',monospace;letter-spacing:.13em;color:var(--teal)}h1{font-size:clamp(26px,3.2vw,47px);line-height:1.02;letter-spacing:-.045em;max-width:840px;margin:9px 0 12px}.brief-head p{font-size:13px;max-width:790px;color:var(--muted);margin:0}.readout{border-left:1px solid var(--line);padding-left:22px;display:flex;flex-direction:column}.readout span,.readout small{font:10px 'DM Mono',monospace}.readout strong{font:800 49px Manrope;letter-spacing:-.06em;color:var(--teal);line-height:1.1}.controls{display:grid;grid-template-columns:1.4fr repeat(4,minmax(115px,1fr));gap:8px;padding:14px 0 12px;border-bottom:1px solid var(--line)}.range{grid-column:span 2;border:1px solid var(--line);padding:6px 12px 0;background:#e7e9df}.range label{font:10px 'DM Mono';letter-spacing:.03em}.advisory{display:flex;gap:10px;align-items:flex-start;background:#fae6d8;border-left:4px solid var(--signal);padding:10px 14px;font-size:12px;margin-top:12px}.table-meta{display:flex;justify-content:space-between;padding:13px 2px 8px;font:10px 'DM Mono';letter-spacing:.05em}.legend i{display:inline-block;width:7px;height:7px;margin:0 5px 0 15px}.risk-dot{background:var(--signal)}.evidence-dot{background:var(--teal)}.table-shell{overflow:auto;border-top:2px solid var(--ink);box-shadow:0 12px 30px rgba(33,52,46,.08)}table{border-collapse:collapse;width:100%;min-width:1280px;background:#f8f7ef;font-size:11px}th{text-align:left;background:#dfe4da;color:#45554f;font:500 9px 'DM Mono';letter-spacing:.08em;text-transform:uppercase;padding:9px 8px;border-bottom:1px solid var(--ink);position:sticky;top:0;z-index:1}td{padding:8px;border-bottom:1px solid #d5d9cf;vertical-align:middle}tbody tr{transition:transform .16s ease,background-color .16s ease}tbody tr:hover{background:#e8eee6;transform:translateX(2px)}tbody tr td:first-child{box-shadow:inset 3px 0 transparent}.profile-trustworthy td:first-child{box-shadow:inset 3px 0 #2b7b66}.profile-risky td:first-child{box-shadow:inset 3px 0 var(--signal)}.profile-incomplete td:first-child{box-shadow:inset 3px 0 #c59529}.profile-stale td:first-child{box-shadow:inset 3px 0 #8d5c9c}.profile-loading td:first-child{box-shadow:inset 3px 0 #78909c}.unavailable{opacity:.7}.rank,.mono,.version{font-family:'DM Mono',monospace}.rank{color:var(--muted)}.vendor{min-width:190px}.vendor>a{font-weight:800;color:var(--ink);font-size:12px;text-decoration:none}.vendor>a:hover,.vendor>a:focus-visible{color:var(--teal);text-decoration:underline}.tag{font:500 8px 'DM Mono';padding:2px 4px;margin-right:4px}.sim{background:#f0d79c}.missing{background:#efd3c7}.pending{background:#dbe4e5}.version{font-size:8px;color:var(--muted)}.score{font:800 20px Manrope;border-left:4px solid var(--line);padding-left:7px}.score.hot{border-color:var(--signal)}.score.warm{border-color:#c59529}.score.cool{border-color:var(--teal)}td b{display:block;font-size:10px;text-transform:uppercase}td small{display:block;color:var(--muted);font-size:9px}.cats{display:flex;gap:3px;flex-wrap:wrap;max-width:230px}.cats span{border:1px solid #bac4b8;padding:2px 4px;font-size:9px}.quality{position:relative;width:82px;height:19px;background:#dfe2d8;overflow:hidden}.quality span{position:absolute;inset:0 auto 0 0;background:#84aca1}.quality b{position:relative;padding:3px 5px;font:500 9px 'DM Mono';color:var(--ink)}.fresh{font:500 9px 'DM Mono';padding:3px 5px}.current{background:#d3e4db;color:#164e43}.aging{background:#eee0b7}.stale{background:#efd3c7;color:#8e321f}.actions{display:flex;gap:4px}.actions a{font:500 8px 'DM Mono';letter-spacing:.04em;color:var(--teal);border:1px solid var(--teal);padding:5px;text-decoration:none;transition:background .15s,color .15s}.actions a:hover,.actions a:focus-visible{background:var(--teal);color:#f3f0e6;outline:2px solid #d4a746;outline-offset:2px}.state-panel{max-width:760px;margin:60px auto;padding:32px;border-left:6px solid var(--teal);background:#e5e8df}.state-panel h2{font-size:25px;margin:8px 0}.state-panel p{color:var(--muted);font-size:13px}.state-panel.failure{border-color:var(--signal)}
table{min-width:1160px;font-size:12px}th{font-size:10px;letter-spacing:.06em;padding:10px 7px}td{padding:9px 7px}.eyebrow,.state-kicker,.readout span,.readout small,.range label,.table-meta{font-size:11px}.brief-head p{font-size:14px}.advisory{font-size:13px}.vendor{min-width:175px}.vendor>a{font-size:13px}.actions a{font-size:10px;padding:6px 5px}
@media(max-width:900px){.portfolio{padding:18px 14px 40px}.brief-head{grid-template-columns:1fr}.readout{border-left:0;border-top:1px solid var(--line);padding:12px 0 0}.controls{grid-template-columns:1fr 1fr}.range{grid-column:span 1}.table-meta{gap:10px}.legend{display:none}}@media(max-width:600px){.controls{grid-template-columns:1fr}.range{grid-column:span 1}.brief-head{gap:18px}}
</style>