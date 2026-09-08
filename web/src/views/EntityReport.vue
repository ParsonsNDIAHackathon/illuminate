<template>
  <v-container fluid v-if="rep" class="report">
    <div class="d-flex align-center ga-2 mb-1">
      <v-btn icon="mdi-arrow-left" variant="text" @click="router.back()" />
      <h2 class="text-h6">{{ rep.identity.name }}</h2>
      <v-chip v-if="rep.identity.simulated" size="x-small" color="warning" variant="tonal">SIMULATED</v-chip>
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
    <v-tabs v-model="tab" density="compact"><v-tab value="overview">Overview</v-tab><v-tab value="people">People</v-tab><v-tab value="risk">Risk</v-tab><v-tab value="artifacts">Artifacts</v-tab><v-tab value="graph">Graph</v-tab></v-tabs>
    <v-window v-model="tab" class="mt-3">
      <v-window-item value="overview">
        <v-row>
          <v-col cols="12" md="8">
            <v-card variant="outlined" class="mb-3"><v-card-text>
              <div class="d-flex align-center ga-2 mb-1"><span class="section">Summary</span><v-chip size="x-small" variant="tonal">{{ rep.summary.text ? `generated · ${rep.summary.model || 'model'} · ${rep.summary.source_count} sources` : 'not generated' }}</v-chip><v-spacer /><v-btn size="x-small" variant="text" @click="regen" :loading="regen_busy">Regenerate</v-btn></div>
              <p class="text-body-2" v-if="rep.summary.text">{{ rep.summary.text }}</p>
              <p class="text-body-2" v-else style="opacity:.6">No model-written summary yet. Requires an OpenAI key; the report below stands on its own.</p>
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
                <tbody><tr v-for="s in rep.supply.supplies" :key="s.id + s.contract_ref"><td><router-link :to="`/entities/${s.id}`">{{ s.name }}</router-link></td><td>{{ s.tier }}</td><td>{{ s.psc }}</td><td>{{ s.sole_source ? 'yes' : '' }}</td><td>{{ s.amount ? '$' + Number(s.amount).toLocaleString() : '' }}</td><td>{{ s.contract_ref }}</td><td><a v-if="s.source_url" :href="s.source_url" target="_blank" rel="noopener">{{ s.source }}</a></td></tr></tbody></v-table>
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
                <dt>Awards</dt><dd>{{ rep.supply.awards.count }} on record</dd>
                <dt>Tier</dt><dd>{{ rep.supply.tier_from_root != null ? `${rep.supply.tier_from_root} from root` : '—' }}</dd>
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
            <template #append><v-chip v-if="p.interlock" size="x-small" color="secondary" variant="tonal">Interlock</v-chip><v-chip v-if="p.elsewhere.some((x:any) => x.flagged)" size="x-small" color="error" variant="tonal" class="ml-1">Linked to flagged</v-chip><a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ p.source }}</a></template>
          </v-list-item>
          <v-list-subheader>Former</v-list-subheader>
          <v-list-item v-for="p in rep.people.former" :key="p.edge_id" :title="`${p.name} — ${p.title || ''}`" :subtitle="`${p.role_type || ''} · ${p.from || '?'} – ${p.to || '?'}${p.elsewhere.length ? ' · now: ' + p.elsewhere.filter((x:any) => x.current).map((x:any) => x.entity).join(', ') : ''}`">
            <template #append><v-chip v-if="p.moved_to_flagged" size="x-small" color="error" variant="tonal">Moved to flagged</v-chip><a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ p.source }}</a></template>
          </v-list-item>
          <v-list-item v-if="!rep.people.current.length && !rep.people.former.length" subtitle="No officers or directors resolved. LittleSis and EDGAR coverage is strongest for large listed firms." />
        </v-list>
      </v-window-item>
      <v-window-item value="risk">
        <v-list density="compact" lines="two">
          <v-list-item v-for="i in rep.risk.indicators" :key="i.family" :title="i.label" :subtitle="i.detail || ''">
            <template #prepend><v-icon :icon="sevIcon(i.severity)" :color="sevColor(i.severity)" /></template>
            <template #append><v-chip size="x-small" variant="tonal" :color="sevColor(i.severity)">{{ i.severity ? i.severity : 'No data' }}</v-chip><a v-if="i.source_url" :href="i.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ i.source }}</a><span v-else class="ml-2 text-caption" style="opacity:.7">{{ i.source || '—' }}</span></template>
          </v-list-item>
        </v-list>
        <v-alert variant="tonal" density="compact" class="mt-2" type="info">
          <b v-if="rep.risk.composite != null">Composite {{ rep.risk.composite }}/100.</b> {{ rep.risk.note }}
        </v-alert>
        <p class="text-caption mt-2" style="opacity:.7">{{ rep.risk.disclaimer }}</p>
      </v-window-item>
      <v-window-item value="artifacts">
        <v-table density="compact"><thead><tr><th>Kind</th><th>Title</th><th>Source</th><th>Date</th><th>View</th></tr></thead>
          <tbody><tr v-for="a in rep.artifacts" :key="a.id"><td>{{ a.kind }}</td><td><a :href="a.url" target="_blank" rel="noopener">{{ a.title }}</a></td><td>{{ a.source }}</td><td>{{ a.published_at || (a.retrieved_at || '').slice(0, 10) }}</td><td><v-btn icon="mdi-text-box-search-outline" size="x-small" variant="text" title="View contents" @click="rawId = a.id" /></td></tr></tbody></v-table>
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
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import GraphCanvas from '../components/GraphCanvas.vue'
import ArtifactViewer from '../components/ArtifactViewer.vue'
import { useGraph } from '../stores/graph'
const rawId = ref<string | null>(null)
import { useJobs } from '../stores/jobs'
import { useWorkspace } from '../stores/workspace'
const props = defineProps<{ id: string }>()
const router = useRouter(); const graph = useGraph(); const jobs = useJobs(); const ws = useWorkspace()
const rep = ref<any>(null); const tab = ref('overview'); const enriching = ref(false); const regen_busy = ref(false)
async function load() { rep.value = await api.get(`/api/entities/${props.id}/report`) }
function sevIcon(s: string | null) { return s === 'high' ? 'mdi-alert-octagon' : s === 'medium' ? 'mdi-alert' : s === 'low' ? 'mdi-information-outline' : s === 'clear' ? 'mdi-check-circle-outline' : 'mdi-help-circle-outline' }
function sevColor(s: string | null) { return s === 'high' ? 'error' : s === 'medium' ? 'warning' : s === 'low' ? 'secondary' : s === 'clear' ? 'success' : undefined }
async function enrich() { enriching.value = true; try { await jobs.enqueue(props.id) } finally { enriching.value = false } }
async function regen() { regen_busy.value = true; try { await api.post(`/api/entities/${props.id}/summary`); await load() } catch (e: any) { alert(e.message) } finally { regen_busy.value = false } }
async function openInGraph() { await graph.loadNeighbourhood(props.id, 2, ws.ws.layers); graph.select(props.id); router.push('/') }
watch(tab, async (t) => { if (t === 'graph') { await graph.loadNeighbourhood(props.id, 2, { ...ws.ws.layers, people: true, countries: true }, true); graph.select(props.id) } })
watch(() => jobs.jobs.filter(j => j.entity_id === props.id && ['succeeded', 'empty', 'partial', 'failed', 'timed_out'].includes(j.status)).length, load)
onMounted(load); watch(() => props.id, load)
</script>
<style scoped>
.section { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .6; }
dl { display: grid; grid-template-columns: 110px 1fr; gap: 3px 8px; margin: 6px 0 0; font-size: 13px; }
dt { opacity: .6; } dd { margin: 0; }
</style>
