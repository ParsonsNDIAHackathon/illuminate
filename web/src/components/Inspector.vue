<template>
  <div class="inspector" v-if="node">
    <div class="d-flex align-center ga-2 flex-wrap mb-1">
      <v-chip size="x-small" variant="tonal">{{ node.label }}<span v-if="p.kind"> · {{ p.kind }}</span></v-chip>
      <v-chip v-if="p.flagged" size="x-small" color="error" variant="tonal" :title="p.flag_reason">flagged</v-chip>
      <v-chip v-if="scorable" size="x-small" variant="tonal" :color="bandChip(rs.band)"
              :title="rs.note || 'Not scored yet'">{{ scoreLabel(rs.score, rs.band) }}</v-chip>
    </div>
    <div class="ids text-caption">
      <span v-if="p.uei">UEI {{ p.uei }}</span><span v-if="p.cage"> · CAGE {{ p.cage }}</span><span v-if="p.lei"> · LEI {{ p.lei }}</span><span v-if="p.ticker"> · {{ p.ticker }}</span>
    </div>
    <div class="d-flex flex-wrap ga-1 my-2" v-if="node.label === 'Entity'">
      <v-chip v-if="detail?.parent_seat && !String(detail.parent_seat.code).startsWith('US')" size="x-small" color="error" variant="tonal">Foreign ultimate parent</v-chip>
      <v-chip v-if="supplies.some((s:any) => s.sole_source)" size="x-small" color="warning" variant="tonal">Sole source</v-chip>
      <v-chip v-if="detail?.tier" size="x-small" variant="tonal">Tier {{ detail.tier }}</v-chip>
    </div>
    <template v-if="node.label === 'Entity' && detail">
      <section v-if="hasSupply">
        <h4>Supply</h4>
        <dl>
          <template v-if="detail.categories?.length"><dt>Category</dt><dd>{{ detail.categories.map((c:any) => c.name).join(' › ') }}</dd></template>
          <template v-if="supplies.length"><dt>Supplies</dt><dd>{{ supplies.map((s:any) => `${s.name} (T${s.tier ?? '?'}${s.sole_source ? ', sole' : ''})`).join('; ') }}</dd></template>
          <template v-if="supplies[0]?.psc"><dt>PSC</dt><dd>{{ supplies[0].psc }}<span v-if="supplies[0].naics"> · NAICS {{ supplies[0].naics }}</span></dd></template>
          <template v-if="detail.suppliers_count"><dt>Suppliers</dt><dd>{{ detail.suppliers_count }}</dd></template>
        </dl>
      </section>
      <section>
        <h4>Geography</h4>
        <dl>
          <dt>Incorporated</dt><dd>{{ detail.incorporated?.code || '—' }}</dd>
          <dt>Operates</dt><dd>{{ detail.operates?.map((x:any) => x.code).join(', ') || '—' }}</dd>
          <dt>Manufactures</dt><dd>{{ detail.manufactures?.map((x:any) => x.code).join(', ') || '—' }}</dd>
          <dt>Parent seat</dt><dd>{{ detail.parent_seat?.code || '—' }}</dd>
        </dl>
      </section>
      <section v-if="detail.ultimate_parents?.length || detail.direct_parents?.length">
        <h4>Control</h4>
        <dl>
          <template v-if="detail.direct_parents?.length"><dt>Owner</dt><dd>{{ detail.direct_parents.map((x:any) => x.name + (x.pct ? ` ${x.pct}%` : '')).join(', ') }}</dd></template>
          <template v-if="detail.ultimate_parents?.length"><dt>Ultimate</dt><dd>{{ detail.ultimate_parents.map((x:any) => x.name).join(', ') }}</dd></template>
        </dl>
      </section>
    </template>
    <section v-if="node.label === 'Person'">
      <h4>Roles</h4>
      <div v-for="r in personRoles" :key="r.edge_id" class="text-body-2">{{ r.title }} · {{ r.entity }} <span class="text-caption">{{ r.from || '?' }} – {{ r.current ? 'now' : (r.to || '?') }}</span></div>
    </section>
    <section v-if="scorable">
      <div class="d-flex align-center ga-1">
        <h4 class="flex-grow-1">Risk</h4>
        <v-btn v-if="graph.highlightIds.length" size="x-small" variant="text" density="compact"
               @click="graph.trace(null)">clear trace</v-btn>
      </div>
      <p v-if="rs.score == null" class="text-caption" style="opacity:.7">
        Nothing to grade yet — no dimension returned data. Enrich this node to give the scorer something to read.
      </p>
      <template v-else>
        <!-- Coverage before breakdown: the number is only readable once you know how much
             of the model stood behind it. -->
        <p class="text-caption mb-1" :class="{ 'text-warning': isThin(rs.confidence) }">
          {{ confidenceNote(rs.confidence, rs.dimensions_scored, rs.dimensions_requested) }}
        </p>
        <div v-for="c in riskComponents" :key="c.dimension" class="risk-row"
             :class="{ clickable: c.element_ids?.length }" :title="c.detail || c.label"
             @click="trace(c)">
          <v-icon size="14" :icon="sevIcon(c.severity)" :color="sevColor(c.severity)" />
          <span class="risk-label">{{ c.label }}</span>
          <span class="risk-sev">{{ c.severity || 'no data' }}</span>
        </div>
      </template>
    </section>
    <section>
      <h4>Provenance</h4>
      <dl>
        <dt>Source</dt><dd>{{ p.source || '—' }} <a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener">↗</a></dd>
        <dt>Retrieved</dt><dd>{{ (p.retrieved_at || '').slice(0, 10) || '—' }}</dd>
        <dt>Method</dt><dd>{{ p.method || '—' }}<span v-if="p.confidence != null"> · confidence {{ p.confidence }}</span></dd>
      </dl>
    </section>
    <section v-if="node.label === 'Artifact'">
      <h4>Artifact</h4>
      <dl>
        <!-- An award URL can run to 200 characters; the row shows what identifies the page and
             keeps the whole of it on hover and in the link itself. -->
        <template v-if="p.url"><dt>Page</dt><dd class="url" :title="p.url"><SourceLink :href="p.url" :artifact-id="node.id">{{ p.url }}</SourceLink></dd></template>
        <template v-if="p.published_at"><dt>Published</dt><dd>{{ p.published_at }}</dd></template>
        <template v-if="p.amount"><dt>Amount</dt><dd>${{ Number(p.amount).toLocaleString() }}</dd></template>
        <template v-if="p.award_id"><dt>Award</dt><dd>{{ p.award_id }}</dd></template>
        <template v-if="p.form"><dt>Form</dt><dd>{{ p.form }}</dd></template>
      </dl>
    </section>
    <!-- A generated document, kept in the graph beside what it is about. The two things that
         belong on a stored report are when it was written and a way to write it again, because
         a report about a graph that keeps changing is only as good as its timestamp. -->
    <section v-if="node.label === 'Report'">
      <h4>Report</h4>
      <dl>
        <dt>Kind</dt><dd>{{ kindLabel(p.kind) }}</dd>
        <dt>Subject</dt><dd><a href="#" @click.prevent="showSubject">{{ p.subject_name || p.subject_id }}</a></dd>
        <dt>Generated</dt><dd>{{ generatedAt }}</dd>
        <dt>Written by</dt><dd>{{ p.generated_by && p.generated_by !== 'derived' ? p.generated_by : 'computed from the graph' }}</dd>
        <template v-if="p.finding_count != null"><dt>Findings</dt><dd>{{ p.finding_count }}<span v-if="p.top_band"> · worst {{ p.top_band }}</span></dd></template>
        <template v-if="p.cited_count"><dt>Cites</dt><dd>{{ p.cited_count }} nodes</dd></template>
      </dl>
      <p v-if="p.summary" class="text-body-2 mt-2" style="opacity:.85">{{ p.summary }}</p>
    </section>
    <div class="d-flex flex-wrap ga-1 mt-2">
      <v-btn v-if="node.label === 'Artifact'" prepend-icon="mdi-text-box-search-outline" @click="rawId = node.id">Contents</v-btn>
      <v-btn v-if="node.label === 'Artifact'" prepend-icon="mdi-eye-outline" @click="viewId = node.id">View</v-btn>
      <template v-if="node.label === 'Report'">
        <v-btn prepend-icon="mdi-book-open-variant" :to="`/reports/${node.id}`">Read</v-btn>
        <v-btn prepend-icon="mdi-refresh" :loading="reports.busy === node.id" @click="regenerate"
               title="Rebuild this report from current graph data — same report, new timestamp">Regenerate</v-btn>
        <v-btn v-if="citations.length" prepend-icon="mdi-map-marker-path" variant="text" @click="traceCitations"
               title="Light up everything this report names">Trace</v-btn>
      </template>
      <!-- Generating is the one action that makes something new, so it is a menu rather than a
           button: which kind of document is a decision, not a default. -->
      <v-menu v-if="node.label === 'Entity'" location="bottom start">
        <template #activator="{ props: act }">
          <v-btn v-bind="act" prepend-icon="mdi-file-document-outline" append-icon="mdi-menu-down"
                 :loading="!!reports.busy">Report</v-btn>
        </template>
        <v-list density="compact" style="min-width:280px">
          <v-list-subheader>Generate</v-list-subheader>
          <v-list-item v-for="k in reports.kinds" :key="k.kind" :title="k.label" :subtitle="k.description"
                       @click="makeReport(k.kind)" />
          <template v-if="existingReports.length">
            <v-divider />
            <v-list-subheader>Already written</v-list-subheader>
            <v-list-item v-for="r in existingReports" :key="r.id" :title="kindLabel(r.kind)"
                         :subtitle="`generated ${new Date(r.generated_at).toLocaleString()}`"
                         :to="`/reports/${r.id}`" prepend-icon="mdi-book-open-variant" />
          </template>
        </v-list>
      </v-menu>
      <v-btn v-if="node.label !== 'Report'" prepend-icon="mdi-arrow-expand-all" @click="$emit('expand', node.id)">Expand</v-btn>
      <v-btn v-if="isProgram" prepend-icon="mdi-sitemap-outline" @click="openDiscover" :loading="discovering">Find suppliers</v-btn>
      <v-btn v-if="node.label === 'Entity'" prepend-icon="mdi-auto-fix" @click="enrich" :loading="enriching">Enrich</v-btn>
      <v-btn v-if="isProgram && node.id !== graph.focusId" prepend-icon="mdi-target" variant="text" @click="focusHere" :loading="focusing" title="Show only this program and its supply chain">Focus</v-btn>
    </div>
    <v-dialog v-model="discoverDlg" max-width="520">
      <v-card>
        <v-card-title class="text-subtitle-1">Find suppliers of {{ node.name }}</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-3" style="opacity:.75">
            Federal award records are searched for these words. Prime recipients become tier-1 suppliers and their
            reported sub-awardees tier-2. Use the designation the contracts carry — “E-2D”, not the full programme
            title — since a broad word pulls in unrelated companies that happen to share it.
          </p>
          <v-combobox v-model="kw" label="Award keywords" multiple chips closable-chips clearable
                      hint="Press enter after each" persistent-hint density="comfortable" />
          <div class="d-flex ga-3 mt-3">
            <v-text-field v-model="agency" label="Awarding agency" density="comfortable" hide-details
                          placeholder="Department of Defense" />
            <v-text-field v-model.number="maxSubs" label="Max sub-awardees" type="number" density="comfortable" hide-details style="max-width:150px" />
          </div>
          <p v-if="discoverError" class="text-body-2 mt-3 text-error">{{ discoverError }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="discoverDlg = false">Cancel</v-btn>
          <v-btn color="primary" :disabled="!kw.length" :loading="discovering" @click="runDiscover">Search awards</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <ArtifactViewer :artifact-id="rawId" @close="rawId = null" />
    <SourceFrame v-if="viewId" :artifact-id="viewId" @close="viewId = null" />
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, qs } from '../api/client'
import { useRouter } from 'vue-router'
import { useGraph } from '../stores/graph'
import { useJobs } from '../stores/jobs'
import { useReports } from '../stores/reports'
import { useWorkspace } from '../stores/workspace'
import ArtifactViewer from './ArtifactViewer.vue'
import SourceFrame from './SourceFrame.vue'
import SourceLink from './SourceLink.vue'
import { bandChip, confidenceNote, isThin, scoreLabel, sevColor, sevIcon } from '../styles/risk'
const graph = useGraph(); const jobs = useJobs(); const ws = useWorkspace(); const reports = useReports()
const router = useRouter()
const rawId = ref<string | null>(null); const viewId = ref<string | null>(null)
defineEmits<{ (e: 'expand', id: string): void }>()
const node = computed(() => graph.selected)
const p = computed(() => node.value?.props || {})
const detail = ref<any>(null); const supplies = ref<any[]>([]); const personRoles = ref<any[]>([]); const enriching = ref(false); const focusing = ref(false)
const isProgram = computed(() => node.value?.label === 'Entity' && p.value.kind === 'program')
// A heading over an empty list reads as missing data; an agency simply has no supply to show.
const hasSupply = computed(() => !!(detail.value?.categories?.length || supplies.value.length || detail.value?.suppliers_count))
// Only organisations, programs and people are scored; locations, artifacts and claims are
// evidence about parties, not parties to be graded.
const scorable = computed(() => node.value?.label === 'Entity' || node.value?.label === 'Person')
// The breakdown is ~2 KB per node, so it is stripped from the canvas payload
// (graphio.HEAVY_PROPS) and fetched for the one node that is actually open.
const risk = ref<any>(null)
const riskComponents = computed<any[]>(() => risk.value?.components || [])
// The canvas payload carries the score, band and confidence; the fetch supersedes them
// once it lands, and covers a node that has never been through a pass (explain() recomputes).
const rs = computed(() => risk.value ?? {
  score: p.value.risk_score, band: p.value.risk_band, confidence: p.value.risk_confidence,
  note: p.value.risk_note, dimensions_scored: p.value.risk_dimensions_scored,
  dimensions_requested: p.value.risk_dimensions_requested,
})
/** Light up the nodes and edges a dimension was computed from: a score the user cannot walk
 *  back to its evidence is only an assertion. */
function trace(c: any) { if (c.element_ids?.length) graph.trace(c.element_ids) }

// --- reports -------------------------------------------------------------------------
// The canvas payload carries a report's metadata but never its html or its citation list
// (graphio.HEAVY_PROPS), so the open node fetches what it needs to show and to trace.
const reportDetail = ref<any>(null)
const citations = computed<string[]>(() => reportDetail.value?.element_ids || [])
const existingReports = computed(() => (node.value ? reports.forSubject(node.value.id) : []))
const generatedAt = computed(() => (p.value.generated_at ? new Date(p.value.generated_at).toLocaleString() : '—'))
function kindLabel(k: string) { return reports.kinds.find(x => x.kind === k)?.label || k }
async function showSubject() {
  const id = p.value.subject_id
  if (!id) return
  if (!graph.nodes.has(id)) await graph.loadNeighbourhood(id, 1, ws.ws.layers)
  graph.select(id)
}
/** Everything the document names, lit up on the canvas: the report and the graph should
 *  never be able to disagree about what a finding was made of. */
function traceCitations() { if (citations.value.length) graph.trace(citations.value) }
async function regenerate() {
  const id = node.value!.id
  await reports.regenerate(id)
  reportDetail.value = await reports.fetch(id, false)
}
async function makeReport(kind: string) {
  const row = await reports.generate(kind, node.value!.id)
  router.push(`/reports/${row.id}`)
}
const discoverDlg = ref(false); const discovering = ref(false); const discoverError = ref('')
const kw = ref<string[]>([]); const agency = ref(''); const maxSubs = ref<number | null>(null)
watch(node, async (n) => {
  detail.value = null; supplies.value = []; personRoles.value = []; risk.value = null; reportDetail.value = null
  if (!n) return
  // The kinds and the reports already written are what the Report menu is built from, and
  // the list is a dozen rows at most; load it once, the first time a node is opened.
  if (!reports.kinds.length) reports.load()
  // Both labels are scored, so this is fetched before the label-specific work below.
  if (scorable.value) {
    try { risk.value = await api.get(`/api/risk/${n.id}`) } catch {}
  }
  if (n.label === 'Report') {
    try { reportDetail.value = await reports.fetch(n.id, false) } catch {}
  }
  if (n.label === 'Entity') {
    try {
      // tier is counted towards the focused program; with nothing focused there is no tier
      const rep = await api.get(`/api/entities/${n.id}/report?${qs({ root_id: graph.focusId })}`)
      detail.value = { ...rep.geography, ...rep.control, categories: rep.categories, tier: rep.supply.tier_from_root, suppliers_count: rep.supply.suppliers_count }
      supplies.value = rep.supply.supplies
    } catch {}
  } else if (n.label === 'Person') {
    personRoles.value = graph.edgeList.filter(e => e.type === 'HELD_ROLE' && e.source === n.id).map(e => ({ edge_id: e.id, entity: graph.nodes.get(e.target)?.name, ...e.props }))
  }
}, { immediate: true })
async function enrich() { enriching.value = true; try { await jobs.enqueue(node.value!.id) } finally { enriching.value = false } }
function openDiscover() {
  // the keywords a previous search used, never a guess from the name: guessing is how
  // "Hawkeye" pulls in a satellite company that has nothing to do with the aircraft
  kw.value = [...(p.value.keywords || [])]
  agency.value = p.value.award_agency ?? ''
  maxSubs.value = p.value.max_subs ?? null
  discoverError.value = ''
  discoverDlg.value = true
}
async function runDiscover() {
  discovering.value = true; discoverError.value = ''
  try {
    // the write is held at the permission gate, so this resolves when the user decides
    await api.post(`/api/programs/${node.value!.id}/suppliers`, {
      keywords: kw.value, agency: agency.value || null, max_subs: maxSubs.value ?? null,
    })
    discoverDlg.value = false
  } catch (e: any) {
    discoverError.value = e?.message || 'the award search was refused'
  } finally { discovering.value = false }
}
async function focusHere() {
  focusing.value = true
  const id = node.value!.id
  try { await graph.focus(id, node.value!.name, ws.depth, ws.ws.layers); graph.select(id) } finally { focusing.value = false }
}
</script>
<style scoped>
.inspector { padding: 10px 12px 12px; font-size: 13px; }
.ids { opacity: .7; }
section { margin-top: 10px; }
h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .6; margin-bottom: 4px; }
dl { display: grid; grid-template-columns: 90px 1fr; gap: 2px 8px; margin: 0; }
dt { opacity: .6; } dd { margin: 0; }
.url { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.url a { display: block; overflow: hidden; text-overflow: ellipsis; }
.risk-row { display: grid; grid-template-columns: 18px 1fr auto; align-items: center; gap: 4px; padding: 1px 0; }
.risk-row.clickable { cursor: pointer; }
.risk-row.clickable:hover .risk-label { text-decoration: underline; }
.risk-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.risk-sev { font-size: 11px; opacity: .6; }
</style>
