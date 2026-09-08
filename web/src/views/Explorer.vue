<template>
  <div class="explorer">
    <div class="canvas">
      <GraphCanvas ref="canvas" @expand="expand" />
      <LayerToggles @change="reload" />
      <Legend />
      <div v-if="!graph.nodes.size && !graph.loading" class="empty">
        <div v-if="ws.ws.root_id"><v-btn color="primary" @click="reload">Load {{ ws.ws.root_label }}</v-btn></div>
        <div v-else>No consumer set. <router-link to="/settings">Pick a root</router-link> or search below.</div>
      </div>
      <div class="search">
        <v-autocomplete v-model="picked" :items="hits" item-title="name" item-value="id" :loading="searching" v-model:search="q" placeholder="Search entities, people, UEI, CAGE…" hide-details no-filter clearable prepend-inner-icon="mdi-magnify" @update:model-value="onPick" density="compact" variant="solo" flat>
          <template #item="{ props, item }"><v-list-item v-bind="props" :subtitle="[item.raw.label, item.raw.uei && `UEI ${item.raw.uei}`].filter(Boolean).join(' · ')" /></template>
        </v-autocomplete>
      </div>
      <div class="cypher-peek" v-if="graph.lastCypher">
        <details><summary>last query</summary><CypherBlock :statement="graph.lastCypher.statement" :params="graph.lastCypher.params" /></details>
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
import { onMounted, ref, watch } from 'vue'
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
const q = ref(''); const hits = ref<any[]>([]); const searching = ref(false); const picked = ref<string | null>(null)
let t: any
watch(q, (v) => { clearTimeout(t); if (!v || v.length < 2) return; t = setTimeout(async () => { searching.value = true; try { hits.value = (await api.get(`/api/graph/search?${qs({ q: v, limit: 10 })}`)).results } finally { searching.value = false } }, 250) })
async function onPick(id: string | null) { if (!id) return; await graph.loadNeighbourhood(id, 1, ws.ws.layers); graph.select(id) }
async function reload() { if (ws.ws.root_id) await graph.loadNeighbourhood(ws.ws.root_id, ws.depth, ws.ws.layers, true) }
async function expand(id: string) { await graph.loadNeighbourhood(id, 1, ws.ws.layers) }
onMounted(async () => { if (!ws.loaded) await ws.load(); if (!graph.nodes.size) reload() })
watch(() => ws.depth, reload)
</script>
<style scoped>
.explorer { display: grid; grid-template-columns: 1fr 380px; height: calc(100vh - 48px); }
.canvas { position: relative; }
.side { display: grid; grid-template-rows: minmax(120px, 42%) 1fr; border-left: 1px solid rgba(128,128,128,.2); min-height: 0; }
.inspector-pane { border-bottom: 1px solid rgba(128,128,128,.2); overflow: auto; min-height: 0; }
.chat-pane { min-height: 0; }
.hint { padding: 12px; opacity: .6; font-size: 13px; }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: .8; }
.search { position: absolute; top: 44px; left: 12px; width: 360px; }
.cypher-peek { position: absolute; right: 56px; bottom: 12px; max-width: 520px; font-size: 12px; }
.cypher-peek summary { cursor: pointer; opacity: .6; text-align: right; }
</style>
