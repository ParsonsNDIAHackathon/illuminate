<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2">
      <h2 class="text-h6">Claims</h2>
      <v-btn-toggle v-model="status" mandatory density="compact" variant="outlined"><v-btn value="staged">Staged</v-btn><v-btn value="committed">Committed</v-btn><v-btn value="rejected">Rejected</v-btn></v-btn-toggle>
      <v-spacer /><span class="text-caption">{{ items.length }} · authoritative connectors auto-commit; open-web facts wait here for a human or a second source</span>
    </div>
    <v-data-table :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading">
      <template #item.assertion="{ item }">
        <span>{{ item.subject }}</span> <b class="mono">{{ item.claim.predicate }}</b> <span>{{ item.object || item.claim.object_value }}</span>
        <div class="text-caption" style="opacity:.7">{{ item.claim.detail }}</div>
      </template>
      <template #item.source="{ item }">{{ item.claim.source }} <span class="text-caption">· {{ item.claim.method }}<span v-if="item.claim.model"> · {{ item.claim.model }}</span></span><br><span class="text-caption">conf {{ item.claim.confidence }} · {{ item.claim.trust }}</span></template>
      <template #item.artifacts="{ item }"><span v-for="a in item.artifacts" :key="a.id" class="mr-2 text-no-wrap"><a :href="a.url" target="_blank" rel="noopener">{{ a.kind }}</a><v-btn icon="mdi-code-json" size="x-small" variant="text" density="compact" title="View raw payload" @click="rawId = a.id" /></span></template>
      <template #item.actions="{ item }">
        <template v-if="item.claim.status === 'staged'">
          <v-btn size="x-small" color="success" @click="act(item.claim.id, 'commit')">Commit</v-btn>
          <v-btn size="x-small" color="error" variant="text" @click="act(item.claim.id, 'reject')">Reject</v-btn>
        </template>
        <span v-else class="text-caption">{{ item.claim.decision_note }}</span>
      </template>
    </v-data-table>
    <ArtifactRaw :artifact-id="rawId" @close="rawId = null" />
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import ArtifactRaw from '../components/ArtifactRaw.vue'
const status = ref('staged'); const items = ref<any[]>([]); const loading = ref(false); const rawId = ref<string | null>(null)
const headers = [{ title: 'Assertion', key: 'assertion' }, { title: 'Source', key: 'source', width: 200 }, { title: 'Evidence', key: 'artifacts', width: 120 }, { title: 'When', key: 'claim.retrieved_at', width: 120 }, { title: '', key: 'actions', width: 160 }]
async function load() { loading.value = true; try { items.value = await api.get(`/api/claims?status=${status.value}&limit=500`) } finally { loading.value = false } }
async function act(id: string, what: 'commit' | 'reject') { await api.post(`/api/claims/${id}/${what}`, {}); load() }
watch(status, load); onMounted(load)
</script>
<style scoped>.mono { font-family: ui-monospace, monospace; font-size: 12px; }</style>
