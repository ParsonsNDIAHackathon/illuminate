<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2">
      <h2 class="text-h6">Risk</h2>
      <v-select v-model="band" :items="bandItems" label="band" hide-details style="max-width: 170px" />
      <v-select v-model="label" :items="[{ title: 'everything', value: '' }, { title: 'organisations', value: 'entity' }, { title: 'people', value: 'person' }]"
                label="kind" hide-details style="max-width: 170px" />
      <v-spacer />
      <span class="text-caption mr-2" v-if="bands">
        <span v-for="b in bandOrder" :key="b" class="ml-2">{{ b }} {{ bands[b] || 0 }}</span>
        <span class="ml-2" style="opacity:.7">unscored {{ bands.unscored || 0 }}</span>
      </span>
      <v-btn size="small" prepend-icon="mdi-refresh" :loading="rescoring" @click="rescore">Rescore graph</v-btn>
    </div>

    <v-data-table :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading" hover
                  @click:row="(_: any, r: any) => open(r.item)">
      <template #item.score="{ item }">
        <v-chip size="x-small" variant="tonal" :color="bandChip(item.band)">{{ item.score ?? '—' }}</v-chip>
      </template>
      <template #item.name="{ item }">
        {{ item.name }}
        <v-chip v-if="item.flagged" size="x-small" color="error" variant="tonal" class="ml-1">flagged</v-chip>
        <v-chip v-if="item.simulated" size="x-small" color="warning" variant="tonal" class="ml-1">SIM</v-chip>
      </template>
      <template #item.confidence="{ item }">
        <!-- The number is meaningless without this. A 100 on two of seven dimensions and a
             100 on six are different findings and the table has to say which is which. -->
        <span :class="{ 'text-warning': isThin(item.confidence) }">
          {{ item.confidence == null ? '—' : `${item.confidence}%` }}
          <span class="text-caption" style="opacity:.6" v-if="item.dimensions_scored != null">
            {{ item.dimensions_scored }}/{{ item.dimensions_requested }}
          </span>
        </span>
      </template>
      <template #item.top_factor="{ item }"><span style="opacity:.85">{{ item.top_factor || '—' }}</span></template>
      <template #item.view="{ item }"><v-btn icon="mdi-graph" size="x-small" variant="text" title="Open on the canvas" @click.stop="openOnCanvas(item.id, item.label)" /></template>
    </v-data-table>

    <v-alert variant="tonal" density="compact" type="info" class="mt-3">
      A score is the weighted mean of the dimensions that returned data. Dimensions that returned
      nothing are left out rather than counted as clear, so a high score on thin coverage means
      “everything we know is bad”, not “everything is bad” — enrich the node to settle it.
      Proximity is walked up to {{ maxHops }} hops over ownership, personnel and commercial edges.
    </v-alert>
    <p class="text-caption mt-2" style="opacity:.7">{{ reference }}</p>
  </v-container>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, qs } from '../api/client'
import { bandChip, isThin, RISK_BANDS } from '../styles/risk'
import { useOpenOnCanvas } from '../composables/openOnCanvas'

const router = useRouter()
const items = ref<any[]>([]); const bands = ref<Record<string, number> | null>(null)
const loading = ref(false); const rescoring = ref(false)
const band = ref(''); const label = ref('')
const maxHops = ref(3); const reference = ref('')
const bandOrder = RISK_BANDS.map(b => b.band)
const bandItems = [{ title: 'all bands', value: '' }, ...RISK_BANDS.map(b => ({ title: b.label, value: b.band }))]
const headers = [
  { title: 'Score', key: 'score', width: 90 },
  { title: 'Band', key: 'band', width: 100 },
  { title: 'Name', key: 'name' },
  { title: 'Kind', key: 'kind', width: 110 },
  { title: 'Coverage', key: 'confidence', width: 130 },
  { title: 'Leading factor', key: 'top_factor' },
  { title: '', key: 'view', width: 44, sortable: false },
]

async function load() {
  loading.value = true
  try {
    const r = await api.get(`/api/risk?${qs({ band: band.value || undefined, label: label.value || undefined, limit: 500 })}`)
    items.value = r.items; bands.value = r.bands; maxHops.value = r.max_hops; reference.value = r.reference
  } finally { loading.value = false }
}
async function rescore() {
  rescoring.value = true
  try { await api.post('/api/risk/rescore', {}); await load() } finally { rescoring.value = false }
}
// Each kind of party has a page of its own; the row opens it.
const { openOnCanvas } = useOpenOnCanvas()
function open(row: any) { router.push(row.label === 'Person' ? `/people/${row.id}` : `/entities/${row.id}`) }
watch([band, label], load)
onMounted(load)
</script>
