<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2">
      <h2 class="text-h6">Entities</h2>
      <v-text-field v-model="q" placeholder="filter by name" hide-details style="max-width: 280px" prepend-inner-icon="mdi-magnify" clearable />
      <v-select v-model="kind" :items="['', 'organization', 'program', 'agency']" label="kind" hide-details style="max-width: 160px" />
      <v-checkbox v-model="flagged" label="flagged only" hide-details density="compact" />
      <v-select v-model="band" :items="bandItems" label="risk band" hide-details style="max-width: 150px" />
      <v-spacer /><span class="text-caption">{{ total }} entities</span>
    </div>
    <RiskUnscoredHint :items="items" @scored="load" />
    <v-data-table class="entities-table" :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading" hover @click:row="(_: any, r: any) => router.push(`/entities/${r.item.id}`)">
      <template #item.risk_score="{ item }">
        <v-chip size="x-small" variant="tonal" :color="bandChip(item.risk_band)"
                :title="`${bandLabel(item.risk_band)} · ${confidenceNote(item.risk_confidence, item.risk_dimensions_scored, item.risk_dimensions_requested)}`">
          {{ item.risk_score ?? '—' }}<span v-if="isThin(item.risk_confidence)">?</span>
        </v-chip>
      </template>
      <template #item.name="{ item }"><span>{{ item.name }}</span><v-chip v-if="item.flagged" size="x-small" color="error" class="ml-1" variant="tonal">flagged</v-chip></template>
      <template #item.parent_seat="{ item }"><span :class="{ 'text-error': item.parent_seat && !item.parent_seat.startsWith('US') }">{{ item.parent_seat || '—' }}</span></template>
      <template #item.sole_source="{ item }"><v-icon v-if="item.sole_source" icon="mdi-alert-circle-outline" color="warning" size="16" /></template>
      <!-- The row opens the page; this opens the node on the canvas instead. -->
      <template #item.view="{ item }"><v-btn icon="mdi-graph" size="x-small" variant="text" title="Open on the canvas" @click.stop="openOnCanvas(item.id, 'Entity')" /></template>
    </v-data-table>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, qs } from '../api/client'
import RiskUnscoredHint from '../components/RiskUnscoredHint.vue'
import { bandChip, bandLabel, confidenceNote, isThin, RISK_BANDS } from '../styles/risk'
import { useOpenOnCanvas } from '../composables/openOnCanvas'
const router = useRouter(); const { openOnCanvas } = useOpenOnCanvas()
const q = ref(''); const kind = ref(''); const flagged = ref(false); const band = ref('')
const items = ref<any[]>([]); const total = ref(0); const loading = ref(false)
const bandItems = [{ title: 'any', value: '' }, ...RISK_BANDS.map(b => ({ title: b.label, value: b.band }))]
const headers = [
  { title: 'Risk', key: 'risk_score', width: 80 },
  { title: 'Name', key: 'name' }, { title: 'Tier', key: 'tier', width: 70 }, { title: 'UEI', key: 'uei' }, { title: 'LEI', key: 'lei' }, { title: 'Inc.', key: 'incorporated', width: 80 },
  { title: 'Parent seat', key: 'parent_seat', width: 100 }, { title: 'Ultimate parent', key: 'parent' }, { title: 'Sole', key: 'sole_source', width: 60 }, { title: 'Source', key: 'source', width: 110 },
  { title: '', key: 'view', width: 44, sortable: false },
]
// Filtering by band is asking "show me the worst", so that view is ordered by score;
// otherwise the list keeps its tier order, which is what it is for.
async function load() {
  loading.value = true
  try {
    const r = await api.get(`/api/entities?${qs({ q: q.value, kind: kind.value, flagged: flagged.value ? true : undefined, band: band.value || undefined, sort: band.value ? 'risk' : undefined, limit: 500 })}`)
    items.value = r.items; total.value = r.total
  } finally { loading.value = false }
}
let t: any; watch([q, kind, flagged, band], () => { clearTimeout(t); t = setTimeout(load, 250) })
onMounted(load)
</script>
