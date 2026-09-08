<template>
  <v-chip-group multiple :model-value="active" @update:model-value="onChange" filter variant="tonal" class="layers">
    <v-chip value="entities" size="small" disabled>Entities</v-chip>
    <v-chip :value="INDIRECT_ORGS" size="small" title="Organizations no supply, ownership or affiliation chain joins to a program — only a person, place, document or claim does. Turn off to keep them off the canvas.">Indirect orgs</v-chip>
    <v-chip value="people" size="small">People</v-chip>
    <v-chip value="countries" size="small">Countries</v-chip>
    <v-chip value="categories" size="small" title="Goods / services taxonomy nodes">Categories</v-chip>
    <v-chip value="artifacts" size="small" title="Documents: filings, awards, news, web pages">Artifacts</v-chip>
    <v-chip value="sources" size="small" title="Where data came from: registry entries and source records (LittleSis, GLEIF, SAM.gov, OFAC…)">Sources</v-chip>
    <v-chip value="claims" size="small" title="Reified assertions the evidence supports">Claims</v-chip>
  </v-chip-group>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspace } from '../stores/workspace'
import { INDIRECT_ORGS } from '../stores/graphLayers'
const ws = useWorkspace()
// Layers the server fetches by; a change here means a reload.
const FETCHED = ['people', 'countries', 'categories', 'artifacts', 'sources', 'claims']
// Indirect orgs is a canvas-side filter over entities the server always sends, so it redraws without a fetch.
const TOGGLABLE = [...FETCHED, INDIRECT_ORGS]
const active = computed(() => Object.entries(ws.ws.layers).filter(([, v]) => v).map(([k]) => k))
const emit = defineEmits<{ (e: 'change'): void }>()
function onChange(vals: string[]) {
  let fetched = false
  for (const k of TOGGLABLE) {
    const v = vals.includes(k)
    if (v === !!ws.ws.layers[k]) continue
    ws.setLayer(k, v)
    if (FETCHED.includes(k)) fetched = true
  }
  if (fetched) emit('change')
}
</script>
<style scoped>.layers { flex: 0 0 auto; }</style>
