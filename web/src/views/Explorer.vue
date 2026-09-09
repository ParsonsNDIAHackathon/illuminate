<template>
  <div class="explorer" :class="{ 'map-mode': viewMode === 'map' }" ref="root" :style="{ '--side-width': `${sideW}px` }">
    <div class="canvas" ref="canvasBox">
      <GraphMap v-if="viewMode === 'map'" :location-code="String(route.query.map_location || '')" @select-news="selectNews" />
      <GraphCanvas v-show="viewMode === 'graph'" :active="viewMode === 'graph'" ref="canvas" @expand="expand" />
      <div class="toolbar">
        <v-btn-toggle :model-value="viewMode" mandatory density="compact" color="primary" aria-label="Graph visualization" @update:model-value="changeView">
          <v-btn value="graph" size="small">Graph</v-btn><v-btn value="map" size="small">Map</v-btn>
        </v-btn-toggle>
        <!-- Both menus follow the pattern on illuminate-map: the controls fold away so the
             canvas keeps its corners, and the properties card gets the right edge. -->
        <v-menu :close-on-content-click="false" location="bottom start">
          <template #activator="{ props }">
            <v-btn v-bind="props" size="small" prepend-icon="mdi-layers-outline" append-icon="mdi-menu-down"
                   title="Which kinds of node the canvas draws">Layers</v-btn>
          </template>
          <v-card class="pa-3 layers-menu"><LayerToggles @change="reload" /></v-card>
        </v-menu>
        <v-menu v-if="viewMode === 'graph'" location="bottom start">
          <template #activator="{ props }">
            <v-btn v-bind="props" size="small" prepend-icon="mdi-tune-variant" append-icon="mdi-menu-down"
                   title="Fit, re-lay out and clear the canvas">Canvas</v-btn>
          </template>
          <v-list density="compact" class="canvas-menu">
            <v-list-item prepend-icon="mdi-fit-to-screen" title="Fit to screen" @click="canvas?.fit()" />
            <v-list-item prepend-icon="mdi-graph-outline" title="Re-layout" @click="canvas?.layout()" />
            <v-list-item prepend-icon="mdi-format-color-fill" title="Clear styles"
                         subtitle="Drop the highlights the chat applied" @click="graph.clearStyleOps()" />
            <v-list-item prepend-icon="mdi-broom" title="Clear canvas"
                         subtitle="Take every node off the view" @click="graph.clear()" />
          </v-list>
        </v-menu>
        <!-- The icon says which of the two states you are in: a crosshair only means something
             when the canvas is actually narrowed to one program. -->
        <v-select class="focus" :model-value="graph.focusId" :items="focusItems" item-title="name" item-value="id"
                  density="compact" variant="solo" flat hide-details
                  :prepend-inner-icon="graph.focusId ? 'mdi-target' : 'mdi-earth'"
                  :title="graph.focusId ? 'Showing one program and its supply chain — pick Everything to see them all' : 'Showing every program'"
                  @update:model-value="setFocus" />
      </div>
      <Legend v-if="viewMode === 'graph'" />
      <!-- Properties ride on the canvas beside the node they describe, so the conversation
           below never has to give up its space to them. -->
      <SelectionCard :show-acled="viewMode === 'map'" @expand="expand" />
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
    <!-- Double-click restores the default width, so a drag can always be undone without guessing. -->
    <div class="gutter" :class="{ dragging }" title="Drag to resize — double-click to reset"
         @pointerdown="startDrag" @dblclick="setWidth(DEFAULT_W)"></div>
    <div class="side"><ChatRail /></div>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAcled } from '../stores/acled'
import { useNews } from '../stores/news'
import type { NewsArticle } from '../newsMap'
import GraphMap from '../components/GraphMap.vue'
import { api, qs } from '../api/client'
import GraphCanvas from '../components/GraphCanvas.vue'
import SelectionCard from '../components/SelectionCard.vue'
import ChatRail from '../components/ChatRail.vue'
import Legend from '../components/Legend.vue'
import LayerToggles from '../components/LayerToggles.vue'
import CypherBlock from '../components/CypherBlock.vue'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
const graph = useGraph(); const ws = useWorkspace()
const news = useNews()
const acled = useAcled()
watch(() => acled.selectedId, id => {
  if (id) { graph.select(null); graph.selectEdge(null); news.selectedUrl = null }
})
function selectNews(article: NewsArticle) {
  acled.selectedId = ''
  graph.select(null)
  graph.selectEdge(null)
  news.selectedUrl = article.url
}
watch([() => graph.selectedId, () => graph.selectedEdgeId], ([node, edge]) => {
  if (node || edge) { news.selectedUrl = null; acled.selectedId = '' }
})
const route = useRoute(); const router = useRouter()
const viewMode = ref(route.query.view === 'map' ? 'map' : 'graph')
const graphLayers = computed(() => viewMode.value === 'map' ? { ...ws.ws.layers, countries: true } : ws.ws.layers)
async function changeView(value: string) {
  await router.replace({ query: { ...route.query, view: value, map_location: undefined } })
}
const canvas = ref<InstanceType<typeof GraphCanvas>>()
const canvasBox = ref<HTMLElement>()
const q = ref(''); const hits = ref<any[]>([]); const searching = ref(false); const open = ref(false)
// The chat is the main way to work the graph, so it gets a panel wide enough to read a
// paragraph in — and a handle, because how much canvas a question needs is the user's call.
const WIDTH_KEY = 'illuminate.side.width'
const DEFAULT_W = 440, MIN_W = 320, MIN_CANVAS = 420
const root = ref<HTMLElement>()
const dragging = ref(false)
const sideW = ref(clamp(Number(localStorage.getItem(WIDTH_KEY)) || DEFAULT_W))
function clamp(px: number) { return Math.max(MIN_W, Math.min(px, Math.max(MIN_W, window.innerWidth - MIN_CANVAS))) }
function setWidth(px: number) { sideW.value = clamp(px); localStorage.setItem(WIDTH_KEY, String(sideW.value)) }
// preventDefault() here would suppress the compatibility mouse events the double-click
// reset rides on, so the drag guards against text selection with CSS instead.
function startDrag(e: PointerEvent) {
  if (e.button !== 0) return
  dragging.value = true
  const right = root.value!.getBoundingClientRect().right
  const move = (ev: PointerEvent) => { sideW.value = clamp(right - ev.clientX) }
  const up = () => {
    dragging.value = false
    setWidth(sideW.value)
    window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
}
// A window that shrank below what the stored width leaves for the canvas gives the canvas its floor back.
function onResize() { sideW.value = clamp(sideW.value) }
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
onMounted(async () => { window.addEventListener('resize', onResize); await applyRoute(); graph.loadPrograms() })
watch(() => route.fullPath, applyRoute)
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
// The card is measured rather than assumed: it is only in the DOM once something is
// selected, so this waits a tick for it before asking where its edge fell.
watch(() => graph.selectedId, async (id) => {
  if (!id || viewMode.value !== 'graph') return
  await nextTick()
  const box = canvasBox.value?.getBoundingClientRect()
  const card = canvasBox.value?.querySelector('.selection-card')?.getBoundingClientRect()
  if (!box || !card) return
  canvas.value?.panIntoView(id, card.left - box.left)
})
// Depth only shapes a focused view; the whole graph is not walked from a root.
watch(() => ws.depth, () => { if (graph.focusId) reload() })
</script>
<style scoped>
.explorer { display: grid; grid-template-columns: minmax(0, 1fr) 6px var(--side-width); height: calc(100vh - 48px); }
.explorer:has(.gutter.dragging) { user-select: none; cursor: col-resize; }
.canvas { position: relative; min-width: 0; min-height: 0; }
.gutter { cursor: col-resize; background: rgba(128,128,128,.2); transition: background .12s; user-select: none; touch-action: none; }
.gutter:hover, .gutter.dragging { background: rgb(var(--v-theme-primary)); }
.side { min-height: 0; min-width: 0; }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: .8; }
.toolbar { position: absolute; top: 8px; left: 12px; z-index: 5; display: flex; align-items: center; gap: 8px; }
.layers-menu { max-width: 340px; }
.canvas-menu { min-width: 260px; }
.focus { width: 230px; }
.search { position: absolute; top: 52px; left: 12px; width: 360px; z-index: 5; }
.hits { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; max-height: 320px; overflow: auto; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,.25); }
.notes { position: absolute; right: 12px; bottom: 12px; max-width: 520px; font-size: 12px; text-align: right; }
.notes summary { cursor: pointer; opacity: .6; }
.warn { color: #f59e0b; }
@media (max-width: 1100px) {
  .toolbar { right:12px; flex-wrap:wrap; }
  .focus { width:100%; }
  .search { top:100px; width:calc(100% - 24px); }
  .map-mode :deep(.geo-view) { padding-top:154px; }
}
@media (max-width: 800px) {
  .gutter { display:none; }
  .explorer { grid-template-columns:1fr; grid-template-rows:minmax(500px,70dvh) minmax(500px,70dvh); height:auto; }
  .map-mode.explorer { grid-template-rows:minmax(710px,80dvh) minmax(500px,70dvh); }
  .map-mode .canvas { min-height:710px; }
}
</style>
