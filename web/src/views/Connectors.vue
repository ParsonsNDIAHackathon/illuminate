<template>
  <v-container style="max-width: 980px">
    <h2 class="text-h6 mb-1">Settings › Connectors</h2>
    <p class="text-body-2 mb-4" style="opacity:.75">Credentials are encrypted at rest and decrypted only inside the connector process; they never enter a prompt. Without an OpenAI key the app degrades to graph browsing and template queries.</p>
    <v-list lines="two">
      <v-list-item v-for="c in items" :key="c.name" :title="c.label" :subtitle="c.description">
        <template #prepend><v-icon :icon="c.connected ? 'mdi-check-circle' : 'mdi-key-alert'" :color="c.connected ? 'success' : 'warning'" /></template>
        <template #append>
          <div class="d-flex align-center ga-2">
            <v-chip size="x-small" variant="tonal" :color="c.trust === 'authoritative' ? 'primary' : undefined">{{ c.trust }}</v-chip>
            <span class="text-caption" style="min-width: 120px; text-align: right">{{ c.connected ? c.detail : 'Key needed' }}</span>
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
    <v-dialog v-model="dlg" max-width="520">
      <v-card v-if="editing">
        <v-card-title>{{ editing.label }} credential</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-2" v-if="editing.key_note">{{ editing.key_note }}</p>
          <p class="text-body-2 mb-3" v-if="editing.key_url">Register: <a :href="editing.key_url" target="_blank" rel="noopener">{{ editing.key_url }}</a></p>
          <v-text-field v-model="value" label="API key" type="password" autofocus hide-details @keydown.enter="save" />
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" @click="dlg = false">Cancel</v-btn><v-btn color="primary" variant="flat" @click="save" :disabled="!value.trim()">Save</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type ConnectorTestResult } from '../api/client'
import { useChat } from '../stores/chat'
const items = ref<any[]>([]); const dlg = ref(false); const editing = ref<any>(null); const value = ref(''); const checking = ref<Record<string, boolean>>({}); const checkResults = ref<Record<string, ConnectorTestResult>>({})
async function load() { items.value = await api.get('/api/connectors') }
function open(c: any) { editing.value = c; value.value = ''; dlg.value = true }
async function save() { await api.put(`/api/connectors/${editing.value.name}/credential`, { value: value.value }); dlg.value = false; await load(); if (editing.value.name === 'openai' || editing.value.name === 'websearch') useChat().modelKey = true }
async function remove(c: any) { await api.del(`/api/connectors/${c.name}/credential`); await load() }
async function check(c: any) {
  checking.value[c.name] = true
  try {
    checkResults.value[c.name] = await api.post<ConnectorTestResult>(`/api/connectors/${encodeURIComponent(c.name)}/test`)
  } catch {
    checkResults.value[c.name] = { ok: false, status: 'unavailable', detail: 'The connectivity test could not be completed' }
  } finally {
    checking.value[c.name] = false
  }
}
onMounted(load)
</script>
