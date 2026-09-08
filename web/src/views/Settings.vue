<template>
  <v-container style="max-width: 860px">
    <h1 class="text-h6 mb-1">Administration</h1>
    <p class="text-body-2 mb-3" style="opacity:.75">Manage workspace behavior and data access from one place.</p>
    <v-card class="mb-4" variant="outlined">
      <v-card-title class="text-subtitle-1">Data connectors</v-card-title>
      <v-card-text class="d-flex align-center flex-wrap ga-3">
        <span class="text-body-2">Add, replace, test, or remove credentials used by external data sources.</span>
        <v-spacer />
        <v-btn :to="{ path: '/connectors', query: route.query }" prepend-icon="mdi-power-plug-outline" variant="tonal">Manage connectors</v-btn>
      </v-card-text>
    </v-card>
    <v-card class="mb-4" variant="outlined">
      <v-card-title class="text-subtitle-1">NDIA catalog contribution</v-card-title>
      <v-card-text>
        <p class="text-body-2 mb-3" style="opacity:.75">Review the exact event 3 dataset record before running a validation-only dry run or publishing it. Credentials never enter the browser.</p>
        <v-alert v-if="catalogError" type="error" variant="tonal" class="mb-3">{{ catalogError }}</v-alert>
        <v-alert v-if="catalogResult" :type="catalogResult.dataset_id ? 'success' : 'info'" variant="tonal" class="mb-3">
          <strong>{{ catalogResult.contribution_state }}</strong> — {{ catalogResult.message }}
          <span v-if="catalogResult.dataset_id"> Dataset ID: <code>{{ catalogResult.dataset_id }}</code></span>
        </v-alert>
        <div v-if="catalogPreview">
          <v-table density="compact" class="mb-3">
            <tbody>
              <tr v-for="(value, key) in catalogPreview.metadata" :key="key">
                <th class="text-caption" style="width: 180px">{{ key }}</th>
                <td class="text-body-2 py-2">{{ Array.isArray(value) ? value.join(', ') : value }}</td>
              </tr>
              <tr><th class="text-caption">export_watermark</th><td><code class="text-caption">{{ catalogPreview.export_watermark }}</code></td></tr>
            </tbody>
          </v-table>
          <v-checkbox v-model="catalogConfirmed" label='I reviewed this exact record and confirm “PUBLISH EVENT 3”.' hide-details class="mb-2" />
          <v-text-field
            v-model="catalogOperatorToken"
            label="Operator authorization code (live publish only)"
            type="password"
            autocomplete="off"
            hide-details
            class="mb-3"
          />
          <div class="d-flex ga-2 flex-wrap">
            <v-btn variant="outlined" :loading="catalogBusy" :disabled="!catalogConfirmed" @click="submitCatalog(true)">Validate dry run</v-btn>
            <v-btn color="primary" :loading="catalogBusy" :disabled="!catalogConfirmed || !catalogPreview.publication_ready" @click="submitCatalog(false)">Publish to NDIA</v-btn>
            <v-btn variant="text" :loading="catalogBusy" @click="loadCatalog(true)">Refresh status</v-btn>
          </div>
          <p v-if="!catalogPreview.publication_ready" class="text-caption mt-2" style="opacity:.7">Live publication needs a server-side NDIA key and public dataset URL. Dry-run remains available.</p>
        </div>
        <v-progress-linear v-else-if="catalogBusy" indeterminate />
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
        <p class="text-caption mt-2" style="opacity:.7">The key itself is managed in <router-link :to="{ path: '/connectors', query: route.query }">Administration › Data connectors</router-link>. The constant system prefix (schema, tools, taxonomy) is prompt-cached.</p>
      </v-card-text>
    </v-card>
    <v-card variant="outlined">
      <v-card-title class="text-subtitle-1">MCP</v-card-title>
      <v-card-text class="text-body-2">
        Same tools, second transport. Streamable HTTP at <code>{{ origin }}/mcp/</code>; stdio via <code>illuminate-mcp</code>. Writes from external agents queue here for approval exactly like chat.
      </v-card-text>
    </v-card>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ndiaCatalog, type CatalogContributionPreview, type CatalogContributionResult } from '../api/client'
import { useWorkspace } from '../stores/workspace'
const ws = useWorkspace()
const route = useRoute()
const strong = ref(''); const fast = ref(''); const baseUrl = ref('')
const catalogPreview = ref<CatalogContributionPreview | null>(null)
const catalogResult = ref<CatalogContributionResult | null>(null)
const catalogConfirmed = ref(false)
const catalogOperatorToken = ref('')
const catalogBusy = ref(false)
const catalogError = ref('')
const origin = location.origin
async function saveModels() { await ws.save({ model_strong: strong.value || null, model_fast: fast.value || null, openai_base_url: baseUrl.value || null }) }
async function loadCatalog(refresh = false) {
  catalogBusy.value = true; catalogError.value = ''
  const errors: string[] = []
  try { catalogResult.value = await ndiaCatalog.status(refresh) }
  catch (e: any) { errors.push(e?.message || 'Status request failed') }
  try {
    catalogPreview.value = await ndiaCatalog.preview()
    catalogConfirmed.value = false
  } catch (e: any) { errors.push(e?.message || 'Preview request failed') }
  catalogError.value = errors.join(' ')
  catalogBusy.value = false
}
async function submitCatalog(dryRun: boolean) {
  if (!catalogPreview.value || !catalogConfirmed.value) return
  catalogBusy.value = true; catalogError.value = ''
  try {
    catalogResult.value = await ndiaCatalog.submit(
      catalogPreview.value.confirmation_token, dryRun,
      dryRun ? undefined : catalogOperatorToken.value,
    )
    catalogPreview.value = await ndiaCatalog.preview()
    catalogConfirmed.value = false
  } catch (e: any) {
    catalogError.value = e?.message || 'Catalog request failed'
    try { catalogPreview.value = await ndiaCatalog.preview(); catalogConfirmed.value = false } catch {}
  }
  finally { catalogBusy.value = false }
}
onMounted(async () => {
  if (!ws.loaded) await ws.load()
  strong.value = ws.ws.model_strong || ''; fast.value = ws.ws.model_fast || ''; baseUrl.value = ws.ws.openai_base_url || ''
  await loadCatalog()
})
</script>
<style scoped>
:deep(td), :deep(code) { overflow-wrap: anywhere; }
@media (max-width: 767px) {
  :deep(.v-radio .v-label) { white-space: normal; line-height: 1.35; }
  :deep(.v-radio) { align-items: flex-start; margin-bottom: 8px; }
  .d-flex.ga-3 > .v-input { min-width: 100% !important; width: 100%; }
}
@media (max-width: 600px) {
  :deep(.v-table table) { width: 100%; min-width: 0 !important; }
  :deep(.v-table tbody), :deep(.v-table tr), :deep(.v-table th), :deep(.v-table td) { display: block; width: 100%; }
  :deep(.v-table tr) { padding-block: 6px; border-bottom: thin solid rgba(var(--v-border-color), var(--v-border-opacity)); }
  :deep(.v-table th) { width: auto !important; }
  :deep(.v-table th), :deep(.v-table td) { min-width: 0; height: auto; border: 0; }
  :deep(.v-table th) { padding-bottom: 2px !important; }
  :deep(.v-table td) { padding-top: 2px !important; }
}
</style>
