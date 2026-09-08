<template>
  <div class="finding-list">
    <div class="list-intro">
      <strong>Graph as a list</strong>
      <span>Use Tab and Enter to investigate without the canvas.</span>
    </div>
    <div v-if="!rows.length" class="list-empty">No graph items are loaded. Choose a program or load the graph first.</div>
    <ul v-else aria-label="Graph findings and paths">
      <li v-for="row in rows" :key="row.key" :class="{ active: row.active }">
        <button type="button" @click="select(row)" @keydown.enter.prevent="select(row)">
          <v-icon :icon="row.kind === 'node' ? 'mdi-circle-outline' : 'mdi-arrow-right'" size="14" />
          <span><strong>{{ row.title }}</strong><small>{{ row.detail }}</small></span>
        </button>
        <div class="actions">
          <v-btn size="x-small" variant="text" @click="inspect(row)">Inspect</v-btn>
          <v-btn v-if="row.kind === 'node'" size="x-small" variant="text" @click="$emit('expand', row.id)">Expand</v-btn>
          <v-btn v-if="row.evidenceUrl" size="x-small" variant="text" :href="row.evidenceUrl" target="_blank" rel="noopener">Evidence</v-btn>
        </div>
      </li>
    </ul>
    <v-btn v-if="resultIds?.length" size="small" variant="text" :prepend-icon="showAll ? 'mdi-arrow-left' : 'mdi-sitemap-outline'" @click="showAll = !showAll">
      {{ showAll ? 'Return to finding path' : 'Show full graph context' }}
    </v-btn>
    <v-btn v-else-if="graph.focusIds.length" size="small" variant="text" prepend-icon="mdi-arrow-left" @click="graph.clearFocus()">Return to full context</v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useGraph } from '../stores/graph'
import { deriveFindingPath } from '../graphFocusPath'
const graph = useGraph()
const props = defineProps<{ resultIds?: string[]; resultKey?: string }>()
const showAll = ref(false)
watch(() => props.resultKey, () => { showAll.value = false })
const emit = defineEmits<{ (e: 'expand', id: string): void; (e: 'inspect'): void }>()
type Row = { key: string; id: string; kind: 'node' | 'edge'; title: string; detail: string; evidenceUrl?: string; active: boolean }
const relatedIds = computed(() => {
  if (props.resultIds?.length && !showAll.value) return new Set(props.resultIds)
  if (!graph.focusIds.length) return null
  return deriveFindingPath(graph.nodeList, graph.edgeList, graph.focusIds, graph.focusVendorId, graph.focusId, graph.focusFamily).pathIds
})
const rows = computed<Row[]>(() => {
  const focus = relatedIds.value
  const nodes = graph.nodeList
    .filter(n => !focus || focus.has(n.id))
    .map(n => ({
      key: `n:${n.id}`, id: n.id, kind: 'node' as const, title: n.name,
      detail: `${n.label}${n.props?.simulated ? ' · simulated' : ' · live/curated'}${n.id === graph.focusVendorId ? ' · affected vendor' : ''}`,
      evidenceUrl: n.props?.source_url || n.props?.url,
      active: graph.selectedId === n.id,
    }))
  const edges = graph.edgeList
    .filter(e => !focus || focus.has(e.id))
    .map(e => ({
      key: `e:${e.id}`, id: e.id, kind: 'edge' as const,
      title: `${graph.nodes.get(e.source)?.name || e.source} → ${graph.nodes.get(e.target)?.name || e.target}`,
      detail: `${e.type.replace(/_/g, ' ').toLowerCase()}${e.props?.simulated ? ' · simulated' : ''}`,
      evidenceUrl: e.props?.source_url,
      active: graph.selectedEdgeId === e.id,
    }))
  return [...nodes, ...edges]
})
function select(row: Row) { row.kind === 'node' ? graph.select(row.id) : graph.selectEdge(row.id) }
function inspect(row: Row) { select(row); emit('inspect') }
</script>

<style scoped>
.finding-list { padding: 12px; overflow: auto; height: 100%; font-size: 13px; }
.list-intro { display: grid; margin-bottom: 10px; }
.list-intro span,.list-empty { opacity: .65; }
ul { list-style: none; padding: 0; margin: 0; }
li { border-bottom: 1px solid rgba(128,128,128,.18); padding: 5px 0; }
li.active { border-left: 3px solid rgb(var(--v-theme-primary)); padding-left: 5px; }
li > button { width: 100%; display: flex; gap: 8px; align-items: flex-start; padding: 5px; text-align: left; border: 0; background: none; color: inherit; cursor: pointer; }
li > button span { display: grid; min-width: 0; }
li > button small { opacity: .65; overflow-wrap: anywhere; }
.actions { display: flex; padding-left: 25px; }
</style>