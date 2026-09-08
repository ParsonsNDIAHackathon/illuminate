<template>
  <div class="explorer">
    <div class="canvas">
      <GraphCanvas ref="canvas" @expand="expand" />
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
onMounted(async () => { if (!ws.loaded) await ws.load(); graph.loadPrograms(); if (!graph.nodes.size) reload() })
// Depth only shapes a focused view; the whole graph is not walked from a root.
watch(() => ws.depth, () => { if (graph.focusId) reload() })
</script>
<style scoped>
.explorer { display: grid; grid-template-columns: 1fr 380px; height: calc(100vh - 48px); }
.canvas { position: relative; }
.side { display: grid; grid-template-rows: minmax(120px, 42%) 1fr; border-left: 1px solid rgba(128,128,128,.2); min-height: 0; }
.inspector-pane { border-bottom: 1px solid rgba(128,128,128,.2); overflow: auto; min-height: 0; }
.chat-pane { min-height: 0; }
.hint { padding: 12px; opacity: .6; font-size: 13px; }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: .8; }
.toolbar { position: absolute; top: 8px; left: 12px; z-index: 5; display: flex; align-items: center; gap: 8px; }
.focus { width: 230px; }
.search { position: absolute; top: 52px; left: 12px; width: 360px; z-index: 5; }
.hits { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; max-height: 320px; overflow: auto; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,.25); }
.notes { position: absolute; right: 56px; bottom: 12px; max-width: 520px; font-size: 12px; text-align: right; }
.notes summary { cursor: pointer; opacity: .6; }
.warn { color: #f59e0b; }
</style>
