<template>
  <div class="explorer">
    <div class="canvas">
      <GraphCanvas ref="canvas" :show-simulation-notice="false" @expand="expand" />
      <div class="toolbar">
        <LayerToggles @change="reload" />
        <v-select class="focus" :model-value="graph.focusId" :items="focusItems" item-title="name" item-value="id"
                  density="compact" variant="solo" flat hide-details prepend-inner-icon="mdi-target"
                  :title="graph.focusId ? 'Showing one program and its supply chain — pick Everything to see them all' : 'Showing every program'"
                  @update:model-value="setFocus" />
      </div>
      <Legend />
      <div v-if="!graph.nodes.size && !graph.loading" class="empty">
        <v-btn color="primary" @click="reload">Load graph</v-btn>
      </div>
      <div class="canvas-overlays">
        <div class="search">
          <v-text-field v-model="q" :loading="searching" placeholder="Search entities, people, UEI, CAGE…" hide-details clearable prepend-inner-icon="mdi-magnify" density="compact" variant="solo" flat @update:focused="open = $event" @keydown.esc="open = false" @keydown.enter="hits[0] && onPick(hits[0].id)" />
          <!-- mousedown.prevent keeps the field focused so a click here doesn't blur-close the list first -->
          <v-list v-if="open && hits.length" class="hits" density="compact" @mousedown.prevent>
            <v-list-item v-for="h in hits" :key="h.id" :title="h.name" :subtitle="[h.label, h.uei && `UEI ${h.uei}`].filter(Boolean).join(' · ')" @click="onPick(h.id)" />
          </v-list>
        </div>
        <div v-if="hasSimulation" class="simulation-notice">
          <strong>SIMULATION DATA</strong>
          <span>Scenario material for analysis — not an allegation or verified finding.</span>
        </div>
        <div v-if="graph.focusIds.length" class="focus-title">
          <span>REPORT TRACE</span>
          <strong>{{ graph.reportFocusLabel || 'Selected risk indicator' }}</strong>
          <small>Loaded mission context remains visible; unrelated elements are recessed.</small>
          <small v-if="graph.focusUnavailableIds.length" class="focus-missing">{{ graph.focusUnavailableIds.length }} referenced element{{ graph.focusUnavailableIds.length === 1 ? '' : 's' }} unavailable in the loaded graph.</small>
          <div class="focus-links">
            <router-link :to="`/entities/${graph.focusVendorId}`">Vendor report</router-link>
            <a v-if="route.query.evidence" :href="String(route.query.evidence)" target="_blank" rel="noopener">Matching evidence</a>
            <span v-else>No matching evidence destination</span>
          </div>
        </div>
      </div>
      <div class="notes">
        <span v-if="graph.truncated" class="warn">graph capped — narrow to one program or turn layers off</span>
        <details v-if="graph.lastCypher"><summary>last query</summary><CypherBlock :statement="graph.lastCypher.statement" :params="graph.lastCypher.params" /></details>
      </div>
    </div>
    <div class="side">
      <div class="inspector-pane">
        <Inspector v-if="graph.selected" @expand="expand" />
        <EdgeInspector v-else-if="graph.selectedEdge" />
        <div v-else class="hint">Select a node or an edge to inspect it. Double-click a node to expand.</div>
      </div>
      <div class="chat-pane"><ChatRail /></div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, qs } from '../api/client'
import GraphCanvas from '../components/GraphCanvas.vue'
import Inspector from '../components/Inspector.vue'
import EdgeInspector from '../components/EdgeInspector.vue'
import ChatRail from '../components/ChatRail.vue'
import Legend from '../components/Legend.vue'
import LayerToggles from '../components/LayerToggles.vue'
import CypherBlock from '../components/CypherBlock.vue'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
const graph = useGraph(); const ws = useWorkspace()
const route = useRoute()
const q = ref(''); const hits = ref<any[]>([]); const searching = ref(false); const open = ref(false)
// The programs the canvas can be narrowed to. The store keeps this current from live
// deltas, so a program added while this view is open shows up here without a reload.
const focusItems = computed(() => [{ id: null, name: 'Everything' }, ...graph.programs])
const hasSimulation = computed(() => graph.nodeList.some(n => n.props?.simulated) || graph.edgeList.some(e => e.props?.simulated))
let t: any
// A plain text field, not an autocomplete: the typed text — and the canvas filter it drives — must survive blur.
watch(q, (v) => {
  graph.setFilter(v && v.length >= 2 ? v : '')
  clearTimeout(t)
  if (!v || v.length < 2) { hits.value = []; return }
  t = setTimeout(async () => { searching.value = true; try { hits.value = (await api.get(`/api/graph/search?${qs({ q: v, limit: 10 })}`)).results; open.value = true } finally { searching.value = false } }, 250)
})
// A search hit is already on the canvas when nothing is filtered out; pull it in only if it isn't.
async function onPick(id: string) {
  open.value = false; q.value = ''
  if (!graph.nodes.has(id)) await graph.loadNeighbourhood(id, 1, ws.ws.layers)
  graph.select(id)
}
async function setFocus(id: string | null) {
  if (id) await graph.focus(id, graph.programs.find(p => p.id === id)?.name || null, ws.depth, ws.ws.layers)
  else await graph.loadAll(ws.ws.layers)
}
async function reload() {
  if (graph.focusId) await graph.focus(graph.focusId, graph.focusLabel, ws.depth, ws.ws.layers)
  else await graph.loadAll(ws.ws.layers)
}
async function expand(id: string) { await graph.loadNeighbourhood(id, 1, ws.ws.layers) }
async function applyRouteFocus() {
  if (!ws.loaded) await ws.load()
  const ids = String(route.query.focus || '').split(',').filter(Boolean)
  const vendor = String(route.query.vendor || '')
  if (vendor) {
    if (ws.ws.root_id && !graph.nodes.has(ws.ws.root_id)) await graph.loadNeighbourhood(ws.ws.root_id, ws.depth, ws.ws.layers)
    // A report trace may reference people, locations, or evidence hidden by the normal workspace
    // layers. Merge those elements for the trace without changing the user's layer preferences.
    await graph.loadNeighbourhood(vendor, Math.max(2, ws.depth), {
      ...ws.ws.layers,
      people: true,
      countries: true,
      artifacts: true,
      categories: true,
      sources: true,
      claims: true,
    })
    graph.setFocus(ids, String(route.query.finding || 'Selected risk indicator'), vendor, String(route.query.family || ''))
  } else {
    graph.clearFocus()
    if (!graph.nodes.size) await reload()
  }
}
onMounted(async () => { await applyRouteFocus(); graph.loadPrograms() })
watch(() => route.fullPath, applyRouteFocus)
// Depth only shapes a focused view; the whole graph is not walked from a root.
watch(() => ws.depth, () => { if (graph.focusId) reload() })
</script>
<style scoped>
.explorer { display: grid; grid-template-columns: minmax(0, 1fr) 380px; height: calc(100dvh - 48px); min-width: 0; }
.canvas { position: relative; min-width: 0; min-height: 0; }
.side { display: grid; grid-template-rows: minmax(120px, 42%) 1fr; border-left: 1px solid rgba(128,128,128,.2); min-width: 0; min-height: 0; }
.inspector-pane { border-bottom: 1px solid rgba(128,128,128,.2); overflow: auto; min-width: 0; min-height: 0; }
.chat-pane { min-width: 0; min-height: 0; }
.hint { padding: 12px; opacity: .6; font-size: 13px; }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: .8; }
.toolbar { position: absolute; top: 8px; left: 12px; right: 54px; z-index: 5; display: flex; align-items: center; gap: 8px; min-width: 0; max-width: calc(100% - 66px); }
.focus { flex: 0 1 230px; min-width: 150px; }
.canvas-overlays { position: absolute; top: 52px; left: 12px; z-index: 7; display: grid; gap: 8px; width: 360px; }
.search { position: relative; z-index: 1; width: 100%; }
.hits { position: absolute; top: 100%; left: 0; right: 0; z-index: 2; margin-top: 4px; max-height: 320px; overflow: auto; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,.25); }
.simulation-notice { display: flex; align-items: center; gap: 10px; max-height: 96px; overflow: auto; padding: 8px 14px; border: 2px solid #9a6700; border-radius: 4px; background: #fff4cf; color: #563b00; box-shadow: 0 3px 12px rgba(60,45,0,.16); font-size: 12px; letter-spacing: .01em; }
.simulation-notice strong { font-size: 11px; letter-spacing: .12em; white-space: nowrap; }
.focus-title { display: grid; max-height: 180px; overflow: auto; padding: 9px 12px; border-left: 4px solid #006b62; background: rgba(245,248,240,.94); color: #173b37; box-shadow: 0 2px 10px rgba(25,45,40,.12); }
.focus-title span { color: #006b62; font-size: 9px; font-weight: 800; letter-spacing: .14em; }
.focus-title strong { font-size: 13px; line-height: 1.25; }
.focus-title small { opacity: .68; font-size: 10px; margin-top: 2px; }
.focus-title .focus-missing { margin-top: 6px; color: #8a321f; font-weight: 700; opacity: 1; }
.focus-links { display: flex; gap: 10px; align-items: center; margin-top: 7px; padding-top: 6px; border-top: 1px solid rgba(0,107,98,.2); font-size: 11px; }
.focus-links a { color: #006b62; font-weight: 750; text-decoration: none; }
.focus-links span { opacity: .58; }
.notes { position: absolute; right: 56px; bottom: 12px; max-width: 520px; font-size: 12px; text-align: right; }
.notes summary { cursor: pointer; opacity: .6; }
.warn { color: #f59e0b; }
@media (max-width: 900px) {
  .explorer { display: grid; grid-template-columns: 1fr; grid-template-rows: minmax(420px, 58dvh) minmax(480px, 72dvh); height: auto; min-height: calc(100dvh - 48px); }
  .side { grid-template-rows: minmax(160px, 40%) minmax(280px, 1fr); border-left: 0; border-top: 1px solid rgba(128,128,128,.25); }
  .toolbar { left: 8px; right: 50px; display: grid; max-width: calc(100% - 58px); }
  .focus { width: 100%; min-width: 0; }
  .canvas-overlays { top: 96px; left: 8px; width: calc(100% - 68px); }
  .notes { display: none; }
}
@media (max-width: 420px) {
  .explorer { grid-template-rows: minmax(390px, 56dvh) minmax(480px, 76dvh); }
  .simulation-notice { align-items: flex-start; flex-direction: column; gap: 2px; padding: 6px 9px; font-size: 10px; }
}
</style>
