<template>
  <main class="share-page">
    <header class="share-hero">
      <div>
        <div class="eyebrow">INTEROPERABILITY / VERSIONED FINDINGS</div>
        <h1>Share findings without flattening their evidence.</h1>
        <p>The reusable product is the export contract—not the graph drawing. Every consumer must preserve provenance, classification, truth status, simulation state, and quality.</p>
      </div>
      <v-chip color="primary" variant="tonal">Schema {{ page?.meta.schema_version || '—' }}</v-chip>
    </header>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">
      <strong>Findings preview unavailable.</strong> {{ error }}
      <template #append><v-btn variant="text" @click="load">Retry</v-btn></template>
    </v-alert>
    <v-progress-linear v-if="loading" indeterminate color="secondary" class="mb-4" />

    <section v-if="page" aria-labelledby="snapshot-title">
      <div class="section-heading"><div><span>01 / EXPORT SNAPSHOT</span><h2 id="snapshot-title">Bounded, repeatable, and lifecycle-aware.</h2></div><v-btn variant="text" prepend-icon="mdi-refresh" @click="load">Refresh</v-btn></div>
      <div class="metrics">
        <article><span>GENERATED</span><strong>{{ formatDate(page.meta.generated_at) }}</strong></article>
        <article><span>PREVIEW COUNT</span><strong>{{ page.meta.count }}</strong><small>bounded to {{ previewLimit }}</small></article>
        <article><span>FORMATS</span><strong>JSON · NDJSON · CSV</strong></article>
        <article><span>PAGINATION</span><strong>{{ page.meta.next_cursor ? 'MORE AVAILABLE' : 'END OF SNAPSHOT' }}</strong></article>
      </div>
      <div class="watermark"><strong>Opaque watermark</strong><code>{{ page.meta.watermark }}</code><v-btn size="small" variant="text" @click="copy(page.meta.watermark)">Copy</v-btn></div>
      <p class="semantics">Follow every continuation cursor before storing the final watermark. Incremental reads upsert by <code>finding_id</code> and may include <code>deleted: true</code> tombstones. Never infer truth from confidence or remove simulation and handling fields.</p>
      <div class="downloads">
        <v-btn v-for="format in formats" :key="format" color="primary" variant="outlined" prepend-icon="mdi-download" :href="downloadUrl(format)" download>
          Download {{ format.toUpperCase() }} page
        </v-btn>
      </div>
      <small class="download-note">Each file is one bounded page of at most 1,000 findings. JSON carries continuation metadata in the body; NDJSON and CSV carry it in response headers. Use the consumer flow below for complete multi-page synchronization.</small>
    </section>

    <section aria-labelledby="preview-title">
      <div class="section-heading"><div><span>02 / FINDING PREVIEW</span><h2 id="preview-title">Inspect the contract before consuming it.</h2></div></div>
      <div v-if="page && !page.findings.length" class="empty-state">No findings are currently available. The export contract is healthy, but there is nothing to download in this snapshot.</div>
      <v-expansion-panels v-else-if="page" variant="accordion">
        <v-expansion-panel v-for="finding in page.findings" :key="finding.finding_id">
          <v-expansion-panel-title>
            <div class="finding-title"><strong>{{ finding.subject_name || finding.subject_id }}</strong><span>{{ finding.predicate }}</span></div>
            <v-chip size="x-small" :color="finding.simulated ? 'warning' : 'info'" class="mr-2">{{ finding.simulated ? 'SIMULATED' : finding.truth_status }}</v-chip>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="finding-meta"><span>Classification: {{ finding.classification }}</span><span>Truth: {{ finding.truth_status }}</span><span>Provenance records: {{ finding.provenance?.length || 0 }}</span><span>Paths: {{ finding.paths?.length || 0 }}</span></div>
            <pre>{{ JSON.stringify(finding, null, 2) }}</pre>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </section>

    <section aria-labelledby="consume-title">
      <div class="section-heading"><div><span>03 / CONSUMER START</span><h2 id="consume-title">Full snapshot and incremental synchronization.</h2></div></div>
      <div class="code-grid">
        <article><div><strong>Full traversal</strong><v-btn size="small" variant="text" @click="copy(fullExample)">Copy</v-btn></div><pre>{{ fullExample }}</pre></article>
        <article><div><strong>Incremental read</strong><v-btn size="small" variant="text" @click="copy(incrementalExample)">Copy</v-btn></div><pre>{{ incrementalExample }}</pre></article>
      </div>
      <div class="links">
        <a href="/api/exports/v1/schema" target="_blank">JSON Schema</a>
        <a href="/api/exports/v1/fields" target="_blank">Field definitions</a>
        <a href="/api/exports/v1/sample" target="_blank">Sample data</a>
        <a href="/docs" target="_blank">API documentation</a>
      </div>
    </section>

    <section aria-labelledby="catalog-title">
      <div class="section-heading"><div><span>04 / NDIA EVENT 3</span><h2 id="catalog-title">Catalog contribution state.</h2></div><v-btn variant="text" prepend-icon="mdi-refresh" @click="loadCatalog">Refresh status</v-btn></div>
      <v-alert v-if="catalogError" type="error" variant="tonal" class="mb-3">{{ catalogError }}</v-alert>
      <v-card v-if="catalogPreview" variant="outlined">
        <v-card-text>
          <div class="catalog-state">
            <v-chip :color="catalogPublished ? 'success' : catalogResult?.dry_run ? 'info' : 'warning'" variant="flat">{{ catalogLabel }}</v-chip>
            <strong>{{ catalogPreview.event.title }}</strong>
          </div>
          <p>{{ catalogResult?.message || catalogPreview.message }}</p>
          <dl>
            <div><dt>Export identity</dt><dd>{{ catalogPreview.export_id }} · v{{ catalogPreview.export_version }}</dd></div>
            <div><dt>Remote dataset identity</dt><dd>{{ catalogDatasetId || 'Not recorded' }}</dd></div>
            <div><dt>Write readiness</dt><dd>{{ catalogPreview.publication_ready ? 'Configured; live submission remains permission-gated and explicitly confirmed' : 'Organizer write configuration unavailable; dry-run only' }}</dd></div>
          </dl>
          <v-alert type="info" variant="tonal" density="compact">A validated dry run is not publication. “Published” appears only when the server has recorded a remote dataset identity.</v-alert>
        </v-card-text>
        <v-card-actions>
          <v-btn color="primary" :loading="catalogBusy" @click="runDryRun">Validate dry run</v-btn>
          <span class="operator-note">Live publication remains server-side and operator-authorized; catalog credentials are never sent to this browser.</span>
        </v-card-actions>
      </v-card>
    </section>

    <v-snackbar v-model="copied" timeout="1800">Copied to clipboard</v-snackbar>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ndiaCatalog, type CatalogContributionPreview, type CatalogContributionResult, type FindingExportPage } from '../api/client'

const previewLimit = 10
const formats = ['json', 'ndjson', 'csv']
const page = ref<FindingExportPage | null>(null)
const loading = ref(false)
const error = ref('')
const catalogPreview = ref<CatalogContributionPreview | null>(null)
const catalogResult = ref<CatalogContributionResult | null>(null)
const catalogError = ref('')
const catalogBusy = ref(false)
const copied = ref(false)
const baseUrl = window.location.origin
const fullExample = `curl -fsS '${baseUrl}/api/exports/v1/findings?limit=100&format=json'\n# Follow meta.next_cursor; store the final meta.watermark only after all pages commit.`
const incrementalExample = computed(() => `curl -fsS '${baseUrl}/api/exports/v1/findings/incremental?limit=100&since=${encodeURIComponent(page.value?.meta.watermark || 'YOUR_OPAQUE_WATERMARK')}'\n# Upsert stable finding_id values and apply deleted:true tombstones.`)
const catalogDatasetId = computed(() => catalogResult.value?.dataset_id || catalogPreview.value?.remote_dataset_id || null)
const catalogPublished = computed(() => Boolean(catalogDatasetId.value) && (catalogResult.value?.contribution_state || catalogPreview.value?.contribution_state) === 'published')
const catalogLabel = computed(() => catalogPublished.value ? 'PUBLISHED' : catalogResult.value?.dry_run ? 'VALIDATED DRY RUN' : (catalogResult.value?.contribution_state || catalogPreview.value?.contribution_state || 'NOT SUBMITTED').replaceAll('_', ' ').toUpperCase())

function formatDate(value: string) { return new Date(value).toLocaleString() }
function downloadUrl(format: string) { return `/api/exports/v1/findings?limit=1000&format=${format}` }
async function copy(value: string) { await navigator.clipboard.writeText(value); copied.value = true }
async function load() {
  loading.value = true; error.value = ''
  try { page.value = await api.get<FindingExportPage>(`/api/exports/v1/findings?limit=${previewLimit}`) }
  catch (cause: any) { error.value = cause.message }
  finally { loading.value = false }
}
async function loadCatalog() {
  catalogError.value = ''
  const [preview, status] = await Promise.allSettled([ndiaCatalog.preview(), ndiaCatalog.status()])
  if (preview.status === 'fulfilled') catalogPreview.value = preview.value
  if (status.status === 'fulfilled') catalogResult.value = status.value
  const failures = [preview, status].filter(result => result.status === 'rejected') as PromiseRejectedResult[]
  if (failures.length) catalogError.value = `Catalog state partially unavailable: ${failures.map(result => result.reason?.message || 'request failed').join('; ')}`
}
async function runDryRun() {
  if (!catalogPreview.value) return
  catalogBusy.value = true; catalogError.value = ''
  try { catalogResult.value = await ndiaCatalog.submit(catalogPreview.value.confirmation_token, true) }
  catch (cause: any) { catalogError.value = `Dry run failed: ${cause.message}` }
  finally { catalogBusy.value = false }
}
onMounted(() => { void load(); void loadCatalog() })
</script>

<style scoped>
.share-page { max-width: 1320px; margin: 0 auto; padding: 32px; }
.share-hero, .section-heading, .catalog-state { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.share-hero { padding: 24px 0 36px; }
.share-hero h1 { font-size: clamp(2rem, 4vw, 3.5rem); max-width: 850px; line-height: 1.05; margin: 8px 0 14px; }
.share-hero p { max-width: 850px; opacity: .78; }
.eyebrow, .section-heading span, article > span { font: 700 .72rem 'IBM Plex Mono', monospace; letter-spacing: .13em; color: rgb(var(--v-theme-secondary)); }
section { margin-bottom: 44px; }
.section-heading { margin-bottom: 18px; }
.section-heading h2 { margin-top: 4px; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.metrics article { padding: 18px; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 8px; display: grid; gap: 8px; }
.metrics strong { font-size: 1.05rem; }
.metrics small { opacity: .65; }
.watermark { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; margin-top: 14px; padding: 12px; background: rgba(var(--v-theme-surface-variant), .35); border-radius: 6px; }
.watermark code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.semantics { margin: 16px 0; max-width: 1000px; }
.downloads, .links { display: flex; flex-wrap: wrap; gap: 10px; }
.download-note { display: block; max-width: 900px; margin-top: 10px; opacity: .68; }
.finding-title { display: grid; flex: 1; }
.finding-title span, .finding-meta { opacity: .7; font-size: .85rem; }
.finding-meta { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px; }
pre { overflow: auto; white-space: pre-wrap; background: #10151c; color: #dce7f3; border-radius: 6px; padding: 16px; font-size: .78rem; }
.code-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.code-grid article { border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 8px; padding: 14px; }
.code-grid article > div { display: flex; align-items: center; justify-content: space-between; }
.empty-state { border: 1px dashed currentColor; border-radius: 8px; padding: 24px; opacity: .7; }
.catalog-state { justify-content: flex-start; margin-bottom: 12px; }
dl > div { display: grid; grid-template-columns: 180px 1fr; gap: 12px; margin: 8px 0; }
dt { opacity: .65; } dd { margin: 0; }
.operator-note { font-size: .78rem; opacity: .68; padding: 0 10px; }
@media (max-width: 800px) { .share-page { padding: 20px; } .metrics, .code-grid { grid-template-columns: 1fr; } .share-hero { align-items: flex-start; } .watermark { grid-template-columns: 1fr auto; } .watermark strong { grid-column: 1 / -1; } }
</style>