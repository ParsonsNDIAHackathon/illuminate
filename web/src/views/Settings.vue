<template>
  <v-container style="max-width: 860px">
    <h2 class="text-h6 mb-3">Settings</h2>
    <v-card class="mb-4" variant="outlined">
      <v-card-title class="text-subtitle-1">Consumer (root)</v-card-title>
      <v-card-text>
        <p class="text-body-2 mb-2" style="opacity:.75">Point the graph at a program and it is supply-chain illumination; point it at the buying organisation and it is vendor risk. Same graph, different root.</p>
        <v-autocomplete v-model="rootPick" :items="hits" item-title="name" item-value="id" v-model:search="q" no-filter hide-details :placeholder="ws.ws.root_label || 'search an entity'" @update:model-value="setRoot" clearable />
      </v-card-text>
    </v-card>
    <v-card class="mb-4" variant="outlined">
      <v-card-title class="text-subtitle-1">Writes</v-card-title>
      <v-card-text>
        <v-radio-group :model-value="ws.ws.permission_mode" @update:model-value="(v: any) => ws.save({ permission_mode: v })" hide-details>
          <v-radio value="ask_always" label="Ask every time (default) — every WRITE / DESTRUCTIVE statement is previewed and held" />
          <v-radio value="auto_create" label="Auto-approve pure creates; ask on modify and delete" />
          <v-radio value="session_allowlist" label="Session allowlist — approve a statement shape once and repeat it without re-prompting" />
        </v-radio-group>
        <p class="text-caption mt-2" style="opacity:.7">Destructive statements never auto-approve and require the affected count to be acknowledged. The same gate applies to MCP clients.</p>
      </v-card-text>
    </v-card>
    <v-card class="mb-4" variant="outlined">
      <v-card-title class="text-subtitle-1">Model tiers</v-card-title>
      <v-card-text>
        <div class="d-flex ga-3 flex-wrap">
          <v-text-field v-model="strong" label="Strong (chat, Cypher, synthesis)" :placeholder="ws.ws.defaults?.model_strong" hide-details style="min-width: 260px" @blur="saveModels" />
          <v-text-field v-model="fast" label="Fast (extraction, classification)" :placeholder="ws.ws.defaults?.model_fast" hide-details style="min-width: 260px" @blur="saveModels" />
          <v-text-field v-model="baseUrl" label="OpenAI-compatible base URL (optional)" hide-details style="min-width: 300px" @blur="saveModels" />
        </div>
        <p class="text-caption mt-2" style="opacity:.7">The key itself lives under <router-link to="/connectors">Connectors</router-link>. The constant system prefix (schema, tools, taxonomy) is prompt-cached.</p>
      </v-card-text>
    </v-card>
    <v-card variant="outlined">
      <v-card-title class="text-subtitle-1">MCP</v-card-title>
      <v-card-text class="text-body-2">
        Same tools, second transport. Streamable HTTP at <code>{{ origin }}/mcp</code>; stdio via <code>illuminate-mcp</code>. Writes from external agents queue here for approval exactly like chat.
      </v-card-text>
    </v-card>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, qs } from '../api/client'
import { useWorkspace } from '../stores/workspace'
const ws = useWorkspace()
const q = ref(''); const hits = ref<any[]>([]); const rootPick = ref<string | null>(null)
const strong = ref(''); const fast = ref(''); const baseUrl = ref('')
const origin = location.origin
let t: any
watch(q, (v) => { clearTimeout(t); if (!v || v.length < 2) return; t = setTimeout(async () => { hits.value = (await api.get(`/api/graph/search?${qs({ q: v, kind: 'entity', limit: 10 })}`)).results }, 250) })
async function setRoot(id: string | null) { if (!id) return; const h = hits.value.find(x => x.id === id); await ws.save({ root_id: id, root_label: h?.name || null }) }
async function saveModels() { await ws.save({ model_strong: strong.value || null, model_fast: fast.value || null, openai_base_url: baseUrl.value || null }) }
onMounted(async () => { if (!ws.loaded) await ws.load(); strong.value = ws.ws.model_strong || ''; fast.value = ws.ws.model_fast || ''; baseUrl.value = ws.ws.openai_base_url || '' })
</script>
