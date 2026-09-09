<template>
  <div class="reports">
    <div class="list">
      <div class="list-head">
        <h2 class="text-subtitle-1">Reports</h2>
        <v-spacer />
        <span class="text-caption">{{ store.items.length }}</span>
        <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="newDlg = true">New</v-btn>
      </div>
      <v-progress-linear v-if="store.loading" indeterminate height="2" />
      <div v-if="!store.items.length && !store.loading" class="empty">
        <p>No reports yet.</p>
        <p class="mt-2">Ask the chat for one — “write a risk assessment for the V-22” — press <b>New</b>, or use
          the Report control on any organisation's properties card. A report is stored in the graph beside its
          subject and can be regenerated whenever the graph has moved on.</p>
      </div>
      <v-list density="compact" nav>
        <v-list-item v-for="r in store.items" :key="r.id" :active="r.id === openId" @click="open(r.id)">
          <template #prepend><v-icon size="18" :icon="kindIcon(r.kind)" /></template>
          <v-list-item-title>{{ r.subject_name || r.title }}</v-list-item-title>
          <v-list-item-subtitle>
            {{ kindLabel(r.kind) }} · {{ when(r.generated_at) }}
          </v-list-item-subtitle>
          <template #append>
            <v-chip v-if="r.finding_count" size="x-small" variant="tonal" :color="bandChip(r.top_band)"
                    :title="`${r.finding_count} finding(s)`">{{ r.finding_count }}</v-chip>
            <v-chip v-if="r.simulated" size="x-small" color="warning" variant="tonal" class="ml-1">SIM</v-chip>
          </template>
        </v-list-item>
      </v-list>
    </div>

    <div class="reader">
      <template v-if="current">
        <div class="reader-head">
          <div class="titles">
            <div class="text-subtitle-1">{{ current.title }}</div>
            <div class="text-caption" style="opacity:.75">
              Generated {{ when(current.generated_at) }}
              <span v-if="current.generated_by && current.generated_by !== 'derived'"> · narrative by {{ current.generated_by }}</span>
              <span v-else> · computed from the graph, no model narrative</span>
              <span v-if="current.cited_count"> · cites {{ current.cited_count }} node{{ current.cited_count === 1 ? '' : 's' }}</span>
            </div>
          </div>
          <v-spacer />
          <v-btn size="small" variant="tonal" prepend-icon="mdi-refresh" :loading="store.busy === current.id"
                 title="Rebuild this report from current graph data — same report, new timestamp"
                 @click="regenerate">Regenerate</v-btn>
          <v-btn size="small" variant="text" prepend-icon="mdi-graph" title="Show the subject and this report on the canvas"
                 @click="openInGraph">Open in graph</v-btn>
          <v-menu location="bottom end">
            <template #activator="{ props }"><v-btn v-bind="props" size="small" variant="text" icon="mdi-dots-vertical" /></template>
            <v-list density="compact">
              <v-list-item prepend-icon="mdi-open-in-new" title="Open in a new tab" @click="openTab" />
              <v-list-item prepend-icon="mdi-download" title="Download .html" @click="download" />
              <v-list-item prepend-icon="mdi-delete-outline" title="Delete report" @click="confirmDelete = true" />
            </v-list>
          </v-menu>
        </div>
        <p v-if="store.error" class="text-error text-body-2 px-4">{{ store.error }}</p>
        <!-- The document is a whole HTML file with its own stylesheet, so it renders in a frame
             rather than being spliced into the app. sandbox keeps it inert: no scripts, no
             access to this origin, and links leave for a real tab instead of navigating the frame. -->
        <iframe class="doc" :srcdoc="current.html" sandbox="allow-popups allow-popups-to-escape-sandbox"
                referrerpolicy="no-referrer" title="Report" />
      </template>
      <div v-else-if="loadingDoc" class="placeholder"><v-progress-circular indeterminate size="26" /></div>
      <div v-else class="placeholder">
        <p class="text-body-2" style="opacity:.7">Pick a report to read it.</p>
      </div>
    </div>

    <v-dialog v-model="newDlg" max-width="560">
      <v-card>
        <v-card-title class="text-subtitle-1">New report</v-card-title>
        <v-card-text>
          <v-select v-model="kind" :items="store.kinds" item-title="label" item-value="kind" label="Kind"
                    density="comfortable" hide-details class="mb-1" />
          <p class="text-caption mb-3" style="opacity:.7">{{ kindDescription }}</p>
          <v-autocomplete v-model="subjectId" :items="subjectItems" :loading="searching" v-model:search="subjectQuery"
                          item-title="name" item-value="id" label="Subject" density="comfortable" hide-details
                          no-filter :no-data-text="subjectQuery ? 'No match' : 'Type to search entities'" />
          <p v-if="genError" class="text-error text-body-2 mt-3">{{ genError }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="newDlg = false">Cancel</v-btn>
          <v-btn color="primary" :disabled="!subjectId" :loading="!!store.busy" @click="generate">Generate</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="confirmDelete" max-width="460">
      <v-card>
        <v-card-title class="text-subtitle-1">Delete this report?</v-card-title>
        <v-card-text class="text-body-2">
          It is removed from the graph along with the edges to what it cites. Nothing it was written from is
          touched, so the same report can be generated again.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmDelete = false">Cancel</v-btn>
          <v-btn color="error" variant="tonal" @click="remove">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, qs } from '../api/client'
import { useReports, type Report } from '../stores/reports'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { bandChip } from '../styles/risk'

const store = useReports(); const graph = useGraph(); const ws = useWorkspace()
const route = useRoute(); const router = useRouter()
const props = defineProps<{ id?: string }>()

const current = ref<Report | null>(null)
const loadingDoc = ref(false)
const openId = computed(() => current.value?.id || props.id || null)
const newDlg = ref(false); const confirmDelete = ref(false)
const kind = ref(store.defaultKind); const subjectId = ref<string | null>(null)
const subjectQuery = ref(''); const subjectItems = ref<any[]>([]); const searching = ref(false)
const genError = ref('')

const kindDescription = computed(() => store.kinds.find(k => k.kind === kind.value)?.description || '')
function kindLabel(k: string) { return store.kinds.find(x => x.kind === k)?.label || k }
function kindIcon(k: string) { return k === 'risk_assessment' ? 'mdi-shield-alert-outline' : 'mdi-domain' }
function when(iso?: string) { return iso ? new Date(iso).toLocaleString() : '—' }

async function open(id: string) {
  if (route.params.id !== id) router.replace(`/reports/${id}`)
  loadingDoc.value = true
  try { current.value = await store.fetch(id) } catch { current.value = null } finally { loadingDoc.value = false }
}
async function regenerate() {
  if (!current.value) return
  await store.regenerate(current.value.id)
  await open(current.value.id)
}
async function remove() {
  if (!current.value) return
  const id = current.value.id
  confirmDelete.value = false
  await store.remove(id)
  current.value = null
  router.replace('/reports')
}
/** Draw the subject and the report next to each other, with what the report cites lit up —
 *  the same evidence in the document and on the canvas. */
async function openInGraph() {
  if (!current.value) return
  const r = current.value
  await graph.loadNeighbourhood(r.subject_id, ws.depth, { ...ws.ws.layers, reports: true })
  graph.select(r.id)
  if (r.element_ids?.length) graph.trace(r.element_ids)
  router.push('/')
}
function blob() { return new Blob([current.value?.html || ''], { type: 'text/html;charset=utf-8' }) }
function openTab() { const u = URL.createObjectURL(blob()); window.open(u, '_blank', 'noopener'); setTimeout(() => URL.revokeObjectURL(u), 60000) }
function download() {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob())
  a.download = `${(current.value?.title || 'report').replace(/[^\w.-]+/g, '-').toLowerCase()}.html`
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 60000)
}
async function generate() {
  genError.value = ''
  try {
    const row = await store.generate(kind.value, subjectId.value!)
    newDlg.value = false
    await open(row.id)
  } catch (e: any) { genError.value = e?.message || String(e) }
}

// Programs first: a risk assessment is normally asked for about one, and typing is only
// needed for the rest of the graph.
let t: any
watch(subjectQuery, (q) => {
  clearTimeout(t)
  if (!q || q.length < 2) { subjectItems.value = graph.programs; return }
  t = setTimeout(async () => {
    searching.value = true
    try { subjectItems.value = (await api.get(`/api/graph/search?${qs({ q, kind: 'entity', limit: 12 })}`)).results }
    finally { searching.value = false }
  }, 250)
})
watch(newDlg, (v) => {
  if (!v) return
  kind.value = store.defaultKind
  genError.value = ''
  if (!graph.programs.length) graph.loadPrograms()
  subjectItems.value = graph.programs
  subjectId.value = graph.focusId || graph.programs[0]?.id || null
})
watch(() => props.id, (id) => { if (id && id !== current.value?.id) open(id) })
onMounted(async () => {
  await store.load()
  if (props.id) open(props.id)
  else if (store.items.length) open(store.items[0].id)
})
</script>

<style scoped>
.reports { display: grid; grid-template-columns: 320px 1fr; height: calc(100vh - 48px); }
.list { border-right: 1px solid rgba(128,128,128,.2); overflow-y: auto; min-width: 0; }
.list-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid rgba(128,128,128,.2); }
.empty { padding: 16px 14px; font-size: 13px; opacity: .8; }
.reader { display: flex; flex-direction: column; min-width: 0; }
.reader-head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid rgba(128,128,128,.2); }
.titles { min-width: 0; }
.titles .text-subtitle-1 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc { flex: 1; width: 100%; border: 0; background: #fff; }
.placeholder { flex: 1; display: flex; align-items: center; justify-content: center; }
</style>
