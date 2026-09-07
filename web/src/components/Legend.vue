<template>
  <div v-if="graph.legend.length" class="legend">
    <v-chip v-for="l in graph.legend" :key="l.swatch + l.label" variant="tonal" size="small">
      <span class="swatch" :style="{ background: resolveSwatch(l.swatch, ws.theme) }"></span>
      {{ l.label }} · {{ l.count }}
    </v-chip>
    <span class="hint">legend generated from style_ops</span>
  </div>
</template>
<script setup lang="ts">
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { resolveSwatch } from '../styles/palette'
const graph = useGraph(); const ws = useWorkspace()
</script>
<style scoped>
.legend { position: absolute; left: 12px; bottom: 12px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.hint { font-size: 11px; opacity: .6; margin-left: 4px; }
</style>
