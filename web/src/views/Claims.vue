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
          <v-btn size="x-small" color="success" @click="openReview(item.claim.id, 'commit')">Commit</v-btn>
          <v-btn size="x-small" color="error" variant="text" @click="openReview(item.claim.id, 'reject')">Reject</v-btn>
        </template>
        <span v-else class="text-caption">{{ item.claim.decision_note }}</span>
      </template>
    </v-data-table>
    <v-card v-if="entityId && history.length" variant="outlined" class="mt-3">
      <v-card-title class="text-subtitle-1">Accountability history</v-card-title>
      <v-card-subtitle>Claim truth reviews and vendor dispositions are separate append-only events.</v-card-subtitle>
      <v-list density="compact">
        <v-list-item v-for="event in history" :key="event.id">
          <template #prepend><TruthBadge :value="event.simulated ? 'simulated' : event.kind === 'claim_review' ? event.to_status : 'derived'" /></template>
          <v-list-item-title>{{ event.kind === 'claim_review' ? `Claim ${event.claim_id} ${event.to_status}` : `Analyst disposition: ${labelize(event.disposition)}` }}</v-list-item-title>
          <v-list-item-subtitle>{{ event.rationale || 'No rationale recorded' }} · {{ date(event.decided_at) }} · {{ event.actor }}</v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </v-card>
    <ArtifactViewer :artifact-id="rawId" @close="rawId = null" />
    <v-dialog v-model="reviewDialog" max-width="560">
      <v-card>
        <v-card-title>{{ reviewAction === 'commit' ? 'Commit claim' : 'Reject claim' }}</v-card-title>
        <v-card-text>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">This changes claim truth status and records an attributed history event. It does not create a vendor disposition.</v-alert>
          <v-textarea v-model="reviewRationale" label="Review rationale" maxlength="2000" counter rows="4" />
          <v-alert v-if="reviewError" type="error" density="compact">{{ reviewError }}</v-alert>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn @click="reviewDialog = false">Cancel</v-btn><v-btn :color="reviewAction === 'commit' ? 'success' : 'error'" :loading="reviewSaving" :disabled="reviewRationale.trim().length < 3" @click="act">Record review</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, type DecisionHistory } from '../api/client'
import ArtifactViewer from '../components/ArtifactViewer.vue'
import SourceLink from '../components/SourceLink.vue'
import TruthBadge from '../components/TruthBadge.vue'
import { useRoute, useRouter } from 'vue-router'
import { claimScope } from '../navigationState'
const route = useRoute()
const router = useRouter()
const scope = computed(() => claimScope(route.query))
const status = ref(scope.value.status); const items = ref<any[]>([]); const loading = ref(false); const rawId = ref<string | null>(null)
const entityId = computed(() => scope.value.entityId)
const history = ref<DecisionHistory['events']>([])
let loadVersion = 0
const reviewDialog = ref(false); const reviewAction = ref<'commit' | 'reject'>('commit'); const reviewClaimId = ref(''); const reviewRationale = ref(''); const reviewSaving = ref(false); const reviewError = ref('')
const headers = [{ title: 'Assertion', key: 'assertion', width: 360 }, { title: 'Truth status', key: 'status', width: 120 }, { title: 'Source lineage', key: 'source', width: 220 }, { title: 'Evidence', key: 'artifacts', width: 140 }, { title: 'Retrieved', key: 'when', width: 140 }, { title: '', key: 'actions', width: 170 }]
async function load() {
  const version = ++loadVersion
  const { status: requestedStatus, entityId, programId, claimId } = scope.value
  loading.value = true
  try {
    const [nextItems, nextHistory] = await Promise.all([
      api.get<any[]>(`/api/claims?status=${requestedStatus}${entityId ? `&entity_id=${encodeURIComponent(entityId)}` : ''}${claimId ? `&claim_id=${encodeURIComponent(claimId)}` : ''}&limit=500`),
      entityId
        ? api.get<DecisionHistory>(`/api/claims/entities/${encodeURIComponent(entityId)}/history${programId ? `?program_id=${encodeURIComponent(programId)}` : ''}`)
        : Promise.resolve<DecisionHistory>({ current: null, events: [] }),
    ])
    if (version === loadVersion) {
      items.value = claimId ? nextItems.filter(item => item.claim.id === claimId) : nextItems
      history.value = nextHistory.events
    }
  } finally { if (version === loadVersion) loading.value = false }
}
async function applyRoute() {
  status.value = scope.value.status
  await load()
}
function openReview(id: string, action: 'commit' | 'reject') {
  reviewClaimId.value = id; reviewAction.value = action; reviewRationale.value = ''; reviewError.value = ''; reviewDialog.value = true
}
async function act() {
  reviewSaving.value = true; reviewError.value = ''
  try {
    await api.post(`/api/claims/${reviewClaimId.value}/${reviewAction.value}`, { note: reviewRationale.value })
    reviewDialog.value = false
    await load()
  } catch (error: any) { reviewError.value = error.message } finally { reviewSaving.value = false }
}
function confidence(value: unknown) { const n = Number(value); return Number.isFinite(n) ? `${Math.round(n * 100)}%` : 'Unavailable' }
function date(value: unknown) { return value ? new Date(String(value)).toLocaleString() : 'Unavailable' }
function labelize(value: string) { return value.replaceAll('_', ' ') }
watch(status, async next => {
  if (next === scope.value.status) return
  await router.replace({ query: { ...route.query, status: next } })
})
watch(() => route.fullPath, applyRoute)
onMounted(applyRoute)
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
