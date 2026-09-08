<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2">
      <h2 class="text-h6">Entities</h2>
      <v-text-field v-model="q" placeholder="filter by name" hide-details style="max-width: 280px" prepend-inner-icon="mdi-magnify" clearable />
      <v-select v-model="kind" :items="['', 'organization', 'program', 'agency']" label="kind" hide-details style="max-width: 160px" />
      <v-checkbox v-model="flagged" label="flagged only" hide-details density="compact" />
      <v-spacer /><span class="text-caption">{{ total }} entities</span>
    </div>
    <v-data-table class="entities-table" :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading" hover @click:row="(_: any, r: any) => router.push(`/entities/${r.item.id}`)">
      <template #item.name="{ item }"><span>{{ item.name }}</span><v-chip v-if="item.flagged" size="x-small" color="error" class="ml-1" variant="tonal">flagged</v-chip></template>
      <template #item.parent_seat="{ item }"><span :class="{ 'text-error': item.parent_seat && !item.parent_seat.startsWith('US') }">{{ item.parent_seat || '—' }}</span></template>
      <template #item.sole_source="{ item }"><v-icon v-if="item.sole_source" icon="mdi-alert-circle-outline" color="warning" size="16" /></template>
    </v-data-table>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, qs } from '../api/client'
const router = useRouter()
const q = ref(''); const kind = ref(''); const flagged = ref(false); const items = ref<any[]>([]); const total = ref(0); const loading = ref(false)
const headers = [
  { title: 'Name', key: 'name', width: 260 }, { title: 'Tier', key: 'tier', width: 70 }, { title: 'UEI', key: 'uei', width: 130 }, { title: 'LEI', key: 'lei', width: 170 }, { title: 'Inc.', key: 'incorporated', width: 90 },
  { title: 'Parent seat', key: 'parent_seat', width: 110 }, { title: 'Ultimate parent', key: 'parent', width: 180 }, { title: 'Sole', key: 'sole_source', width: 70 }, { title: 'Source', key: 'source', width: 120 },
]
async function load() { loading.value = true; try { const r = await api.get(`/api/entities?${qs({ q: q.value, kind: kind.value, flagged: flagged.value ? true : undefined, limit: 500 })}`); items.value = r.items; total.value = r.total } finally { loading.value = false } }
let t: any; watch([q, kind, flagged], () => { clearTimeout(t); t = setTimeout(load, 250) })
onMounted(load)
</script>
<style scoped>
.entities-table :deep(table) { min-width: 1200px; }
.entities-table :deep(th:first-child), .entities-table :deep(td:first-child) { min-width: 260px; }
</style>
