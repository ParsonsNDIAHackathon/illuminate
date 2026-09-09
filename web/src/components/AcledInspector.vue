<template>
  <section v-if="acled.selected" class="pa-4 acled-inspector" aria-label="ACLED inspector">
    <div class="text-overline">ACLED · Aggregated activity</div>
    <h2 class="text-h6">{{ acled.selected.name }}, {{ acled.selected.country }}</h2>
    <p class="my-3">{{ acled.selected.events.toLocaleString() }} events · {{ acled.selected.fatalities.toLocaleString() }} reported fatalities</p>
    <p class="text-caption">Weekly reporting dates after {{ acled.data?.windows[acled.period]?.after }} through {{ acled.data?.through }}. This is a stored snapshot, not live coverage.</p>
    <v-divider class="my-3" />
    <p v-for="row in acled.selected.breakdown" :key="row.type" class="mb-2 text-body-2">
      <strong>{{ row.type }}</strong><br>{{ row.events.toLocaleString() }} events · {{ row.fatalities.toLocaleString() }} reported fatalities
    </p>
    <v-divider class="my-3" />
    <p v-if="acled.selected.latitude !== null" class="text-caption">State/province centroid: {{ acled.selected.latitude }}, {{ acled.selected.longitude }}. The marker represents an area, not an incident location.</p>
    <p v-else class="text-caption">No valid area centroid supplied. This activity is included in totals but cannot be placed on the map.</p>
    <p v-for="source in acled.selected.sources" :key="source" class="text-caption mt-3">Workbook: {{ acled.data?.sources[source]?.filename }}</p>
    <v-btn class="mt-3" href="https://acleddata.com/conflict-data/download-data-files" target="_blank" rel="noopener" variant="tonal" size="small" append-icon="mdi-open-in-new">ACLED source</v-btn>
  </section>
</template>
<script setup lang="ts">
import { useAcled } from '../stores/acled'
const acled = useAcled()
</script>
<style scoped>
.acled-inspector { overflow-wrap:anywhere; }
</style>
