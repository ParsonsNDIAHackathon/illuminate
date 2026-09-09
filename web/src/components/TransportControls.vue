<template>
  <section class="transport-controls" aria-label="US transport reference">
    <div class="network-row">
      <v-checkbox v-model="transport.highways" label="US highways" density="compact" hide-details />
      <v-checkbox v-model="transport.rail" label="US rail" density="compact" hide-details />
      <v-btn size="small" variant="tonal" prepend-icon="mdi-map-marker-radius" @click="emit('focus-us')">US</v-btn>
      <v-text-field v-model="transport.query" label="Find corridor or city" density="compact" variant="outlined" hide-details clearable @click:clear="transport.query = ''" />
      <v-select :model-value="transport.selectedId" :items="options" label="Inspect US corridor" density="compact" variant="outlined" hide-details @update:model-value="transport.selectedId = $event" />
    </div>
    <p class="network-note">US reference: {{ transport.visible.length }} corridors. Blue: Interstates · Orange: rail. Generalized paths; local roads and final-mile access omitted. Independent of supplier scope and evidence filters.</p>
    <v-alert v-if="transport.error" type="warning" density="compact" variant="tonal">{{ transport.error }} <v-btn size="x-small" @click="transport.load()">Retry</v-btn></v-alert>
    <v-progress-linear v-if="transport.loading" indeterminate aria-label="Loading US transport reference" />
    <v-dialog :model-value="!!transport.selected" max-width="640" @update:model-value="!$event && (transport.selectedId = '')">
      <v-card v-if="transport.selected">
        <v-card-title>{{ transport.selected.name }}</v-card-title>
        <v-card-text>
          <v-chip size="small">{{ transport.selected.mode === 'truck' ? 'Major Interstate' : 'Freight rail' }} · Reference geography</v-chip>
          <p class="mt-4">{{ transport.selected.stops.join(' → ') }}</p>
          <p class="mt-4">{{ transport.selected.notes }}</p>
          <p class="mt-4"><a :href="safeSourceLink(transport.selected.source.reference)" target="_blank" rel="noopener noreferrer">{{ transport.selected.source.title }} ↗</a></p>
          <p class="text-caption mt-2">Catalog reviewed {{ transport.selected.updated_at }}. Schematic city-to-city geometry; not a live service or closure feed.</p>
          <v-alert variant="tonal" density="compact" class="mt-4">A corridor on this map does not establish use by any supplier. Supplier journeys are separately labeled and sourced under Shipping routes.</v-alert>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn @click="transport.selectedId = ''">Close corridor</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useTransport } from '../stores/transport'
import { safeSourceLink } from '../shippingMap'
const transport = useTransport()
const emit = defineEmits<{ 'focus-us': [] }>()
const options = computed(() => [{ title: 'Select corridor', value: '' }, ...transport.visible.map(c => ({ title: c.name, value: c.id }))])
watch(() => transport.visible, rows => { if (!rows.some(c => c.id === transport.selectedId)) transport.selectedId = '' })
onMounted(() => { if (!transport.attempted) transport.load() })
</script>
<style scoped>
.transport-controls { flex-shrink:0; margin-bottom:8px; padding:8px; border:1px solid #81bac844; border-radius:8px; }.network-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }.network-row :deep(.v-checkbox) { flex:0 0 auto; }.network-row :deep(.v-text-field) { flex:1 1 170px; min-width:150px; }.network-note { font-size:10px; opacity:.75; line-height:1.5; margin-top:6px; }
</style>
