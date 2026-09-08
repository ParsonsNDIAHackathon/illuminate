<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2"><h2 class="text-h6">Artifacts</h2><v-select v-model="kind" :items="['', 'award', 'registry', 'filing', 'news', 'web', 'record', 'document']" label="kind" hide-details style="max-width: 160px" /><v-spacer /><span class="text-caption">{{ items.length }} evidence artifacts</span></div>
    <v-data-table class="artifacts-table" :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading">
      <template #item.title="{ item }"><SourceLink :href="item.url" :artifact-id="item.id">{{ item.title }}</SourceLink><div v-if="item.simulated" class="simulation-note">Training scenario only — not a real allegation</div></template>
      <template #item.about="{ item }"><router-link v-for="a in item.about" :key="a.id" :to="`/entities/${a.id}`" class="mr-2">{{ a.name }}</router-link></template>
      <template #item.amount="{ item }">{{ item.amount ? '$' + Number(item.amount).toLocaleString() : '' }}</template>
      <template #item.raw="{ item }"><v-btn icon="mdi-text-box-search-outline" size="x-small" variant="text" title="View contents" @click="rawId = item.id" /></template>
      <template #item.status="{ item }"><TruthBadge :value="artifactStatus(item)" /></template>
      <template #item.retrieved="{ item }">{{ item.retrieved_at ? new Date(item.retrieved_at).toLocaleString() : 'Unavailable' }}</template>
    </v-data-table>
    <ArtifactViewer :artifact-id="rawId" @close="rawId = null" />
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, qs } from '../api/client'
import ArtifactViewer from '../components/ArtifactViewer.vue'
import SourceLink from '../components/SourceLink.vue'
import TruthBadge from '../components/TruthBadge.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const kind = ref(''); const items = ref<any[]>([]); const loading = ref(false); const rawId = ref<string | null>(null)
const headers = [{ title: 'Kind', key: 'kind', width: 90 }, { title: 'Title', key: 'title', width: 320 }, { title: 'Truth status', key: 'status', width: 110 }, { title: 'About', key: 'about', width: 220 }, { title: 'Source', key: 'source', width: 110 }, { title: 'Published', key: 'published_at', width: 110 }, { title: 'Retrieved', key: 'retrieved', width: 150 }, { title: 'Amount', key: 'amount', width: 130 }, { title: 'Claims', key: 'claims', width: 80 }, { title: 'View', key: 'raw', width: 60, sortable: false }]
async function load() { loading.value = true; try { items.value = await api.get(`/api/artifacts?${qs({ kind: kind.value, entity_id: String(route.query.entity_id || ''), limit: 500 })}`) } finally { loading.value = false } }
function artifactStatus(item: any) {
  if (item.simulated) return 'simulated'
  if (item.claim_statuses?.includes('committed')) return 'verified'
  if (item.claim_statuses?.includes('staged')) return 'staged'
  if (item.claim_statuses?.includes('rejected')) return 'rejected'
  return 'unavailable'
}
watch(kind, load); onMounted(load)
</script>
<style scoped>
.simulation-note { color: #8a5213; font-size: 10px; font-weight: 700; }
.artifacts-table :deep(table) { min-width: 1380px; }
.artifacts-table :deep(th:nth-child(2)), .artifacts-table :deep(td:nth-child(2)) { min-width: 320px; }
.artifacts-table :deep(th:nth-child(4)), .artifacts-table :deep(td:nth-child(4)) { min-width: 220px; }
</style>
