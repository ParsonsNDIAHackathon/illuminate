<template>
  <section v-if="acled.visible" class="acled-details" aria-label="ACLED area details">
    <div class="text-caption">
      <strong>ACLED · {{ total.toLocaleString() }} events · {{ places.length }} areas in view</strong>
      · Purple squares show state/province centroids, not incident locations.
      <template v-if="acled.data">Weekly aggregates after {{ acled.data.windows[acled.period]?.after }} through {{ acled.data.through }} (latest common coverage). Downloaded {{ acled.data.snapshot }}.</template>
      <a href="https://acleddata.com/conflict-data/download-data-files" target="_blank" rel="noopener">Source: ACLED</a>
    </div>
    <v-progress-linear v-if="acled.loading" indeterminate aria-label="Loading ACLED data" />
    <v-alert v-if="acled.error" type="warning" density="compact">{{ acled.error }} <v-btn size="small" @click="acled.load()">Retry</v-btn></v-alert>
    <div class="acled-results">
      <v-list density="compact" aria-label="ACLED areas" class="acled-list">
        <v-list-item v-for="place in places" :key="place.id" :active="acled.selectedId === place.id"
          :title="`${place.name}, ${place.country}`" :subtitle="`${place.latitude === null ? 'Unplaced · ' : ''}${place.events.toLocaleString()} events · ${place.fatalities.toLocaleString()} reported fatalities`"
          @click="acled.selectedId = place.id" />
      </v-list>
      <p v-if="!places.length" class="text-caption pa-2" role="status">{{ acled.loading ? 'Loading areas…' : 'No ACLED activity in this map area. Zoom out or pan to another location.' }}</p>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useAcled } from '../stores/acled'
const acled = useAcled()
const props = defineProps<{ places: ReturnType<typeof import('../acledMap').acledPlaces> }>()
const total = computed(() => props.places.reduce((n, p) => n + p.events, 0))
</script>
<style scoped>
.acled-details { flex:0 0 150px; min-height:0; display:flex; flex-direction:column; padding-top:8px; }
.acled-results { display:flex; min-height:0; flex:1; gap:12px; }
.acled-list { flex:1; min-width:0; overflow:auto; padding:0; }
.acled-list :deep(.v-list-item-title),.acled-list :deep(.v-list-item-subtitle) { font-size:12px; }
a { margin-left:6px; }
</style>
