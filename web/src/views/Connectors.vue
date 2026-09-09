<template>
  <v-container :class="embedded ? 'pa-0' : undefined" :style="embedded ? undefined : 'max-width: 980px'">
    <v-toolbar v-if="!embedded" color="transparent" density="compact" class="mb-1">
      <v-toolbar-title class="text-h6">Settings › Connectors</v-toolbar-title>
    </v-toolbar>
    <v-card-subtitle class="px-0 mb-4">Credentials are encrypted at rest and decrypted only inside the connector process; they never enter a prompt. Without an OpenAI key the app degrades to graph browsing and template queries.</v-card-subtitle>
    <v-list lines="two" bg-color="transparent">
      <v-list-item v-for="c in items" :key="c.name" :title="c.label" :subtitle="c.description">
        <template #prepend><v-icon :icon="c.connected ? 'mdi-check-circle' : 'mdi-key-alert'" :color="c.connected ? 'success' : 'warning'" /></template>
        <template #append>
          <v-sheet color="transparent" class="d-flex align-center ga-2">
            <v-chip size="x-small" variant="tonal" :color="c.trust === 'authoritative' ? 'primary' : undefined">{{ c.trust }}</v-chip>
            <v-chip size="x-small" variant="text" style="min-width: 120px; justify-content: end">{{ c.connected ? c.detail : 'Key needed' }}</v-chip>
            <v-btn v-if="c.key_name" @click="open(c)">{{ c.connected ? 'Replace' : 'Add credential' }}</v-btn>
            <v-btn v-if="c.key_name && c.connected" icon="mdi-delete-outline" variant="text" @click="remove(c)" />
            <v-btn v-if="c.name === 'openai' && c.connected" variant="text" @click="check" :loading="checking">Test</v-btn>
          </v-sheet>
        </template>
      </v-list-item>
    </v-list>
    <v-alert v-if="checkResult" :type="checkResult.ok ? 'success' : 'error'" variant="tonal" density="compact" class="mt-2">{{ checkResult.ok ? `Key works — ${checkResult.models} models visible` : checkResult.error }}</v-alert>
    <v-dialog v-model="dlg" max-width="520">
      <v-card v-if="editing">
        <v-card-title>{{ editing.label }} credential</v-card-title>
        <v-card-text>
          <v-card-subtitle v-if="editing.key_note" class="px-0 mb-2">{{ editing.key_note }}</v-card-subtitle>
          <v-btn v-if="editing.key_url" :href="editing.key_url" target="_blank" rel="noopener" variant="text" prepend-icon="mdi-open-in-new" class="px-0 mb-3">Register for a key</v-btn>
          <v-text-field v-model="value" label="API key" type="password" autofocus hide-details @keydown.enter="save" />
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" @click="dlg = false">Cancel</v-btn><v-btn color="primary" variant="flat" @click="save" :disabled="!value.trim()">Save</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import { useChat } from '../stores/chat'
defineProps<{ embedded?: boolean }>()
const items = ref<any[]>([]); const dlg = ref(false); const editing = ref<any>(null); const value = ref(''); const checking = ref(false); const checkResult = ref<any>(null)
async function load() { items.value = await api.get('/api/connectors') }
function open(c: any) { editing.value = c; value.value = ''; dlg.value = true }
async function save() { await api.put(`/api/connectors/${editing.value.name}/credential`, { value: value.value }); dlg.value = false; await load(); if (editing.value.name === 'openai' || editing.value.name === 'websearch') useChat().modelKey = true }
async function remove(c: any) { await api.del(`/api/connectors/${c.name}/credential`); await load() }
async function check() { checking.value = true; try { checkResult.value = await api.post('/api/connectors/openai/check') } finally { checking.value = false } }
onMounted(load)
</script>
