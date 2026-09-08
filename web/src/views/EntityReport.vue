<template>
  <v-container fluid v-if="rep" class="report">
    <div class="d-flex align-center ga-2 mb-1">
      <v-btn icon="mdi-arrow-left" variant="text" @click="router.back()" />
      <h2 class="text-h6">{{ rep.identity.name }}</h2>
      <v-chip v-if="rep.entity.flagged" size="x-small" color="error" variant="tonal">flagged</v-chip>
      <v-spacer />
      <v-btn prepend-icon="mdi-compare-horizontal" :to="`/compare/vendors?left=${encodeURIComponent(props.id)}`">Compare</v-btn>
      <v-btn prepend-icon="mdi-graph" @click="openInGraph">Open in graph</v-btn>
      <v-btn prepend-icon="mdi-auto-fix" @click="enrich" :loading="enriching">Enrich</v-btn>
    </div>
    <div class="text-caption mb-3" style="opacity:.75">
      <span v-if="rep.identity.uei">UEI {{ rep.identity.uei }}</span><span v-if="rep.identity.cage"> · CAGE {{ rep.identity.cage }}</span><span v-if="rep.identity.lei"> · LEI {{ rep.identity.lei }}</span>
      · {{ rep.identity.public ? `public${rep.identity.ticker ? ' (' + rep.identity.ticker + ')' : ''}` : 'private' }}<span v-if="rep.control.ultimate_parents?.length">, subsidiary of {{ rep.control.ultimate_parents[0].name }}</span>
      <span v-if="rep.identity.registration_status"> · {{ rep.identity.registration_status }}</span>
    </div>
    <v-tabs v-model="tab" density="compact"><v-tab value="overview">Overview</v-tab><v-tab value="people">People</v-tab><v-tab value="affiliations">Affiliations<v-badge v-if="rep.affiliations?.count" :content="rep.affiliations.count" inline /></v-tab><v-tab value="risk">Risk</v-tab><v-tab value="artifacts">Artifacts</v-tab><v-tab value="graph">Graph</v-tab></v-tabs>
    <v-window v-model="tab" class="mt-3">
      <v-window-item value="overview">
        <v-row>
          <v-col cols="12" md="8">
            <v-card variant="outlined" class="mb-3"><v-card-text>
              <div class="d-flex align-center ga-2 mb-1"><span class="section">Summary</span><v-chip size="x-small" variant="tonal">{{ `${rep.summary.generated_by} · ${rep.summary.source_count} sources` }}</v-chip><v-spacer /><v-btn size="x-small" variant="text" @click="regen" :loading="regen_busy">Regenerate</v-btn></div>
              <p class="text-body-2" v-if="rep.summary.text">{{ rep.summary.text }}</p>
              <p class="text-caption mt-1" v-if="rep.summary.citations?.length">Evidence: {{ rep.summary.citations.join(', ') }}</p>
            </v-card-text></v-card>
            <v-card variant="outlined" class="mb-3" v-if="rep.entity.ticker || rep.entity.last_price"><v-card-text>
              <span class="section">Market — {{ rep.entity.ticker }}</span>
              <p class="text-body-2">{{ rep.entity.last_price ? `Last ${rep.entity.last_price}` : 'Listed; quote requires a market-data key' }}<span v-if="rep.entity.market_cap"> · market cap {{ rep.entity.market_cap }}</span></p>
            </v-card-text></v-card>
            <v-card variant="outlined" class="mb-3"><v-card-text>
              <span class="section">Recent news</span>
              <div v-if="!rep.news.length" class="text-body-2" style="opacity:.6">No news artifacts. Run enrichment with GDELT to fetch recent coverage.</div>
              <div v-for="n in rep.news" :key="n.id" class="text-body-2 my-1"><a :href="n.url" target="_blank" rel="noopener">{{ n.title }}</a> <span class="text-caption" style="opacity:.7">{{ n.domain }} · {{ n.published_at }}<span v-if="n.sentiment"> · sentiment {{ n.sentiment }}</span></span></div>
            </v-card-text></v-card>
            <v-card variant="outlined"><v-card-text>
              <span class="section">Supply relationships</span>
              <v-table density="compact"><thead><tr><th>Supplies</th><th>Tier</th><th>PSC</th><th>Sole source</th><th>Amount</th><th>Contract</th><th>Source</th></tr></thead>
                <tbody><template v-for="s in rep.supply.supplies" :key="s.edge_id || s.id + s.contract_ref"><tr><td><router-link :to="`/entities/${s.id}`">{{ s.name }}</router-link></td><td>{{ s.tier }}</td><td>{{ s.psc }}</td><td>{{ formatSoleSource(s.sole_source) }}</td><td>{{ s.amount ? '$' + Number(s.amount).toLocaleString() : '—' }}</td><td>{{ s.contract_ref || '—' }}</td><td><a v-if="s.source_url" :href="s.source_url" target="_blank" rel="noopener">{{ s.source }}</a><span v-else>{{ s.source || 'Unavailable' }}</span></td></tr>
                  <tr class="lineage-row"><td colspan="7"><div class="lineage"><TruthBadge :value="supplyTruthStatus(s)" /><span>Retrieved {{ formatDate(supplyEvidence(s)?.retrieved_at) }}</span><span>Method {{ supplyEvidence(s)?.method || 'Unavailable' }}</span><span>Rule <span class="mono">{{ supplyFactor(s)?.rule_id || 'Unavailable' }}</span></span><span>Confidence {{ formatConfidence(supplyEvidence(s)?.confidence) }}</span><span>Freshness <TruthBadge :value="supplyFactor(s)?.freshness || 'unavailable'" /></span><router-link v-if="supplyEvidence(s)?.claim_id" :to="{ path: '/claims', query: { entity_id: props.id, status: supplyEvidence(s)?.claim_status || 'committed' } }">Review claim</router-link><span v-else>No backing claim available</span></div></td></tr>
                </template></tbody></v-table>
            </v-card-text></v-card>
          </v-col>
          <v-col cols="12" md="4">
            <v-card variant="outlined" class="mb-3"><v-card-text>
              <span class="section">At a glance</span>
              <dl>
                <dt>Status</dt><dd>{{ rep.identity.public ? 'Public' : 'Private' }}{{ rep.control.ultimate_parents?.length ? ' sub' : '' }}</dd>
                <dt>Parent</dt><dd>{{ rep.control.ultimate_parents?.[0]?.name || rep.control.direct_parents?.[0]?.name || '—' }}</dd>
                <dt>Seat</dt><dd>{{ rep.geography.parent_seat?.code || '—' }}</dd>
                <dt>Incorporated</dt><dd>{{ rep.geography.incorporated?.code || '—' }}</dd>
                <dt>Manufactures</dt><dd>{{ rep.geography.manufactures?.map((m:any) => m.code).join(', ') || '—' }}</dd>
                <dt>Employees</dt><dd>{{ rep.entity.employees || '—' }}</dd>
                <dt>Revenue</dt><dd>{{ rep.identity.revenue ? '$' + Number(rep.identity.revenue).toLocaleString() : '—' }}</dd>
                <dt>Awards</dt><dd>{{ rep.supply.awards.count }} on record</dd>
                <dt>Tier</dt><dd>{{ rep.supply.tier_from_root != null ? `${rep.supply.tier_from_root} from ${graph.focusLabel || 'the focused program'}` : '—' }}</dd>
              </dl>
            </v-card-text></v-card>
            <v-card variant="outlined" class="mb-3"><v-card-text>
              <span class="section">Screens</span>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip v-for="s in rep.screens" :key="s.predicate" size="small" variant="tonal" :color="s.result === 'hit' ? 'error' : s.result === 'clear' ? 'success' : undefined" :title="s.detail">{{ s.source }} {{ s.result }}</v-chip>
                <v-chip v-if="rep.geography.parent_seat && !rep.geography.parent_seat.code.startsWith('US')" size="small" variant="tonal" color="warning">Foreign seat</v-chip>
                <span v-if="!rep.screens.length" class="text-body-2" style="opacity:.6">Not yet screened — run enrichment.</span>
              </div>
            </v-card-text></v-card>
            <v-card variant="outlined"><v-card-text><span class="section">Sources</span><p class="text-body-2">{{ rep.sources.join(' · ') || '—' }}</p></v-card-text></v-card>
          </v-col>
        </v-row>
      </v-window-item>
      <v-window-item value="people">
        <p class="text-caption mb-2" style="opacity:.7">Current — {{ rep.people.resolved_current_count }} resolved<span v-if="rep.people.board_size"> of {{ rep.people.board_size }} seats</span>. Two tenures are two edges, not one record overwritten.</p>
        <v-list density="compact" lines="two">
          <v-list-subheader>Current</v-list-subheader>
          <v-list-item v-for="p in rep.people.current" :key="p.edge_id" :title="`${p.name} — ${p.title || ''}`" :subtitle="`${p.role_type || ''} · since ${p.from || '?'}${p.elsewhere.length ? ' · also: ' + p.elsewhere.map((x:any) => x.entity + (x.current ? '' : ' (former)')).join(', ') : ''}`">
            <template #append><v-chip v-if="p.interlock" size="x-small" color="secondary" variant="tonal">Interlock</v-chip><v-chip v-if="p.concurrent_government" size="x-small" color="warning" variant="tonal" class="ml-1">Government post</v-chip><v-chip v-else-if="p.former_government" size="x-small" color="secondary" variant="tonal" class="ml-1">Ex-government</v-chip><v-chip v-if="p.public_official" size="x-small" color="secondary" variant="tonal" class="ml-1">Public official</v-chip><v-chip v-if="p.elsewhere.some((x:any) => x.flagged)" size="x-small" color="error" variant="tonal" class="ml-1">Linked to flagged</v-chip><a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ p.source }}</a></template>
          </v-list-item>
          <v-list-subheader>Former</v-list-subheader>
          <v-list-item v-for="p in rep.people.former" :key="p.edge_id" :title="`${p.name} — ${p.title || ''}`" :subtitle="`${p.role_type || ''} · ${p.from || '?'} – ${p.to || '?'}${p.elsewhere.length ? ' · now: ' + p.elsewhere.filter((x:any) => x.current).map((x:any) => x.entity).join(', ') : ''}`">
            <template #append><v-chip v-if="p.moved_to_flagged" size="x-small" color="error" variant="tonal">Moved to flagged</v-chip><a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ p.source }}</a></template>
          </v-list-item>
          <v-list-item v-if="!rep.people.current.length && !rep.people.former.length" subtitle="No officers or directors resolved. LittleSis and EDGAR coverage is strongest for large listed firms." />
        </v-list>
      </v-window-item>
      <v-window-item value="affiliations">
        <p class="text-caption mb-2" style="opacity:.7">Ties recorded beyond supply and ownership: memberships, business relationships, lobbying and giving. Counterparties need not be suppliers. A foreign flag comes from a resolved jurisdiction; a name hint is unverified.</p>
        <template v-for="sec in [['Subsidiaries', 'subsidiaries'], ['Memberships', 'memberships'], ['Business relationships', 'transactions'], ['Lobbying', 'lobbying'], ['Donations', 'donations']]" :key="sec[1]">
          <v-list-subheader>{{ sec[0] }} ({{ rep.affiliations[sec[1]].length }})</v-list-subheader>
          <v-list density="compact" lines="two">
            <v-list-item v-for="t in rep.affiliations[sec[1]]" :key="t.edge_id" :subtitle="`${t.kind === 'agency' ? (t.federal ? 'federal body' : 'government body') : (t.org_types || []).filter((x:string) => x !== 'Organization').join(', ') || 'organization'}${t.from || t.to ? ' · ' + (t.from || '?') + ' – ' + (t.current ? 'present' : t.to || '?') : ''}${t.amount ? ' · $' + Number(t.amount).toLocaleString() : ''}`">
              <template #title><router-link :to="`/entities/${t.entity_id}`">{{ t.entity }}</router-link><span v-if="!t.outbound" class="text-caption ml-1" style="opacity:.7">(inbound)</span></template>
              <template #append><v-chip v-if="t.flagged" size="x-small" color="error" variant="tonal">Flagged</v-chip><v-chip v-else-if="t.foreign" size="x-small" color="warning" variant="tonal">Foreign · {{ t.incorporated || t.parent_seat }}</v-chip><v-chip v-else-if="t.foreign_hint" size="x-small" color="secondary" variant="tonal">Foreign? (name)</v-chip><a v-if="t.source_url" :href="t.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ t.source }}</a></template>
            </v-list-item>
            <v-list-item v-if="!rep.affiliations[sec[1]].length" subtitle="None on record." />
          </v-list>
        </template>
      </v-window-item>
      <v-window-item value="risk">
        <v-card variant="outlined" class="mb-3 recommendation-card">
          <v-card-text>
            <div class="d-flex align-center flex-wrap ga-2"><span class="section">Recommendation basis</span><TruthBadge :value="riskProfile?.freshness || 'unavailable'" /><strong>{{ recommendationLabel }}</strong><v-spacer /><span class="text-caption">{{ coveredCategories }}/{{ riskProfile?.categories.length || 0 }} risk categories covered · {{ formatPercent(riskProfile?.completeness) }} completeness</span></div>
            <div v-if="riskProfile?.diligence_flags.length" class="mt-2">
              <div v-for="flag in riskProfile.diligence_flags" :key="`${flag.category}:${flag.code}`" class="gap-row">
                <TruthBadge :value="flag.code.startsWith('stale') ? 'stale' : flag.code.startsWith('unknown') ? 'unavailable' : 'missing'" />
                <span><b>{{ labelize(flag.category || 'Evidence') }}:</b> {{ flag.message }}</span>
                <span v-if="flag.excluded_truth_statuses?.length" class="text-caption">Excluded: <TruthBadge v-for="state in flag.excluded_truth_statuses" :key="state" :value="state" /></span>
              </div>
            </div>
            <div class="deep-links mt-2"><v-btn size="small" variant="text" prepend-icon="mdi-check-decagram" :to="{ path: '/claims', query: { entity_id: props.id, status: 'committed' } }">Review claims</v-btn><v-btn size="small" variant="text" prepend-icon="mdi-file-document-multiple" :to="{ path: '/artifacts', query: { entity_id: props.id } }">Inspect artifacts</v-btn></div>
          </v-card-text>
        </v-card>
        <div class="factor-grid mb-3">
          <v-card v-for="category in riskProfile?.categories || []" :key="category.id" variant="outlined" class="factor-card">
            <v-card-text>
              <div class="d-flex align-center ga-2"><strong>{{ labelize(category.label || category.id) }}</strong><v-spacer /><TruthBadge :value="category.freshness" /><v-chip size="x-small" variant="tonal" :color="sevColor(category.severity)">{{ category.severity || 'No data' }}</v-chip></div>
              <div v-if="!category.factors.length" class="missing-copy">No approved evidence. This gap is not treated as a clear result.</div>
              <div v-for="factor in category.factors" :key="factor.rule_id" class="factor">
                <div class="d-flex align-center flex-wrap ga-1"><TruthBadge :value="factor.truth_status || 'derived'" /><b>{{ factor.explanation || labelize(factor.rule_id) }}</b></div>
                <dl class="provenance-list"><dt>Claim</dt><dd><TruthBadge :value="factor.claim_status || 'unavailable'" /></dd><dt>Source</dt><dd>{{ factor.provenance?.source || factor.evidence?.[0]?.source || 'Unavailable' }}</dd><dt>Retrieved</dt><dd>{{ formatDate(factor.provenance?.retrieved_at || factor.evidence?.[0]?.retrieved_at) }}</dd><dt>Method</dt><dd>{{ factor.provenance?.method || factor.evidence?.[0]?.method || 'Unavailable' }}</dd><dt>Rule</dt><dd class="mono">{{ factor.rule_id }}</dd><dt>Confidence</dt><dd>{{ formatConfidence(factor.confidence) }}</dd><dt>Freshness</dt><dd><TruthBadge :value="factor.freshness || category.freshness" /></dd></dl>
              </div>
            </v-card-text>
          </v-card>
        </div>
        <v-list density="compact" lines="two">
          <v-list-item v-for="i in rep.risk.indicators" :key="i.family" :title="i.label" :subtitle="i.detail || ''" :class="{ 'finding-selected': selectedFinding === i.family }" @click="selectedFinding = i.family">
            <template #prepend><v-icon :icon="sevIcon(i.severity)" :color="sevColor(i.severity)" /></template>
            <template #append><v-chip size="x-small" variant="tonal" :color="sevColor(i.severity)">{{ i.severity ? i.severity : 'No data' }}</v-chip><span class="ml-2 text-caption" style="opacity:.7">{{ i.source || '—' }}</span></template>
          </v-list-item>
        </v-list>
        <div v-if="activeFinding" class="finding-actions">
          <div><span class="section">Selected report indicator</span><strong>{{ activeFinding.label }}</strong><small>{{ activeFinding.element_ids?.length ? `${activeFinding.element_ids.length} matching graph element${activeFinding.element_ids.length === 1 ? '' : 's'}` : 'No matching graph elements supplied by this report' }}</small></div>
          <v-btn color="primary" prepend-icon="mdi-vector-polyline" :disabled="!activeFinding.element_ids?.length" @click="traceFinding(activeFinding)">Focus mission path</v-btn>
          <v-btn v-if="activeFinding.source_url" variant="outlined" prepend-icon="mdi-source-branch" :href="activeFinding.source_url" target="_blank" rel="noopener">Matching evidence</v-btn>
          <span v-else class="evidence-unavailable">No matching evidence destination supplied</span>
        </div>
        <v-alert variant="tonal" density="compact" class="mt-2" type="info">
          <b v-if="rep.risk.score != null">Risk score {{ rep.risk.score }}/100 · {{ String(rep.risk.band || '').replaceAll('_', ' ') }}.</b>
          <b v-else>Risk score not assessed.</b>
          {{ rep.risk.note }}
        </v-alert>
        <p class="text-caption mt-2" style="opacity:.7">{{ rep.risk.disclaimer }}</p>
      </v-window-item>
      <v-window-item value="artifacts">
        <v-table density="compact"><thead><tr><th>Kind</th><th>Title</th><th>Source</th><th>Date</th><th>View</th></tr></thead>
          <tbody><tr v-for="a in rep.artifacts" :key="a.id"><td>{{ a.kind }}</td><td><SourceLink :href="a.url" :artifact-id="a.id">{{ a.title }}</SourceLink></td><td>{{ a.source }}</td><td>{{ a.published_at || (a.retrieved_at || '').slice(0, 10) }}</td><td><v-btn icon="mdi-text-box-search-outline" size="x-small" variant="text" title="View contents" @click="rawId = a.id" /></td></tr></tbody></v-table>
        <ArtifactViewer :artifact-id="rawId" @close="rawId = null" />
        <p v-if="!rep.artifacts.length" class="text-body-2 mt-2" style="opacity:.6">No artifacts attached yet.</p>
      </v-window-item>
      <v-window-item value="graph">
        <div style="height: 60vh; position: relative"><GraphCanvas /></div>
      </v-window-item>
    </v-window>
  </v-container>
  <v-container v-else><v-progress-linear indeterminate /></v-container>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, getVendorRiskProfile, qs, type VendorRiskProfile } from '../api/client'
import GraphCanvas from '../components/GraphCanvas.vue'
import ArtifactViewer from '../components/ArtifactViewer.vue'
import SourceLink from '../components/SourceLink.vue'
import TruthBadge from '../components/TruthBadge.vue'
import { useGraph } from '../stores/graph'
const rawId = ref<string | null>(null)
import { useJobs } from '../stores/jobs'
import { useWorkspace } from '../stores/workspace'
const props = defineProps<{ id: string }>()
const router = useRouter(); const route = useRoute(); const graph = useGraph(); const jobs = useJobs(); const ws = useWorkspace()
const requestedTab = String(route.query.tab || '')
const tab = ref(requestedTab === 'evidence' ? 'artifacts' : requestedTab || 'overview')
const rep = ref<any>(null); const enriching = ref(false); const regen_busy = ref(false)
const riskProfile = ref<VendorRiskProfile | null>(null)
const selectedFinding = ref<string | null>(null)
const activeFinding = computed(() => rep.value?.risk?.indicators?.find((i: any) => i.family === selectedFinding.value) || null)
async function load() {
  const report = await api.get(`/api/entities/${props.id}/report?${qs({ root_id: graph.focusId })}`)
  rep.value = report
  riskProfile.value = await getVendorRiskProfile(props.id, report)
}
const coveredCategories = computed(() => riskProfile.value?.categories.filter(category => category.factors.length > 0).length || 0)
const recommendationLabel = computed(() => labelize(riskProfile.value?.disposition || 'Complete diligence'))
function labelize(value: string) { return value.replaceAll('_', ' ').replaceAll('.', ' ') }
function formatDate(value?: string) { return value ? new Date(value).toLocaleString() : 'Unavailable' }
function formatConfidence(value?: number | null) { return value == null ? 'Unavailable' : `${Math.round(value * 100)}%` }
function formatPercent(value?: number | null) { return value == null ? 'Unavailable' : `${Math.round(value * 100)}%` }
function formatSoleSource(value: unknown) { return value === true ? 'yes' : value === false ? 'no' : 'Unavailable' }
function supplyEvidence(s: any) {
  if (!s.edge_id) return undefined
  return rep.value?.supply?.risk_evidence?.find((e: any) => e.evidence_id === s.edge_id)
}
function supplyFactor(s: any) {
  const evidence = supplyEvidence(s)
  return riskProfile.value?.categories.find(category => category.id === 'supply_criticality')?.factors.find(factor =>
    factor.evidence_refs.includes(evidence?.claim_id) || factor.evidence_refs.includes(evidence?.evidence_id),
  )
}
function supplyTruthStatus(s: any) {
  const evidence = supplyEvidence(s)
  return evidence?.claim_status || evidence?.status || 'unavailable'
}
function sevIcon(s: string | null) { return s === 'high' ? 'mdi-alert-octagon' : s === 'medium' ? 'mdi-alert' : s === 'low' ? 'mdi-information-outline' : s === 'clear' ? 'mdi-check-circle-outline' : 'mdi-help-circle-outline' }
function sevColor(s: string | null) { return s === 'high' ? 'error' : s === 'medium' ? 'warning' : s === 'low' ? 'secondary' : s === 'clear' ? 'success' : undefined }
async function enrich() { enriching.value = true; try { await jobs.enqueue(props.id) } finally { enriching.value = false } }
async function regen() { regen_busy.value = true; try { await api.post(`/api/entities/${props.id}/summary`); await load() } catch (e: any) { alert(e.message) } finally { regen_busy.value = false } }
async function openInGraph() { await graph.loadNeighbourhood(props.id, 2, ws.ws.layers); graph.select(props.id); router.push({ name: 'graph' }) }
function traceFinding(i: any) {
  const ids = [...new Set((i.element_ids || []).filter(Boolean))].sort()
  router.push({ name: 'graph', query: { vendor: props.id, focus: ids.join(','), finding: i.label, family: i.family, evidence: i.source_url || undefined } })
}
watch(tab, async (t) => { if (t === 'graph') { await graph.loadNeighbourhood(props.id, 2, { ...ws.ws.layers, people: true, countries: true }, true); graph.select(props.id) } })
watch(() => jobs.jobs.filter(j => j.entity_id === props.id && ['succeeded', 'empty', 'partial', 'failed', 'timed_out'].includes(j.status)).length, load)
onMounted(load); watch(() => props.id, load)
</script>
<style scoped>
.section { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .6; }
dl { display: grid; grid-template-columns: 110px 1fr; gap: 3px 8px; margin: 6px 0 0; font-size: 13px; }
dt { opacity: .6; } dd { margin: 0; }
.finding-selected { background: rgba(0,107,98,.08); border-left: 3px solid #006b62; }
.finding-actions { margin-top: 12px; padding: 12px; display: flex; align-items: center; gap: 8px; border: 1px solid rgba(0,107,98,.3); border-radius: 5px; background: rgba(0,107,98,.045); }
.finding-actions > div { display: grid; margin-right: auto; }
.finding-actions strong { font-size: 13px; }
.finding-actions small { opacity: .65; font-size: 11px; }
.evidence-unavailable { max-width: 150px; color: rgba(70,65,55,.72); font-size: 11px; line-height: 1.25; }
.lineage-row td { padding-top: 0 !important; border-bottom: thin solid rgba(0,0,0,.12) !important; }
.lineage { display: flex; align-items: center; flex-wrap: wrap; gap: 5px 12px; padding: 3px 0 8px; font-size: 11px; opacity: .82; }
.factor-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
.factor-card { min-width: 0; }
.factor { margin-top: 10px; padding-top: 10px; border-top: thin solid rgba(0,0,0,.12); }
.provenance-list { grid-template-columns: 76px 1fr; }
.missing-copy { margin-top: 8px; padding: 8px; color: #8a5213; background: rgba(183,121,0,.08); font-size: 12px; }
.gap-row { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin-top: 6px; font-size: 12px; }
.gap-row .v-chip { margin-left: 3px; }
.deep-links { display: flex; flex-wrap: wrap; }
.mono { font-family: ui-monospace, monospace; }
@media (max-width: 767px) {
  .report > .d-flex:first-child { flex-wrap: wrap; }
  .report > .d-flex:first-child h2 { flex: 1 1 calc(100% - 60px); overflow-wrap: anywhere; }
  .report > .d-flex:first-child .v-spacer { display: none; }
  .factor-grid { grid-template-columns: 1fr; }
  .finding-actions { align-items: stretch; flex-direction: column; }
  .finding-actions > div { margin-right: 0; }
  .evidence-unavailable { max-width: none; }
  dl { grid-template-columns: 94px minmax(0,1fr); }
  :deep(.v-list-item__append) { flex-wrap: wrap; justify-content: flex-end; max-width: 46%; }
  :deep(.v-list-item-title), :deep(.v-list-item-subtitle) {
    display: block;
    overflow: visible;
    white-space: normal;
    -webkit-line-clamp: unset;
  }
}
</style>
