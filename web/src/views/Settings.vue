<template>
  <v-container style="max-width: 980px">
    <v-toolbar color="transparent" density="compact" class="mb-2">
      <v-toolbar-title class="text-h6">Settings</v-toolbar-title>
    </v-toolbar>
    <v-tabs :model-value="activeSection" color="primary" class="mb-5" @update:model-value="setSection">
      <v-tab value="general" prepend-icon="mdi-tune">General</v-tab>
      <v-tab value="connectors" prepend-icon="mdi-power-plug">Connectors</v-tab>
    </v-tabs>

    <v-window :model-value="activeSection">
      <v-window-item value="general">
        <v-card class="mb-4" variant="outlined">
        <v-card-title class="text-subtitle-1">Writes</v-card-title>
        <v-card-text>
          <v-radio-group :model-value="ws.ws.permission_mode" @update:model-value="(v: any) => ws.save({ permission_mode: v })" hide-details>
            <v-radio value="ask_always" label="Ask every time (default) — every WRITE / DESTRUCTIVE statement is previewed and held" />
            <v-radio value="auto_create" label="Auto-approve pure creates; ask on modify and delete" />
            <v-radio value="session_allowlist" label="Session allowlist — approve a statement shape once and repeat it without re-prompting" />
          </v-radio-group>
          <v-card-subtitle class="px-0 pt-2">Destructive statements never auto-approve and require the affected count to be acknowledged. The same gate applies to MCP clients.</v-card-subtitle>
        </v-card-text>
        </v-card>
        <v-card class="mb-4" variant="outlined">
          <v-card-title class="text-subtitle-1">Canvas</v-card-title>
          <v-card-text>
            <v-switch :model-value="ws.riskEmphasis" @update:model-value="(v: any) => ws.setRiskEmphasis(!!v)"
                      color="primary" density="compact" hide-details
                      label="Mark risk on the canvas — halo and score on every node the scorer has graded" />
            <p class="text-caption mt-2" style="opacity:.7">
              Off by default, and worth leaving off to start with: a supply chain drawn without it is the picture
              everyone already has — a few hundred identical discs, with nothing saying which one is the problem.
              Turning it on, or asking the chat to colour by risk, is the difference this tool makes.
              Risk is always available either way — on the <router-link to="/data/risk">Risk tab</router-link>, in a node's
              properties, and in any report.
            </p>
          </v-card-text>
        </v-card>
        <v-card class="mb-4" variant="outlined">
        <v-card-title class="text-subtitle-1">Model tiers</v-card-title>
        <v-card-text>
          <v-sheet color="transparent" class="d-flex ga-3 flex-wrap">
            <v-text-field v-model="strong" label="Strong (chat, Cypher, synthesis)" :placeholder="ws.ws.defaults?.model_strong" hide-details style="min-width: 260px" @blur="saveModels" />
            <v-text-field v-model="fast" label="Fast (extraction, classification)" :placeholder="ws.ws.defaults?.model_fast" hide-details style="min-width: 260px" @blur="saveModels" />
            <v-text-field v-model="baseUrl" label="OpenAI-compatible base URL (optional)" hide-details style="min-width: 300px" @blur="saveModels" />
          </v-sheet>
          <v-card-subtitle class="px-0 pt-2">Manage API keys from the Connectors segment above. The constant system prefix (schema, tools, taxonomy) is prompt-cached.</v-card-subtitle>
        </v-card-text>
        </v-card>
        <v-card variant="outlined">
        <v-card-title class="text-subtitle-1">MCP</v-card-title>
        <v-card-text class="text-body-2">
          Same tools, second transport. Streamable HTTP at <code>{{ origin }}/mcp</code>; stdio via <code>illuminate-mcp</code>. Writes from external agents queue here for approval exactly like chat.
        </v-card-text>
        </v-card>
      </v-window-item>
      <v-window-item value="connectors">
        <Connectors embedded />
      </v-window-item>
    </v-window>
  </v-container>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspace } from '../stores/workspace'
import Connectors from './Connectors.vue'
const props = defineProps<{ section?: string }>()
const ws = useWorkspace()
const router = useRouter()
const strong = ref(''); const fast = ref(''); const baseUrl = ref('')
const origin = location.origin
const activeSection = computed(() => props.section === 'connectors' ? 'connectors' : 'general')
function setSection(section: unknown) { router.push(section === 'connectors' ? '/settings/connectors' : '/settings') }
async function saveModels() { await ws.save({ model_strong: strong.value || null, model_fast: fast.value || null, openai_base_url: baseUrl.value || null }) }
onMounted(async () => { if (!ws.loaded) await ws.load(); strong.value = ws.ws.model_strong || ''; fast.value = ws.ws.model_fast || ''; baseUrl.value = ws.ws.openai_base_url || '' })
</script>
