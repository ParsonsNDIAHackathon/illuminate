<template>
  <v-chip-group multiple :model-value="active" @update:model-value="onChange" filter variant="tonal" class="layers">
    <v-chip value="entities" size="small" disabled>Entities</v-chip>
    <v-chip value="people" size="small">People</v-chip>
    <v-chip value="countries" size="small">Countries</v-chip>
    <v-chip value="artifacts" size="small">Artifacts</v-chip>
  </v-chip-group>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspace } from '../stores/workspace'
const ws = useWorkspace()
const active = computed(() => Object.entries(ws.ws.layers).filter(([, v]) => v).map(([k]) => k))
const emit = defineEmits<{ (e: 'change'): void }>()
function onChange(vals: string[]) {
  for (const k of ['people', 'countries', 'artifacts']) { const v = vals.includes(k); if (v !== !!ws.ws.layers[k]) ws.setLayer(k, v) }
  emit('change')
}
</script>
<style scoped>.layers { position: absolute; top: 8px; left: 12px; }</style>
