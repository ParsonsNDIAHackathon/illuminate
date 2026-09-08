<template>
  <div class="legend">
    <div class="legend-heading">
      <strong>Relationship paths</strong>
      <span>Direction follows arrow</span>
    </div>
    <div class="family-grid">
      <span v-for="family in RELATIONSHIP_FAMILIES" :key="family.key" class="family" :title="family.description">
        <i :class="`line-${family.lineStyle}`" :style="{ '--family-color': familyColor(family) }"></i>
        {{ family.label }}
      </span>
    </div>
    <div class="simulation-key" :style="{ '--simulation-color': simulationColor() }"><i></i><b>SIM</b><span>Simulated / scenario data</span></div>
    <div v-if="graph.focusIds.length" class="focus-legend">
      <span class="path-line"></span><strong>Critical path</strong>
      <span class="risk-ring"></span><span>{{ graph.focusIds.length }} report element{{ graph.focusIds.length === 1 ? '' : 's' }}</span>
      <button type="button" @click="graph.clearFocus()">Show full context</button>
    </div>
    <div v-if="graph.legend.length" class="style-legend">
      <v-chip v-for="l in graph.legend" :key="l.swatch + l.label" variant="tonal" size="x-small">
        <span class="swatch" :style="{ background: resolveSwatch(l.swatch, ws.theme) }"></span>
        {{ l.label }} · {{ l.count }}
      </v-chip>
    </div>
  </div>
</template>
<script setup lang="ts">
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { resolveSwatch } from '../styles/palette'
import { RELATIONSHIP_FAMILIES, type RelationshipFamily } from '../styles/relationshipFamilies'
const graph = useGraph(); const ws = useWorkspace()
function familyColor(family: RelationshipFamily) { return ws.theme === 'dark' ? family.darkColor : family.color }
function simulationColor() { return ws.theme === 'dark' ? '#f6c453' : '#b77900' }
</script>
<style scoped>
.legend { position: absolute; left: 12px; bottom: 12px; z-index: 4; width: min(430px, calc(100% - 72px)); display: grid; gap: 7px; padding: 10px 12px; border: 1px solid rgba(100,116,139,.32); border-radius: 6px; background: rgba(var(--v-theme-surface),.94); box-shadow: 0 3px 14px rgba(15,23,42,.13); font-size: 11px; backdrop-filter: blur(5px); }
.legend-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.legend-heading strong { font-size: 12px; letter-spacing: .035em; text-transform: uppercase; }
.legend-heading span { opacity: .6; }
.family-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px 14px; }
.family { display: flex; align-items: center; gap: 7px; white-space: nowrap; }
.family i { width: 25px; flex: none; border-top: 3px solid var(--family-color); }
.family .line-dashed { border-top-style: dashed; }
.family .line-dotted { border-top-style: dotted; }
.simulation-key { display: flex; align-items: center; gap: 7px; color: var(--simulation-color); font-weight: 700; }
.simulation-key i { width: 25px; border-top: 4px dotted var(--simulation-color); }
.simulation-key b { padding: 0 3px; border: 1px dashed var(--simulation-color); font-size: 9px; line-height: 14px; }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.focus-legend { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; padding-top: 7px; border-top: 1px solid rgba(0,107,98,.25); color: rgb(var(--v-theme-on-surface)); font-size: 12px; }
.path-line { width: 25px; height: 4px; background: #006b62; }
.risk-ring { width: 13px; height: 13px; border: 3px solid #a93622; border-radius: 50%; }
button { margin-left: auto; color: #087f72; font: inherit; font-weight: 700; border: 0; border-left: 1px solid rgba(0,107,98,.25); padding-left: 9px; background: none; cursor: pointer; }
.style-legend { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; padding-top: 6px; border-top: 1px solid rgba(100,116,139,.2); }
@media (max-width: 520px) { .family-grid { grid-template-columns: 1fr; } }
</style>
