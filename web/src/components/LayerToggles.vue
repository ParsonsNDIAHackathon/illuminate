<template>
  <v-chip-group multiple :model-value="active" @update:model-value="onChange" filter variant="tonal" class="layers">
    <v-chip value="entities" size="small" disabled>Entities</v-chip>
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
const ws = useWorkspace()
const TOGGLABLE = ['people', 'countries', 'categories', 'artifacts', 'sources', 'claims']
const active = computed(() => Object.entries(ws.ws.layers).filter(([, v]) => v).map(([k]) => k))
const emit = defineEmits<{ (e: 'change'): void }>()
function onChange(vals: string[]) {
  for (const k of TOGGLABLE) { const v = vals.includes(k); if (v !== !!ws.ws.layers[k]) ws.setLayer(k, v) }
  emit('change')
}
</script>
<style scoped>
.layers { flex: 1 1 0; min-width: 0; max-width: 100%; overflow-x: auto; }
</style>
