<template>
  <div class="explorer" :class="{ 'map-mode': viewMode === 'map' }">
    <div class="canvas">
      <GraphMap v-if="viewMode === 'map'" :location-code="String(route.query.map_location || '')" @select-news="selectNews" />
      <GraphCanvas v-show="viewMode === 'graph'" :active="viewMode === 'graph'" ref="canvas" @expand="expand" />
      <div class="toolbar">
        <v-btn-toggle :model-value="viewMode" mandatory density="compact" color="primary" aria-label="Graph visualization" @update:model-value="changeView">
          <v-btn value="graph" size="small">Graph</v-btn><v-btn value="map" size="small">Map</v-btn>
        </v-btn-toggle>
        <v-menu :close-on-content-click="false"><template #activator="{ props }"><v-btn v-bind="props" size="small">Layers</v-btn></template><v-card class="pa-3"><LayerToggles @change="reload" /></v-card></v-menu>
        <v-select class="focus" :model-value="graph.focusId" :items="focusItems" item-title="name" item-value="id"
                  density="compact" variant="solo" flat hide-details prepend-inner-icon="mdi-target"
                  :title="graph.focusId ? 'Showing one program and its supply chain — pick Everything to see them all' : 'Showing every program'"
                  @update:model-value="setFocus" />
      </div>
      <Legend v-if="viewMode === 'graph'" />
      <div v-if="viewMode === 'graph' && !graph.nodes.size && !graph.loading" class="empty">
        <v-btn color="primary" @click="reload">Load graph</v-btn>
      </div>
      <div class="search">
        <v-text-field v-model="q" :loading="searching" placeholder="Search entities, people, UEI, CAGE…" hide-details clearable prepend-inner-icon="mdi-magnify" density="compact" variant="solo" flat @update:focused="open = $event" @keydown.esc="open = false" @keydown.enter="hits[0] && onPick(hits[0].id)" />
        <!-- mousedown.prevent keeps the field focused so a click here doesn't blur-close the list first -->
        <v-list v-if="open && hits.length" class="hits" density="compact" @mousedown.prevent>
          <v-list-item v-for="h in hits" :key="h.id" :title="h.name" :subtitle="[h.label, h.uei && `UEI ${h.uei}`].filter(Boolean).join(' · ')" @click="onPick(h.id)" />
        </v-list>
      </div>
      <div class="notes">
        <span v-if="graph.truncated" class="warn">graph capped — narrow to one program or turn layers off</span>
        <details v-if="graph.lastCypher"><summary>last query</summary><CypherBlock :statement="graph.lastCypher.statement" :params="graph.lastCypher.params" /></details>
      </div>
    </div>
    <div class="side">
      <div class="inspector-pane">
        <NewsInspector v-if="news.selected" />
        <Inspector v-else-if="graph.selected" @expand="expand" />
        <EdgeInspector v-else-if="graph.selectedEdge" />
        <div v-else class="hint">Select a node or an edge to inspect it. Double-click a node to expand.</div>
      </div>
      <div class="chat-pane"><ChatRail /></div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NewsInspector from '../components/NewsInspector.vue'
import { useNews } from '../stores/news'
import type { NewsArticle } from '../newsMap'
import GraphMap from '../components/GraphMap.vue'
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
const news = useNews()
function selectNews(article: NewsArticle) {
  graph.select(null)
  graph.selectEdge(null)
  news.selectedUrl = article.url
}
watch([() => graph.selectedId, () => graph.selectedEdgeId], ([node, edge]) => {
  if (node || edge) news.selectedUrl = null
})
const route = useRoute(); const router = useRouter()
const viewMode = ref(route.query.view === 'map' ? 'map' : 'graph')
const graphLayers = computed(() => viewMode.value === 'map' ? { ...ws.ws.layers, countries: true } : ws.ws.layers)
async function changeView(value: string) {
  await router.replace({ query: { ...route.query, view: value, map_location: undefined } })
}
const q = ref(''); const hits = ref<any[]>([]); const searching = ref(false); const open = ref(false)
// The programs the canvas can be narrowed to. The store keeps this current from live
// deltas, so a program added while this view is open shows up here without a reload.
const focusItems = computed(() => [{ id: null, name: 'Everything' }, ...graph.programs])
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
  if (!graph.nodes.has(id)) await graph.loadNeighbourhood(id, 1, graphLayers.value)
  graph.select(id)
}
async function setFocus(id: string | null) {
  await router.replace({ query: { ...route.query, root_id: id || undefined, map_location: undefined } })
}
async function reload() {
  if (graph.focusId) await graph.focus(graph.focusId, graph.focusLabel, ws.depth, graphLayers.value)
  else await graph.loadAll(graphLayers.value)
}
async function expand(id: string) { await graph.loadNeighbourhood(id, 1, graphLayers.value) }
async function applyRoute() {
  const previousView = viewMode.value
  viewMode.value = route.query.view === 'map' ? 'map' : 'graph'
  if (!ws.loaded) await ws.load()
  if (route.query.map_location) { q.value = ''; graph.setFilter('') }
  const root = String(route.query.root_id || '') || null
  if (root !== graph.focusId) {
    if (root) await graph.focus(root, graph.programs.find(p => p.id === root)?.name || null, ws.depth, graphLayers.value)
    else await graph.loadAll(graphLayers.value)
  } else if (!graph.nodes.size || (viewMode.value === 'map' && previousView !== 'map')) await reload()
}
onMounted(async () => { await applyRoute(); graph.loadPrograms() })
watch(() => route.fullPath, applyRoute)
// Depth only shapes a focused view; the whole graph is not walked from a root.
watch(() => ws.depth, () => { if (graph.focusId) reload() })
</script>
<style scoped>
.explorer { display: grid; grid-template-columns: minmax(0,1fr) 380px; height: calc(100vh - 48px); }
.canvas { position: relative; min-width:0; min-height:0; }
.side { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(120px, 42%) 1fr; border-left: 1px solid rgba(128,128,128,.2); min-height: 0; }
.inspector-pane { border-bottom: 1px solid rgba(128,128,128,.2); overflow: auto; min-height: 0; }
.chat-pane { min-height: 0; }
.hint { padding: 12px; opacity: .6; font-size: 13px; }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: .8; }
.toolbar { position: absolute; top: 8px; left: 12px; z-index: 5; display: flex; align-items: center; gap: 8px; }
.focus { width: 200px; min-width:120px; }
.search { position: absolute; top: 52px; left: 12px; width: 360px; z-index: 5; }
.hits { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; max-height: 320px; overflow: auto; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,.25); }
.notes { position: absolute; right: 56px; bottom: 12px; max-width: 520px; font-size: 12px; text-align: right; }
.notes summary { cursor: pointer; opacity: .6; }
.warn { color: #f59e0b; }
@media (max-width: 1100px) {
  .toolbar { right:12px; flex-wrap:wrap; }
  .focus { width:100%; }
  .search { top:100px; width:calc(100% - 24px); }
  .map-mode :deep(.geo-view) { padding-top:154px; }
}
@media (max-width: 800px) {
  .explorer { grid-template-columns:1fr; grid-template-rows:minmax(500px,70dvh) minmax(500px,70dvh); height:auto; }
  .map-mode.explorer { grid-template-rows:minmax(710px,80dvh) minmax(500px,70dvh); }
  .map-mode .canvas { min-height:710px; }
}
</style>
