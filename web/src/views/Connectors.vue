<template>
  <v-container style="max-width: 980px">
    <h2 class="text-h6 mb-1">Settings › Connectors</h2>
    <p class="text-body-2 mb-4" style="opacity:.75">Credentials are encrypted at rest and decrypted only inside the connector process; they never enter a prompt. Without an OpenAI key the app degrades to graph browsing and template queries.</p>
    <v-list lines="two">
      <v-list-item v-for="c in items" :key="c.name" :title="c.label" :subtitle="c.description">
        <template #prepend><v-icon :icon="statusIcon(c)" :color="statusColor(c)" /></template>
        <template #append>
          <div class="d-flex align-center ga-2">
            <v-chip size="x-small" variant="tonal" :color="c.trust === 'authoritative' ? 'primary' : undefined">{{ c.trust }}</v-chip>
            <v-chip size="x-small" :color="statusColor(c)" variant="tonal">{{ statusLabel(c) }}</v-chip>
            <span class="text-caption" style="min-width: 120px; text-align: right">{{ statusDetail(c) }}</span>
            <v-btn v-if="c.key_name" @click="open(c)">{{ c.connected ? 'Replace' : 'Add credential' }}</v-btn>
            <v-btn v-if="c.key_name && c.connected" icon="mdi-delete-outline" variant="text" @click="remove(c)" />
            <v-btn variant="text" @click="check(c)" :loading="checking[c.name]" :disabled="Boolean(c.key_name && !c.connected)">Test</v-btn>
          </div>
        </template>
        <template #subtitle>
          <div>{{ c.description }}</div>
          <div v-if="checkResults[c.name]" class="text-caption mt-1" :class="checkResults[c.name].ok ? 'text-success' : 'text-error'">
            <v-icon size="small" :icon="checkResults[c.name].ok ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'" />
            {{ checkResults[c.name].detail }}
          </div>
        </template>
      </v-list-item>
    </v-list>
    <h3 class="text-subtitle-1 mt-6 mb-2">Approved source coverage</h3>
    <p class="text-body-2 mb-2" style="opacity:.75">Every approved source is listed, including sources that cannot be queried safely for the current workflow.</p>
    <v-list lines="three" density="compact">
      <v-list-item v-for="s in coverage" :key="s.source_id" :title="s.label">
        <template #prepend>
          <v-icon :icon="coverageIcon(s.policy_status)" :color="coverageColor(s.policy_status)" />
        </template>
        <template #subtitle>
          <div>{{ sourceState(s.policy_status) }} · {{ s.limitations }}</div>
          <div class="text-caption">Freshness: {{ s.freshness }} · Access: {{ s.access }}</div>
          <div v-if="s.action" class="text-caption">{{ s.action }}</div>
        </template>
        <template #append>
          <v-chip size="x-small" variant="tonal">{{ s.adapter ? 'query adapter' : 'not queried' }}</v-chip>
        </template>
      </v-list-item>
    </v-list>
    <v-dialog v-model="dlg" max-width="520">
      <v-card v-if="editing">
        <v-card-title>{{ editing.label }} credential</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-2" v-if="editing.key_note">{{ editing.key_note }}</p>
          <p class="text-body-2 mb-3" v-if="editing.key_url">Register: <a :href="editing.key_url" target="_blank" rel="noopener">{{ editing.key_url }}</a></p>
          <v-text-field v-model="value" label="API key" type="password" autofocus hide-details @keydown.enter="save" />
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" @click="dlg = false">Cancel</v-btn><v-btn color="primary" variant="flat" @click="save" :disabled="!value.trim()" :loading="saving">Save & test</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type ConnectorTestResult } from '../api/client'
import { invalidateConnectorResults, isModelBackedConnector, recordConnectorResult } from '../connectors/diagnosticState'
import { useChat } from '../stores/chat'
const items = ref<any[]>([]); const coverage = ref<any[]>([]); const dlg = ref(false); const editing = ref<any>(null); const value = ref(''); const saving = ref(false); const checking = ref<Record<string, boolean>>({}); const checkResults = ref<Record<string, ConnectorTestResult>>({})
async function load() {
  const [connectors, sources] = await Promise.all([api.get<any[]>('/api/connectors'), api.get<any[]>('/api/connectors/coverage')])
  items.value = connectors
  coverage.value = sources
}
function sourceState(status: string) { return status === 'available' ? 'query adapter available' : status.replaceAll('_', ' ') }
function coverageColor(status: string) { return status === 'available' ? 'primary' : (status === 'not_applicable' ? undefined : 'warning') }
function coverageIcon(status: string) {
  if (status === 'available') return 'mdi-check-circle-outline'
  if (status === 'credential_required') return 'mdi-key-alert-outline'
  if (status === 'not_applicable') return 'mdi-minus-circle-outline'
  return 'mdi-alert-circle-outline'
}
function open(c: any) { editing.value = c; value.value = ''; dlg.value = true }
function testState(c: any): boolean | null {
  if (checkResults.value[c.name]) return checkResults.value[c.name].ok
  return c.key_name ? null : Boolean(c.connected)
}
function statusIcon(c: any) {
  const state = testState(c)
  return state === true ? 'mdi-check-circle' : state === false ? 'mdi-alert-circle' : c.connected ? 'mdi-key' : 'mdi-key-alert'
}
function statusColor(c: any) {
  const state = testState(c)
  return state === true ? 'success' : state === false ? 'error' : c.connected ? 'info' : 'warning'
}
function statusLabel(c: any) {
  const state = testState(c)
  return state === true ? 'available' : state === false ? 'failed' : c.connected ? 'unverified' : (c.needs_key ? 'credential required' : 'unavailable')
}
function statusDetail(c: any) {
  return checkResults.value[c.name]?.detail || (c.connected ? (c.key_name ? 'Credential configured; not yet verified' : c.detail) : 'Key needed')
}
function updateModelAvailability(c: any, result: ConnectorTestResult) {
  if (isModelBackedConnector(c.name)) useChat().modelKey = result.ok
}
function recordResult(c: any, result: ConnectorTestResult) {
  checkResults.value = recordConnectorResult(checkResults.value, c.name, result)
  updateModelAvailability(c, result)
}
async function save() {
  const name = editing.value.name
  saving.value = true
  try {
    checkResults.value = invalidateConnectorResults(checkResults.value, name)
    if (isModelBackedConnector(name)) useChat().modelKey = false
    await api.put(`/api/connectors/${name}/credential`, { value: value.value })
    dlg.value = false
    await load()
    const connector = items.value.find(c => c.name === name)
    if (connector) await check(connector)
  } finally {
    saving.value = false
  }
}
async function remove(c: any) {
  await api.del(`/api/connectors/${c.name}/credential`)
  if (isModelBackedConnector(c.name)) useChat().modelKey = false
  checkResults.value = invalidateConnectorResults(checkResults.value, c.name)
  await load()
}
async function check(c: any): Promise<ConnectorTestResult> {
  checking.value[c.name] = true
  try {
    const result = await api.post<ConnectorTestResult>(`/api/connectors/${encodeURIComponent(c.name)}/test`)
    recordResult(c, result)
    return result
  } catch {
    const result: ConnectorTestResult = { ok: false, status: 'unavailable', detail: 'The connectivity test could not be completed' }
    recordResult(c, result)
    return result
  } finally {
    checking.value[c.name] = false
  }
}
onMounted(load)
</script>
<style scoped>
@media (max-width: 700px) {
  :deep(.v-list-item) { padding-inline: 8px; }
  :deep(.v-list-item-title), :deep(.v-list-item-subtitle) {
    display: block;
    overflow: visible;
    white-space: normal;
    -webkit-line-clamp: unset;
  }
  :deep(.v-list-item__append) { margin-inline-start: 8px; }
  :deep(.v-list-item__append > div) { flex-wrap: wrap; justify-content: flex-end; }
  :deep(.v-list-item__append .text-caption) { min-width: 0 !important; width: 100%; text-align: right; overflow-wrap: anywhere; }
}
@media (max-width: 460px) {
  :deep(.v-list-item) { grid-template-areas: "prepend content" "append append"; }
  :deep(.v-list-item__append) { grid-area: append; margin: 8px 0 4px; }
}
</style>
