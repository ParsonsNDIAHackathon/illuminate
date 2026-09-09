<template>
  <section v-if="lanes.enabled" class="lanes-panel" aria-label="Established shipping lanes">
    <div class="heading"><strong>Established shipping lanes</strong><span>{{ lanes.lanes.length }} connections · {{ lanes.ports.length }} ports</span>
      <v-btn size="x-small" variant="text" :loading="lanes.loading" @click="lanes.load()">Refresh</v-btn></div>
    <p>Selected Los Angeles service connections · August 2026 publication. Teal lines are schematic port connections, not vessel tracks or supplier shipments. Coverage is partial and independent of the graph.</p>
    <v-alert v-if="lanes.error" type="warning" density="compact">{{ lanes.error }} <span v-if="lanes.loaded">Previously loaded reference data remains visible.</span></v-alert>
    <div class="controls">
      <v-text-field v-model="lanes.query" label="Search lanes or services" clearable density="compact" hide-details />
      <v-select v-model="lanes.port" :items="portOptions" label="Port" density="compact" hide-details />
      <v-select v-model="lanes.selectedId" :items="laneOptions" label="Inspect lane" density="compact" hide-details />
    </div>
    <p v-if="!lanes.loading && !lanes.lanes.length" role="status">{{ lanes.error ? 'Lane data is unavailable.' : 'No lanes match these filters.' }}</p>
    <v-dialog :model-value="!!lanes.selected" max-width="600" @update:model-value="!$event && (lanes.selectedId = '')">
      <v-card v-if="lanes.selected" :title="lanes.selected.name">
        <v-card-text>
          <p>Published service: {{ lanes.selected.service }}</p>
          <p>Source publication: {{ lanes.selected.published_at }}</p>
          <p class="my-3">This connection appears in the published port rotation. The path and port positions are approximate; the complete service may call at additional ports. It does not establish cargo ownership, traffic volume, frequency, or current availability.</p>
          <a :href="safeSourceLink(lanes.selected.source.reference)" target="_blank" rel="noopener noreferrer">{{ lanes.selected.source.title }} ↗</a>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn @click="lanes.selectedId = ''">Close</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useShippingLanes } from '../stores/shippingLanes'
import { safeSourceLink } from '../shippingMap'
const lanes = useShippingLanes()
const portOptions = computed(() => [{ title: 'All ports', value: '' }, ...lanes.catalog.ports.map(p => ({ title: p.name, value: p.id }))])
const laneOptions = computed(() => [{ title: 'Select a lane', value: '' }, ...lanes.lanes.map(l => ({ title: l.name, value: l.id }))])
onMounted(() => { if (!lanes.loaded) lanes.load() })
</script>
<style scoped>
.lanes-panel { flex-shrink:0; padding:10px 0; border-bottom:1px solid rgba(128,128,128,.25); }
.heading,.controls { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
.heading span,p { font-size:12px; } p { margin:6px 0; opacity:.8; }
.controls > * { min-width:160px; flex:1; }
</style>
