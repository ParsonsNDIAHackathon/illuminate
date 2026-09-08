<template>
  <div class="legend" :class="{ minimized }">
    <div class="legend-heading">
      <strong>Legend</strong>
      <v-btn class="toggle" :icon="minimized ? 'mdi-chevron-up' : 'mdi-minus'" variant="text" size="x-small"
             :title="minimized ? 'Show legend' : 'Minimize legend'" @click="minimized = !minimized" />
    </div>
    <template v-if="!minimized">
      <!-- Types on the canvas: a quiet key for the muted fills. Only what is currently drawn. -->
      <div v-if="types.length > 1" class="types">
        <span v-for="t in types" :key="t.key" class="type" :title="t.label"><span class="dot" :class="t.shape" :style="{ background: t.fill }"></span>{{ t.label }}</span>
      </div>
      <div v-if="graph.legend.length" class="ops">
        <v-chip v-for="l in graph.legend" :key="l.swatch + l.label" variant="tonal" size="small">
          <span class="swatch" :style="{ background: resolveSwatch(l.swatch, ws.theme) }"></span>
          {{ l.label }} · {{ l.count }}
        </v-chip>
        <span class="hint">legend generated from style_ops</span>
      </div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { resolveSwatch } from '../styles/palette'
import { NODE_TYPES, nodeType, type NodeType } from '../styles/nodeTypes'
const graph = useGraph(); const ws = useWorkspace()
// The legend is a reference, not a fixture: once it has been read it can be folded away,
// and it stays folded across reloads.
const STORAGE_KEY = 'illuminate.legend.minimized'
const minimized = ref(localStorage.getItem(STORAGE_KEY) === '1')
watch(minimized, v => localStorage.setItem(STORAGE_KEY, v ? '1' : '0'))
const types = computed(() => {
  const present = new Set(graph.nodeList.map(nodeType))
  return (Object.keys(NODE_TYPES) as NodeType[]).filter(k => present.has(k)).map(k => ({ key: k, label: NODE_TYPES[k].label, shape: NODE_TYPES[k].shape, fill: NODE_TYPES[k].fill[ws.theme] }))
})
</script>
<style scoped>
.legend { position: absolute; left: 12px; bottom: 12px; display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.legend-heading { display: flex; align-items: center; gap: 6px; font-size: 11px; opacity: .8; padding: 0 4px; }
.legend-heading strong { font-size: 11px; letter-spacing: .035em; text-transform: uppercase; }
.legend-heading .toggle { margin: -4px -6px -4px 0; opacity: .65; }
.legend-heading .toggle:hover { opacity: 1; }
.ops { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.hint { font-size: 11px; opacity: .6; margin-left: 4px; }
.types { display: flex; gap: 10px; flex-wrap: wrap; font-size: 11px; opacity: .8; pointer-events: none; padding: 3px 8px; border-radius: 6px; background: rgba(var(--v-theme-surface), .82); backdrop-filter: blur(2px); }
.type { display: inline-flex; align-items: center; gap: 4px; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
.dot.round-rectangle, .dot.rectangle, .dot.barrel { border-radius: 2px; }
.dot.diamond { transform: rotate(45deg) scale(.85); border-radius: 1px; }
.dot.hexagon { clip-path: polygon(25% 5%, 75% 5%, 100% 50%, 75% 95%, 25% 95%, 0 50%); }
.dot.round-triangle { clip-path: polygon(50% 0, 100% 100%, 0 100%); }
.dot.tag { clip-path: polygon(0 0, 70% 0, 100% 50%, 70% 100%, 0 100%); }
</style>
