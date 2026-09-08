<template>
  <div class="inspector" v-if="node">
    <div class="d-flex align-center ga-2 mb-1">
      <v-chip size="x-small" variant="tonal">{{ node.label }}<span v-if="p.kind"> · {{ p.kind }}</span></v-chip>
      <v-chip v-if="p.simulated" size="x-small" color="warning" variant="tonal">SIMULATED</v-chip>
      <v-chip v-if="p.flagged" size="x-small" color="error" variant="tonal" :title="p.flag_reason">flagged</v-chip>
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="x-small" @click="graph.select(null)" />
    </div>
    <h3 class="name">{{ node.name }}</h3>
    <div class="ids text-caption">
      <span v-if="p.uei">UEI {{ p.uei }}</span><span v-if="p.cage"> · CAGE {{ p.cage }}</span><span v-if="p.lei"> · LEI {{ p.lei }}</span><span v-if="p.ticker"> · {{ p.ticker }}</span>
    </div>
    <div class="d-flex flex-wrap ga-1 my-2" v-if="node.label === 'Entity'">
      <v-chip v-if="detail?.parent_seat && !String(detail.parent_seat.code).startsWith('US')" size="x-small" color="error" variant="tonal">Foreign ultimate parent</v-chip>
      <v-chip v-if="supplies.some((s:any) => s.sole_source)" size="x-small" color="warning" variant="tonal">Sole source</v-chip>
      <v-chip v-if="detail?.tier" size="x-small" variant="tonal">Tier {{ detail.tier }}</v-chip>
    </div>
    <template v-if="node.label === 'Entity' && detail">
      <section>
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
        <template v-if="p.url"><dt>Page</dt><dd><SourceLink :href="p.url" :artifact-id="node.id">{{ p.url }}</SourceLink></dd></template>
        <template v-if="p.published_at"><dt>Published</dt><dd>{{ p.published_at }}</dd></template>
        <template v-if="p.amount"><dt>Amount</dt><dd>${{ Number(p.amount).toLocaleString() }}</dd></template>
        <template v-if="p.award_id"><dt>Award</dt><dd>{{ p.award_id }}</dd></template>
        <template v-if="p.form"><dt>Form</dt><dd>{{ p.form }}</dd></template>
      </dl>
    </section>
    <div class="d-flex flex-wrap ga-1 mt-2">
      <v-btn v-if="node.label === 'Artifact'" prepend-icon="mdi-text-box-search-outline" @click="rawId = node.id">Contents</v-btn>
      <v-btn v-if="node.label === 'Artifact'" prepend-icon="mdi-eye-outline" @click="viewId = node.id">View</v-btn>
      <v-btn v-if="node.label === 'Entity'" prepend-icon="mdi-file-document-outline" :to="`/entities/${node.id}`">Report</v-btn>
      <v-btn prepend-icon="mdi-arrow-expand-all" @click="$emit('expand', node.id)">Expand</v-btn>
      <v-btn v-if="isProgram" prepend-icon="mdi-sitemap-outline" @click="openDiscover" :loading="discovering">Find suppliers</v-btn>
      <v-btn v-if="node.label === 'Entity'" prepend-icon="mdi-auto-fix" @click="enrich" :loading="enriching">Enrich</v-btn>
      <v-btn v-if="node.label === 'Entity'" prepend-icon="mdi-target" variant="text" @click="setRoot" title="Make this the consumer (root)">Set as root</v-btn>
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
import { api } from '../api/client'
import { useGraph } from '../stores/graph'
import { useJobs } from '../stores/jobs'
import { useWorkspace } from '../stores/workspace'
import ArtifactViewer from './ArtifactViewer.vue'
import SourceFrame from './SourceFrame.vue'
import SourceLink from './SourceLink.vue'
const graph = useGraph(); const jobs = useJobs(); const ws = useWorkspace()
const rawId = ref<string | null>(null); const viewId = ref<string | null>(null)
defineEmits<{ (e: 'expand', id: string): void }>()
const node = computed(() => graph.selected)
const p = computed(() => node.value?.props || {})
const detail = ref<any>(null); const supplies = ref<any[]>([]); const personRoles = ref<any[]>([]); const enriching = ref(false)
const isProgram = computed(() => node.value?.label === 'Entity' && p.value.kind === 'program')
const discoverDlg = ref(false); const discovering = ref(false); const discoverError = ref('')
const kw = ref<string[]>([]); const agency = ref(''); const maxSubs = ref<number | null>(null)
watch(node, async (n) => {
  detail.value = null; supplies.value = []; personRoles.value = []
  if (!n) return
  if (n.label === 'Entity') {
    try {
      const rep = await api.get(`/api/entities/${n.id}/report`)
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
async function setRoot() { await ws.save({ root_id: node.value!.id, root_label: node.value!.name }) }
</script>
<style scoped>
.inspector { padding: 12px; font-size: 13px; overflow-y: auto; height: 100%; }
.name { font-size: 16px; line-height: 1.2; margin: 2px 0; }
.ids { opacity: .7; }
section { margin-top: 10px; }
h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .6; margin-bottom: 4px; }
dl { display: grid; grid-template-columns: 90px 1fr; gap: 2px 8px; margin: 0; }
dt { opacity: .6; } dd { margin: 0; }
</style>
