<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2">
      <h2 class="text-h6">Claims</h2>
      <v-btn-toggle v-model="status" class="status-toggle" mandatory density="compact" variant="outlined"><v-btn value="staged">Staged</v-btn><v-btn value="committed">Committed</v-btn><v-btn value="rejected">Rejected</v-btn></v-btn-toggle>
      <v-spacer /><span class="text-caption">{{ items.length }} · authoritative connectors auto-commit; open-web facts wait here for a human or a second source</span>
    </div>
    <v-data-table class="claims-table" :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading">
      <template #item.assertion="{ item }">
        <span>{{ item.subject }}</span> <b class="mono">{{ item.claim.predicate }}</b> <span>{{ item.object || item.claim.object_value }}</span>
        <div class="text-caption" style="opacity:.7">{{ item.claim.detail }}</div>
      </template>
      <template #item.status="{ item }"><TruthBadge :value="item.claim.simulated ? 'simulated' : item.claim.status" /><div v-if="item.claim.simulated" class="simulation-note">Training scenario; not an allegation</div></template>
      <template #item.source="{ item }"><b>{{ item.claim.source || 'Unavailable' }}</b><div class="text-caption">Method {{ item.claim.method || 'Unavailable' }}<span v-if="item.claim.model"> · {{ item.claim.model }}</span></div><div class="text-caption">Confidence {{ confidence(item.claim.confidence) }} · {{ item.claim.trust || 'trust unknown' }}</div></template>
      <template #item.artifacts="{ item }"><span v-for="a in item.artifacts" :key="a.id" class="mr-2 text-no-wrap"><TruthBadge v-if="a.simulated" value="simulated" /><SourceLink :href="a.url" :artifact-id="a.id">{{ a.kind }}</SourceLink><v-btn icon="mdi-text-box-search-outline" size="x-small" variant="text" density="compact" title="View contents" @click="rawId = a.id" /></span><span v-if="!item.artifacts.length" class="text-caption">Missing</span></template>
      <template #item.when="{ item }">{{ date(item.claim.latest_retrieved_at || item.claim.retrieved_at) }}</template>
      <template #item.actions="{ item }">
        <template v-if="item.claim.status === 'staged'">
          <v-btn size="x-small" color="success" @click="act(item.claim.id, 'commit')">Commit</v-btn>
          <v-btn size="x-small" color="error" variant="text" @click="act(item.claim.id, 'reject')">Reject</v-btn>
        </template>
        <span v-else class="text-caption">{{ item.claim.decision_note }}</span>
      </template>
    </v-data-table>
    <ArtifactViewer :artifact-id="rawId" @close="rawId = null" />
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import ArtifactViewer from '../components/ArtifactViewer.vue'
import SourceLink from '../components/SourceLink.vue'
import TruthBadge from '../components/TruthBadge.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const requestedStatus = String(route.query.status || '')
const status = ref(['staged', 'committed', 'rejected'].includes(requestedStatus) ? requestedStatus : 'staged'); const items = ref<any[]>([]); const loading = ref(false); const rawId = ref<string | null>(null)
const claimId = String(route.query.claim_id || '')
const headers = [{ title: 'Assertion', key: 'assertion', width: 360 }, { title: 'Truth status', key: 'status', width: 120 }, { title: 'Source lineage', key: 'source', width: 220 }, { title: 'Evidence', key: 'artifacts', width: 140 }, { title: 'Retrieved', key: 'when', width: 140 }, { title: '', key: 'actions', width: 170 }]
async function load() { loading.value = true; try { const entity = String(route.query.entity_id || ''); items.value = await api.get(`/api/claims?status=${status.value}${entity ? `&entity_id=${encodeURIComponent(entity)}` : ''}${claimId ? `&claim_id=${encodeURIComponent(claimId)}` : ''}&limit=500`) } finally { loading.value = false } }
async function act(id: string, what: 'commit' | 'reject') { await api.post(`/api/claims/${id}/${what}`, {}); load() }
function confidence(value: unknown) { const n = Number(value); return Number.isFinite(n) ? `${Math.round(n * 100)}%` : 'Unavailable' }
function date(value: unknown) { return value ? new Date(String(value)).toLocaleString() : 'Unavailable' }
watch(status, load); onMounted(load)
</script>
<style scoped>
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.simulation-note { max-width: 130px; margin-top: 3px; color: #8a5213; font-size: 10px; font-weight: 700; }
.claims-table :deep(table) { min-width: 1150px; }
.claims-table :deep(th:first-child), .claims-table :deep(td:first-child) { min-width: 360px; }
@media (max-width: 500px) {
  .status-toggle { display: flex; width: 100%; }
  .status-toggle :deep(.v-btn) { flex: 1 1 0; min-width: 0; padding-inline: 6px; font-size: 11px; }
}
</style>
