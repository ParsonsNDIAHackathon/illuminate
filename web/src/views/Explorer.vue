<template>
  <div class="explorer">
    <div class="canvas">
      <h1 data-route-heading class="route-heading">Mission graph</h1>
      <GraphCanvas ref="canvas" @expand="expand" @select="workspaceTab = 'inspect'" />
      <div class="toolbar">
        <v-select class="focus" :model-value="routeFocusId" :items="focusItems" item-title="name" item-value="id"
                  density="compact" variant="solo" flat hide-details prepend-inner-icon="mdi-target"
                  :title="graph.focusId ? 'Showing one program and its supply chain — pick Everything to see them all' : 'Showing every program'"
                  @update:model-value="setFocus" />
        <v-btn color="primary" prepend-icon="mdi-magnify" @click="focusSearch">Find in graph</v-btn>
        <v-menu :close-on-content-click="false" location="bottom end">
          <template #activator="{ props }"><v-btn v-bind="props" variant="tonal" prepend-icon="mdi-tune-variant">Graph options</v-btn></template>
          <v-card class="advanced-menu">
            <v-card-title class="text-subtitle-2">Graph options</v-card-title>
            <v-card-text>
              <v-select :model-value="ws.depth" @update:model-value="ws.setDepth" :items="[1,2,3,4,5,6]" label="Traversal depth" hint="Used when a program is selected" persistent-hint />
              <div class="option-label">Visible layers</div>
              <LayerToggles @change="reload" />
              <v-expansion-panels class="mt-3" variant="accordion">
                <v-expansion-panel title="Legend"><v-expansion-panel-text><Legend :embedded="true" /></v-expansion-panel-text></v-expansion-panel>
                <v-expansion-panel v-if="graph.lastCypher" title="Last query"><v-expansion-panel-text><CypherBlock :statement="graph.lastCypher.statement" :params="graph.lastCypher.params" /></v-expansion-panel-text></v-expansion-panel>
              </v-expansion-panels>
            </v-card-text>
          </v-card>
        </v-menu>
      </div>
      <div v-if="!graph.nodes.size && !graph.loading" class="empty">
        <v-btn color="primary" @click="reload">Load graph</v-btn>
      </div>
      <div class="canvas-overlays">
        <div class="search">
          <v-text-field ref="searchField" v-model="q" :loading="searching" label="Search the graph" placeholder="Name, UEI, CAGE…" hide-details clearable prepend-inner-icon="mdi-magnify" density="compact" variant="solo" flat @update:focused="open = $event" @keydown.esc="open = false" @keydown.enter="hits[0] && onPick(hits[0].id)" />
          <!-- mousedown.prevent keeps the field focused so a click here doesn't blur-close the list first -->
          <v-list v-if="open && hits.length" class="hits" density="compact" @mousedown.prevent>
            <v-list-item v-for="h in hits" :key="h.id" :title="h.name" :subtitle="[h.label, h.uei && `UEI ${h.uei}`].filter(Boolean).join(' · ')" @click="onPick(h.id)" />
          </v-list>
        </div>
        <div v-if="graph.focusIds.length" class="focus-title">
          <span>REPORT TRACE</span>
          <strong>{{ graph.reportFocusLabel || 'Selected risk indicator' }}</strong>
          <small>Loaded mission context remains visible; unrelated elements are recessed.</small>
          <small v-if="graph.focusUnavailableIds.length" class="focus-missing">{{ graph.focusUnavailableIds.length }} referenced element{{ graph.focusUnavailableIds.length === 1 ? '' : 's' }} unavailable in the loaded graph.</small>
          <div class="focus-links">
            <router-link :to="{ path: `/entities/${graph.focusVendorId}`, query: preservedQuery }">Vendor report</router-link>
            <router-link :to="{ name: 'vendor-comparison', query: { ...preservedQuery, left: graph.focusVendorId } }">Compare vendor</router-link>
            <a v-if="route.query.evidence" :href="String(route.query.evidence)" target="_blank" rel="noopener">Matching evidence</a>
            <span v-else>No matching evidence destination</span>
          </div>
        </div>
        <div v-if="graphError" class="graph-error" role="alert">
          <div><strong>{{ failedPreset ? 'Guided analysis could not finish.' : 'Graph context is partially unavailable.' }}</strong><span>{{ graphError }}</span></div>
          <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="retryFailure">{{ failedPreset ? 'Retry analysis' : 'Retry graph' }}</v-btn>
        </div>
        <div v-else-if="presetRunning" class="mission-progress" role="status">
          <v-progress-circular indeterminate size="18" width="2" />
          Running {{ route.query.mission || 'guided' }} analysis…
        </div>
        <div v-else-if="presetCompletion" class="mission-complete" role="status"
             :data-rehearsal-template="presetCompletion.template"
             :data-rehearsal-root="presetCompletion.root"
             :data-rehearsal-elements="presetCompletion.elements">
          <strong>{{ findingSummary.title }}</strong>
          <span>{{ findingSummary.detail }}</span>
          <button type="button" @click="workspaceTab = 'list'">{{ findingSummary.action }}</button>
        </div>
      </div>
      <div v-if="graph.truncated" class="truncation" role="status">
        This view reached its graph limit. Select one program or turn off optional layers to inspect a complete path.
      </div>
    </div>
    <div class="side">
      <v-tabs v-model="workspaceTab" grow density="compact" aria-label="Graph workspace panel">
        <v-tab value="inspect">Inspect</v-tab><v-tab value="list">Path list</v-tab><v-tab value="chat">Ask</v-tab>
      </v-tabs>
      <div class="workspace-pane">
        <div v-show="workspaceTab === 'inspect'" class="panel-fill">
          <Inspector v-if="graph.selected" @expand="expand" />
          <EdgeInspector v-else-if="graph.selectedEdge" />
          <div v-else class="hint"><strong>Select an item to inspect</strong><span>Choose a node or relationship on the canvas, or use Path list. Double-click a person or organization to expand it.</span></div>
        </div>
        <GraphFindingList v-show="workspaceTab === 'list'" :result-ids="guidedListIds" :result-key="presetCompletion?.key" @expand="expand" @inspect="workspaceTab = 'inspect'" />
        <div v-show="workspaceTab === 'chat'" class="panel-fill"><ChatRail /></div>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, qs } from '../api/client'
import GraphCanvas from '../components/GraphCanvas.vue'
import Inspector from '../components/Inspector.vue'
import EdgeInspector from '../components/EdgeInspector.vue'
import ChatRail from '../components/ChatRail.vue'
import Legend from '../components/Legend.vue'
import LayerToggles from '../components/LayerToggles.vue'
import CypherBlock from '../components/CypherBlock.vue'
import GraphFindingList from '../components/GraphFindingList.vue'
import {
  missionAnalysisKey,
  resolveMissionAnalysis,
  retainMissionCompletion,
  shouldRunMissionAnalysis,
  extendMissionResultIds,
  type MissionAnalysisCompletion,
} from '../missionAnalysisState'
import { createRequestGate } from '../navigationState'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
const graph = useGraph(); const ws = useWorkspace()
const navigationRequests = createRequestGate()
const route = useRoute()
const router = useRouter()
const q = ref(''); const hits = ref<any[]>([]); const searching = ref(false); const open = ref(false); const graphError = ref('')
const searchField = ref<any>(); const workspaceTab = ref<'inspect' | 'list' | 'chat'>('inspect'); const failedPreset = ref(false)
// The programs the canvas can be narrowed to. The store keeps this current from live
// deltas, so a program added while this view is open shows up here without a reload.
const focusItems = computed(() => [{ id: null, name: 'Everything' }, ...graph.programs])
const routeFocusId = computed(() => String(route.query.root_id || '') || null)
const presetRunning = ref(false)
const presetCompletion = ref<MissionAnalysisCompletion | null>(null)
const expandedResultIds = ref<string[]>([])
const guidedListIds = computed(() => [...new Set([...(presetCompletion.value?.elementIds || []), ...expandedResultIds.value])])
const findingSummary = computed(() => {
  const template = presetCompletion.value?.template || ''
  const program = graph.focusLabel || graph.programs.find(p => p.id === presetCompletion.value?.root)?.name || 'selected program'
  const affected = presetCompletion.value?.affected || []
  const vendor = affected.length ? `${affected[0].name}${affected.length > 1 ? ` and ${affected.length - 1} more` : ''}` : 'the returned path'
  const descriptions: Record<string, string> = {
    manufactures_in: `A manufacturing path involving ${vendor} matched the selected country and tier criteria.`,
    foreign_parent: `${vendor} has a control path outside the selected home country.`,
    sole_source: `${vendor} appears on a sole-source supply path.`,
  }
  return { title: `${program}: ${template.replace(/_/g, ' ') || 'guided'} finding`, detail: `${descriptions[template] || `The analysis returned ${presetCompletion.value?.elements || 0} graph elements.`} ${presetCompletion.value?.hasSimulated ? 'Includes simulated scenario data.' : 'Uses live or curated graph data.'}`, action: 'Review the finding path and evidence' }
})
const preservedQuery = computed(() => ({
  root_id: String(route.query.root_id || graph.focusId || '') || undefined,
  vendor: String(route.query.vendor || graph.focusVendorId || '') || undefined,
  focus: route.query.focus,
  finding: route.query.finding,
  family: route.query.family,
  evidence: route.query.evidence,
}))
let t: any
let searchRequest = 0
const missionTemplates: Record<string, () => Record<string, string | number>> = {
  manufactures_in: () => ({ root_id: missionRootId(), country: String(route.query.country || 'CN'), min_tier: Number(route.query.min_tier || 2) }),
  foreign_parent: () => ({ root_id: missionRootId(), home_country: String(route.query.home_country || 'US') }),
  sole_source: () => ({ root_id: missionRootId() }),
}
function missionRootId() { return String(route.query.root_id || graph.focusId || '') }
function focusSearch() { searchField.value?.focus() }
// A plain text field, not an autocomplete: the typed text — and the canvas filter it drives — must survive blur.
watch(q, (v) => {
  const request = ++searchRequest
  graph.setFilter(v && v.length >= 2 ? v : '')
  clearTimeout(t)
  if (!v || v.length < 2) { hits.value = []; return }
  t = setTimeout(async () => {
    searching.value = true
    try {
      const results = (await api.get(`/api/graph/search?${qs({ q: v, limit: 10 })}`)).results
      if (request === searchRequest && q.value === v) { hits.value = results; open.value = true }
    } finally { if (request === searchRequest) searching.value = false }
  }, 250)
})
// A search hit is already on the canvas when nothing is filtered out; pull it in only if it isn't.
async function onPick(id: string) {
  searchRequest++; open.value = false; q.value = ''; workspaceTab.value = 'inspect'
  if (!graph.nodes.has(id) && !await graph.loadNeighbourhood(id, 1, ws.ws.layers)) return
  if (graph.nodes.has(id)) graph.select(id)
}
async function setFocus(id: string | null) {
  const query = { ...route.query }
  presetRunning.value = false
  graphError.value = ''
  try {
    await router.replace({ query: { ...query, root_id: id || undefined } })
  } catch (cause) {
    graphError.value = cause instanceof Error ? cause.message : 'The selected program could not be opened.'
  }
}
async function reload() {
  await applyRouteFocus(true)
}
async function retryFailure() {
  if (failedPreset.value && missionTemplates[String(route.query.template || '')]) await runPreset(navigationRequests.begin())
  else await reload()
}
async function expand(id: string) {
  try {
    const applied = await graph.loadNeighbourhood(id, 1, ws.ws.layers)
    if (applied && presetCompletion.value) {
      expandedResultIds.value = extendMissionResultIds(guidedListIds.value, id, graph.edgeList)
    }
  } catch (cause) {
    graphError.value = cause instanceof Error ? cause.message : 'The selected graph item could not be expanded.'
  }
}
async function applyRouteFocus(forceGraph = false) {
  const request = navigationRequests.begin()
  graph.invalidatePendingRequests()
  const query = { ...route.query }
  const template = String(query.template || '')
  const missionKey = missionAnalysisKey(query)
  presetCompletion.value = retainMissionCompletion(presetCompletion.value, missionKey, Boolean(missionTemplates[template]))
  graph.prepareScope(String(query.root_id || '') || null)
  presetRunning.value = false
  failedPreset.value = false
  graphError.value = ''
  if (!ws.loaded) await ws.load()
  if (!navigationRequests.isCurrent(request)) return
  const ids = String(query.focus || '').split(',').filter(Boolean)
  const vendor = String(query.vendor || '')
  const missionRoot = String(query.root_id || '')
  if (vendor) {
    // A report can be scoped to a mission other than the workspace's retained focus.
    // Establish the incoming mission before loading the vendor trace so evidence is
    // never resolved against the previous program (or an unscoped fresh session).
    if (missionRoot && (forceGraph || graph.focusId !== missionRoot || !graph.nodes.size)) {
      try {
        const applied = await graph.focus(missionRoot, graph.programs.find(program => program.id === missionRoot)?.name || null, ws.depth, ws.ws.layers)
        if (!applied || !navigationRequests.isCurrent(request)) return
      } catch (cause) {
        if (!navigationRequests.isCurrent(request)) return
        graphError.value = cause instanceof Error ? cause.message : 'The mission program graph could not be loaded.'
        return
      }
    } else if (graph.focusId && !graph.nodes.has(graph.focusId)) {
      const applied = await graph.loadNeighbourhood(graph.focusId, ws.depth, ws.ws.layers)
      if (!applied || !navigationRequests.isCurrent(request)) return
    }
    // A report trace may reference people, locations, or evidence hidden by the normal workspace
    // layers. Merge those elements for the trace without changing the user's layer preferences.
    try {
      const applied = await graph.loadNeighbourhood(vendor, Math.max(2, ws.depth), {
        ...ws.ws.layers,
        people: true,
        countries: true,
        artifacts: true,
        categories: true,
        sources: true,
        claims: true,
      })
      if (!applied || !navigationRequests.isCurrent(request)) return
    } catch (cause) {
      if (!navigationRequests.isCurrent(request)) return
      graphError.value = cause instanceof Error ? cause.message : 'The report trace could not be loaded.'
    }
    graph.setFocus(ids, String(query.finding || 'Selected risk indicator'), vendor, String(query.family || ''))
  } else {
    graph.clearFocus()
    if (missionRoot && (forceGraph || graph.focusId !== missionRoot || !graph.nodes.size)) {
      try {
        const applied = await graph.focus(missionRoot, graph.programs.find(program => program.id === missionRoot)?.name || null, ws.depth, ws.ws.layers)
        if (!applied || !navigationRequests.isCurrent(request)) return
      } catch (cause) {
        if (!navigationRequests.isCurrent(request)) return
        graphError.value = cause instanceof Error ? cause.message : 'The mission program graph could not be loaded.'
        return
      }
    } else if (forceGraph || !graph.nodes.size) {
      try {
        const applied = await graph.loadAll(ws.ws.layers)
        if (!applied || !navigationRequests.isCurrent(request)) return
      } catch (cause) {
        if (!navigationRequests.isCurrent(request)) return
        graphError.value = cause instanceof Error ? cause.message : 'The graph could not be loaded.'
        return
      }
    }
  }
  if (!navigationRequests.isCurrent(request)) return
  if (shouldRunMissionAnalysis(presetCompletion.value, missionKey, Boolean(missionTemplates[template]))) {
    if (!missionRootId()) {
      graphError.value = 'Select a mission program before running this analysis.'
      return
    }
    await runPreset(request)
  }
}
async function runPreset(request: number) {
  const query = { ...route.query }; const template = String(query.template || ''); const missionKey = missionAnalysisKey(query); const missionRoot = missionRootId()
  presetRunning.value = true; failedPreset.value = false; graphError.value = ''
  await nextTick()
  try {
    const result = await graph.runTemplate(template, missionTemplates[template]())
    if (!navigationRequests.isCurrent(request) || result.stale) return
    const outcome = resolveMissionAnalysis(result, missionKey, template, missionRoot, String(query.mission || 'Guided'))
    presetCompletion.value = outcome.completion; graphError.value = outcome.error; failedPreset.value = !outcome.completion
  } catch (cause) {
    if (navigationRequests.isCurrent(request)) { graphError.value = cause instanceof Error ? cause.message : `${query.mission || 'Guided'} analysis could not be completed.`; failedPreset.value = true }
  } finally { if (navigationRequests.isCurrent(request)) presetRunning.value = false }
}
onMounted(async () => { await applyRouteFocus(); graph.loadPrograms() })
watch(() => route.fullPath, () => applyRouteFocus())
watch(() => presetCompletion.value?.key, () => { expandedResultIds.value = [] })
// Depth only shapes a focused view; the whole graph is not walked from a root.
watch(() => ws.depth, () => { if (graph.focusId) reload() })
</script>
<style scoped>
.explorer { display: grid; grid-template-columns: minmax(0, 1fr) 380px; height: calc(100dvh - 48px); min-width: 0; }
.canvas { position: relative; min-width: 0; min-height: 0; }
.route-heading { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.side { display: grid; grid-template-rows: auto minmax(0,1fr); border-left: 1px solid rgba(128,128,128,.2); min-width: 0; min-height: 0; }
.workspace-pane { overflow: hidden; min-width: 0; min-height: 0; }
.panel-fill { height:100%; min-height:0; }
.hint { padding: 20px; opacity: .7; font-size: 13px; display:grid; gap:5px; }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: .8; }
.toolbar { position: absolute; top: 8px; left: 12px; right: 54px; z-index: 5; display: flex; align-items: center; gap: 8px; min-width: 0; max-width: calc(100% - 66px); }
.focus { flex: 0 1 230px; min-width: 150px; }
.advanced-menu { width: min(520px, 90vw); }
.option-label { margin: 12px 0 4px; font-size: 12px; font-weight: 700; }
.canvas-overlays { position: absolute; top: 52px; left: 12px; z-index: 7; display: grid; gap: 8px; width: 360px; }
.search { position: relative; z-index: 1; width: 100%; }
.hits { position: absolute; top: 100%; left: 0; right: 0; z-index: 2; margin-top: 4px; max-height: 320px; overflow: auto; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,.25); }
.focus-title { display: grid; max-height: 180px; overflow: auto; padding: 9px 12px; border-left: 4px solid #006b62; background: rgba(245,248,240,.94); color: #173b37; box-shadow: 0 2px 10px rgba(25,45,40,.12); }
.focus-title span { color: #006b62; font-size: 9px; font-weight: 800; letter-spacing: .14em; }
.focus-title strong { font-size: 13px; line-height: 1.25; }
.focus-title small { opacity: .68; font-size: 10px; margin-top: 2px; }
.focus-title .focus-missing { margin-top: 6px; color: #8a321f; font-weight: 700; opacity: 1; }
.focus-links { display: flex; gap: 10px; align-items: center; margin-top: 7px; padding-top: 6px; border-top: 1px solid rgba(0,107,98,.2); font-size: 11px; }
.focus-links a { color: #006b62; font-weight: 750; text-decoration: none; }
.focus-links span { opacity: .58; }
.truncation { position:absolute; right:56px; bottom:12px; max-width:420px; padding:7px 10px; background:rgba(var(--v-theme-surface),.94); border-left:4px solid #f59e0b; font-size:12px; }
.graph-error { max-width:520px;display:flex;align-items:center;gap:12px;padding:9px 12px;border-left:4px solid #c04b2d;background:#fae6d8;color:#5b281b;box-shadow:0 2px 10px rgba(45,25,20,.16);font-size:11px; }
.graph-error div,.graph-error strong,.graph-error span { display:block; }
.graph-error span { margin-top:2px;opacity:.8; }
.mission-progress { display:flex;align-items:center;gap:9px;padding:9px 12px;border-left:4px solid #006b62;background:rgba(225,239,234,.96);color:#173b37;box-shadow:0 2px 10px rgba(25,45,40,.12);font-size:12px;font-weight:700; }
.mission-complete { max-width:520px;display:grid;padding:9px 12px;border-left:4px solid #006b62;background:rgba(215,237,229,.96);color:#173b37;box-shadow:0 2px 10px rgba(25,45,40,.12);font-size:12px; }
.mission-complete button { justify-self:start; border:0; background:none; color:#006b62; font-weight:800; padding:5px 0 0; cursor:pointer; }
@media (max-width: 900px) {
  .explorer { display: grid; grid-template-columns: 1fr; grid-template-rows: minmax(420px, 58dvh) minmax(480px, 72dvh); height: auto; min-height: calc(100dvh - 48px); }
  .side { grid-template-rows: auto minmax(440px, 1fr); border-left: 0; border-top: 1px solid rgba(128,128,128,.25); }
  .toolbar { left: 8px; right: 50px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: calc(100% - 58px); }
  .focus { grid-column: 1 / -1; width: 100%; min-width: 0; }
  .toolbar :deep(.v-btn) { min-width: 0; }
  .canvas-overlays { top: 100px; left: 8px; width: calc(100% - 68px); }
  .notes { display: none; }
}
@media (max-width: 420px) {
  .explorer { grid-template-rows: minmax(390px, 56dvh) minmax(480px, 76dvh); }
}
</style>
