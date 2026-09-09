<template>
  <div class="canvas-wrap">
    <div ref="el" class="cy"></div>
    <div v-if="graph.loading" class="loading"><v-progress-circular indeterminate size="28" /></div>
    <aside v-if="active && ws.ws.layers.indirect_orgs !== false && (affiliations.groups.length || affiliations.unconnected.length)" class="affiliations" aria-label="Affiliation groups">
      <v-btn size="small" variant="tonal" :aria-expanded="panelOpen" @click="panelOpen = !panelOpen">Affiliations · {{ affiliations.groups.length }} groups</v-btn>
      <div v-if="panelOpen" class="affiliation-panel">
        <label class="group-switch"><input type="checkbox" v-model="grouped" /> Group affiliations</label>
        <p>Expand a group to see its recorded connections. These are affiliations, not supplier relationships. Significant risk findings stay visible.</p>
        <input v-model="affiliationQuery" class="affiliation-search" type="search" aria-label="Search affiliations" placeholder="Find an organization or group…" />
        <div class="affiliation-results">
          <section v-for="group in filteredGroups" :key="group.id" class="affiliation-entry">
            <button class="group-button" :aria-expanded="expandedGroups.has(group.id)" @click="toggleGroup(group.id)">
              <strong>{{ group.title }} ({{ group.members.length }})</strong><span>{{ group.anchorName }}</span>
              <span>{{ expandedGroups.has(group.id) ? 'Collapse' : 'Expand' }}</span>
            </button>
            <ul v-if="expandedGroups.has(group.id) || affiliationQuery.trim()">
              <li v-for="member in matchingMembers(group)" :key="member.id"><button @click="inspectAffiliation(member.id)">{{ member.name }}</button></li>
            </ul>
          </section>
          <h3>Unconnected in this view ({{ affiliations.unconnected.length }})</h3>
          <p>No recorded path to a program’s supply chain in the loaded graph. Other layers or additional data may provide a connection.</p>
          <ul><li v-for="member in filteredUnconnected.slice(0, 50)" :key="member.id"><button @click="inspectAffiliation(member.id)">{{ member.name }}</button></li></ul>
          <p v-if="filteredUnconnected.length > 50">Showing 50 of {{ filteredUnconnected.length }}. Search to narrow the list.</p>
          <p v-if="!filteredGroups.length && !filteredUnconnected.length">No matching organizations.</p>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, nextTick, ref, watch } from 'vue'
import cytoscape, { type Core } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import cola from 'cytoscape-cola'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { applyStyleOps, clearStyleOps } from '../styles/styleOps'
import { nodeSize, supplierTiers } from '../styles/nodeSize'
import { edgeColor, fillFor, glyphScaleFor, glyphYFor, iconFor, shapeFor } from '../styles/nodeTypes'
import { haloFor, isThin } from '../styles/risk'
import { hiddenNodeIds, layerData } from '../stores/graphLayers'
import { affiliationGroups, affiliationVisibility, type AffiliationGroup } from '../affiliations'

cytoscape.use(fcose)
cytoscape.use(cola)
const props = withDefaults(defineProps<{ active?: boolean }>(), { active: true })
const el = ref<HTMLElement>()
const graph = useGraph()
const ws = useWorkspace()
const grouped = ref(true)
const panelOpen = ref(false)
const affiliationQuery = ref('')
const expandedGroups = ref(new Set<string>())
const groupingEnabled = computed(() => grouped.value && ws.ws.layers.indirect_orgs !== false)
const affiliations = computed(() => affiliationGroups(graph.nodeList, graph.edgeList, graph.focusId ? [graph.focusId] : []))
const affiliationMatch = (name: string) => fold(name).includes(fold(affiliationQuery.value.trim()))
const filteredGroups = computed(() => affiliations.value.groups.filter(g => affiliationMatch(`${g.anchorName} ${g.title}`) || g.members.some(m => affiliationMatch(m.name))))
const filteredUnconnected = computed(() => affiliations.value.unconnected.filter(n => affiliationMatch(n.name)))
function matchingMembers(group: AffiliationGroup) {
  return group.members.filter(m => affiliationMatch(m.name) || affiliationMatch(`${group.anchorName} ${group.title}`))
}
function toggleGroup(id: string) {
  grouped.value = true
  const next = new Set(expandedGroups.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  expandedGroups.value = next
}
async function inspectAffiliation(id: string) {
  panelOpen.value = false
  graph.select(id)
  await nextTick()
  if (!cy) return
  const node = cy.getElementById(id)
  if (node.empty()) return
  cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1) }, { duration: 250 })
}
let cy: Core | null = null
let ro: ResizeObserver | null = null
let restoringView = false
let holdLayout = false
let pendingEntityFocus: string | null = null
let staticLayout: any = null
let renderedScope = ''
const scopeKey = () => graph.focusId || ''
let savedView: { scope: string; zoom: number; pan: { x: number; y: number }; positions: Map<string, { x: number; y: number }> } | null = null
const emit = defineEmits<{ (e: 'expand', id: string): void; (e: 'report', id: string): void; (e: 'select'): void }>()


function badgeFor(n: any) {
  const p = n.props || {}
  const bits: string[] = []
  if (p.simulated) bits.push('SIM')
  if (p.flagged) bits.push('⚑')
  // The number, not just the halo: two nodes in the same band still rank against each
  // other, and a thin score is marked so nobody acts on 100/2-of-7 as if it were settled.
  // Both are risk emphasis, so both answer to the same switch (stores/workspace.ts).
  if (ws.riskEmphasis && p.risk_score != null && p.risk_band && p.risk_band !== 'low') {
    bits.push(`${p.risk_score}${isThin(p.risk_confidence) ? '?' : ''}`)
  }
  return bits.join(' ')
}

/** Risk halo data for a node, or nulls when it is unscored — unscored gets no ink at all.
 *
 *  With risk emphasis off — the default — no node gets a halo whatever it scored. That is
 *  the ordinary picture of a supply chain: a few hundred discs, none of them saying which
 *  one is the problem. Every other way in is still open (the Risk tab, a score in the
 *  properties card, "colour by risk"); what the switch governs is whether the canvas
 *  volunteers it. */
function haloData(n: any, theme: 'light' | 'dark') {
  const halo = ws.riskEmphasis ? haloFor(n.props?.risk_band, theme) : null
  return { haloColor: halo?.color ?? '#000000', haloPad: halo?.padding ?? 0, haloOpacity: halo?.opacity ?? 0 }
}

function styleSheet(): any[] {
  const dark = ws.theme === 'dark'
  const text = dark ? '#e5e7eb' : '#111827'
  const outline = dark ? '#0e1013' : '#ffffff'
  return [
    // The glyph is sized as a share of the node, so it follows supplier tier and the simulated
    // screen-space rescale on its own; `fit: none` is what makes the percentages authoritative.
    { selector: 'node', style: { 'background-color': 'data(baseColor)', shape: 'data(shape)', width: 'data(size)', height: 'data(size)', 'background-image': 'data(icon)', 'background-fit': 'none', 'background-width': 'data(glyphScale)', 'background-height': 'data(glyphScale)', 'background-position-y': 'data(glyphY)', 'background-image-opacity': 0.95, label: 'data(name)', color: text, 'font-size': 10, 'text-wrap': 'ellipsis', 'text-max-width': 120, 'text-valign': 'bottom', 'text-margin-y': 4, 'text-outline-color': outline, 'text-outline-width': 2, 'border-width': 1.5, 'border-color': dark ? '#374151' : '#cbd5e1', 'overlay-padding': 4 } },
    // Drawn under the node, so risk never competes with the border, which already carries
    // root, selection, simulated, freshness and style-op state.
    { selector: 'node[haloOpacity > 0]', style: { 'underlay-color': 'data(haloColor)', 'underlay-padding': 'data(haloPad)', 'underlay-opacity': 'data(haloOpacity)' } },
    { selector: 'node[?isRoot]', style: { 'border-width': 3, 'border-color': dark ? '#60a5fa' : '#1d4ed8', 'font-weight': 'bold', 'font-size': 12 } },
    { selector: 'node[badge != ""]', style: { label: (e: any) => `${e.data('name')}\n${e.data('badge')}`, 'text-wrap': 'wrap' } },
    { selector: 'node[?simulated]', style: { 'border-style': 'dashed', 'border-color': dark ? '#facc15' : '#ca8a04', 'border-width': 2 } },
    { selector: 'edge', style: { width: 1.4, 'line-color': 'data(color)', 'target-arrow-color': 'data(color)', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: dark ? '#9ca3af' : '#4b5563', 'text-rotation': 'autorotate', 'text-outline-color': outline, 'text-outline-width': 2, 'text-background-opacity': 0 } },
    { selector: 'edge[type = "HELD_ROLE"]', style: { 'line-style': 'dashed' } },
    { selector: 'edge[type = "MEMBER_OF"], edge[type = "TRANSACTS_WITH"], edge[type = "LOBBIES"], edge[type = "DONATED_TO"]', style: { 'line-style': 'dashed', 'line-dash-pattern': [2, 3] } },
    { selector: 'edge[?simulated]', style: { 'line-style': 'dotted' } },
    { selector: 'node:selected', style: { 'border-width': 4, 'border-color': dark ? '#f472b6' : '#be185d' } },
    { selector: 'edge:selected', style: { width: 3.5, 'line-color': dark ? '#f472b6' : '#be185d', 'target-arrow-color': dark ? '#f472b6' : '#be185d', 'z-index': 20 } },
    // style ops
    { selector: '.op-fill', style: { 'background-color': 'data(opFill)' } },
    { selector: 'node.op-stroke', style: { 'border-color': 'data(opStroke)', 'border-width': 4 } },
    { selector: 'edge.op-stroke', style: { 'line-color': 'data(opStroke)', 'target-arrow-color': 'data(opStroke)', width: 3 } },
    { selector: 'edge.op-highlight', style: { width: 3.5, 'z-index': 10 } },
    { selector: 'node.op-highlight', style: { 'border-width': 4 } },
    { selector: '.op-badge', style: { label: (e: any) => `${e.data('name')}\n[${e.data('opBadge')}]`, 'text-wrap': 'wrap' } },
    { selector: '.op-size', style: { width: 'data(opSize)', height: 'data(opSize)' } },
    { selector: '.op-shape', style: { shape: 'data(opShape)' } },
    { selector: '.op-dashed', style: { 'line-style': 'dashed', 'border-style': 'dashed' } },
    { selector: '.op-dim', style: { opacity: 0.18 } },
    { selector: '.op-hide', style: { display: 'none' } },
    { selector: '.layer-hide', style: { display: 'none' } },
    { selector: '.affiliation-hide', style: { display: 'none' } },
    { selector: 'node[?affiliationGroup]', style: { shape: 'round-rectangle', width: 110, height: 44, 'background-image': 'none', 'background-color': dark ? '#30334f' : '#e5e7f5', 'border-color': dark ? '#b4b9ef' : '#656ea4', 'border-style': 'dashed', label: 'data(name)', 'text-valign': 'center', 'text-margin-y': 0, 'text-wrap': 'wrap', 'text-max-width': 106, 'font-size': 10 } },
    { selector: 'edge[?affiliationGroup]', style: { 'line-style': 'dotted', 'target-arrow-shape': 'none', width: 1, opacity: 0.65 } },
    // a node or edge that arrived from a live change — held for a few seconds, then released
    { selector: 'node.fresh', style: { 'border-width': 5, 'border-color': dark ? '#34d399' : '#059669', 'z-index': 30 } },
    { selector: 'edge.fresh', style: { width: 3.4, 'line-color': dark ? '#34d399' : '#059669', 'target-arrow-color': dark ? '#34d399' : '#059669', 'z-index': 30 } },
    // search-bar filter: matches stay bright, everything else recedes
    { selector: '.q-dim', style: { opacity: 0.12, 'z-index': 0 } },
    { selector: 'node.q-match', style: { 'border-width': 3, 'border-color': dark ? '#fbbf24' : '#d97706', 'z-index': 20 } },
    { selector: 'edge.q-match', style: { width: 2.2, 'z-index': 20 } },
    // the route behind a risk finding — the ownership chain, the person a proximity hop went
    // through. Held until the user picks another dimension or clears it.
    { selector: 'node.trace', style: { 'border-width': 4, 'border-color': dark ? '#f472b6' : '#be185d', 'z-index': 25 } },
    { selector: 'edge.trace', style: { width: 3.2, 'line-color': dark ? '#f472b6' : '#be185d', 'target-arrow-color': dark ? '#f472b6' : '#be185d', 'z-index': 25 } },
  ]
}

function toElements() {
  const root = graph.focusId
  // Supplier tier drives entity size (see styles/nodeSize.ts); it is resolved over the edge list, so
  // a node grows or shrinks as edges arrive — sync() re-applies data() for nodes already drawn.
  const tiers = supplierTiers(graph.edgeList, graph.nodeList)
  const nodes = graph.nodeList.map(n => {
    const tier = tiers.get(n.id)
    return { group: 'nodes', data: { id: n.id, name: n.name, label: n.label, ...layerData(n), baseColor: fillFor(n, ws.theme), shape: shapeFor(n), icon: iconFor(n), glyphScale: glyphScaleFor(n), glyphY: glyphYFor(n), size: nodeSize(n, tier), tier, isRoot: n.id === root, simulated: !!n.props?.simulated, badge: badgeFor(n), ...haloData(n, ws.theme) } }
  })
  const edges = graph.edgeList.map(e => ({ group: 'edges', data: { id: e.id, source: e.source, target: e.target, type: e.type, color: edgeColor(e.type, ws.theme), simulated: !!e.props?.simulated, label: e.type === 'SUPPLIES' && e.props?.tier ? `T${e.props.tier}${e.props.sole_source ? ' · sole' : ''}` : e.type === 'HELD_ROLE' ? (e.props?.title || '').slice(0, 18) : e.type === 'OWNS' && e.props?.pct ? `${e.props.pct}%` : '' } }))
  const summaries = groupingEnabled.value ? affiliations.value.groups.flatMap(g => [
    { group: 'nodes', data: { id: g.id, affiliationGroup: true, name: `${g.title} (${g.members.length})\n${expandedGroups.value.has(g.id) ? '− Collapse' : '+ Expand'}`, size: 44, baseColor: '#7f86af', shape: 'round-rectangle', icon: '', glyphScale: 0, glyphY: 50, badge: '', haloOpacity: 0 } },
    { group: 'edges', data: { id: `${g.id}:summary`, source: g.anchorId, target: g.id, affiliationGroup: true, type: 'AFFILIATION_SUMMARY', color: '#939bc6', label: '' } },
  ]) : []
  return [...nodes, ...edges, ...summaries]
}

function sync() {
  if (!cy || !props.active) return
  if (renderedScope !== scopeKey()) holdLayout = false
  renderedScope = scopeKey()
  const existing = new Set(cy.elements().map(e => e.id()))
  const wanted = toElements()
  const wantedIds = new Set(wanted.map(w => w.data.id))
  cy.elements().filter(e => !wantedIds.has(e.id())).remove()
  const fresh = wanted.filter(w => !existing.has(w.data.id))
  wanted.filter(w => existing.has(w.data.id)).forEach(w => cy!.getElementById(w.data.id).data(w.data))
  if (fresh.length) {
    cy.add(fresh as any)
    restyle()
    if (existing.size === 0 && !restoringView) layout(true)
    else { seedNearNeighbours(fresh.filter(w => w.group === 'nodes').map(w => w.data.id)); startLive() }
  } else if (cy.elements().length === 0) {
    stopLive()
  }
  restyle()
  if (!restoringView) focusPendingEntity()
}
function restyle() {
  if (!cy || !props.active) return
  clearStyleOps(cy)
  applyStyleOps(cy, graph.styleOps, ws.theme)
  applyFilter()
  applyLayers()
  applyTrace()
  markFresh()
  // Style ops and layer toggles change which components are drawn. Only adjust a simulation that is
  // already running: while the static layout is in flight there is none, and it starts one itself.
  if (live.length) startLive()
}

// Layer toggles gate what the server sends, but nodes can arrive by other routes (chat results,
// generated Cypher, an API that predates the flag). The canvas enforces the toggles too, so an
// unchecked layer is never drawn. Edges to hidden nodes are hidden by Cytoscape automatically.
// The server names each node's layer (graphio.layer_of); the fallback mirrors it for nodes from
// a route that predates the field. Artifacts split by kind: registry entries and source records
// are "sources", documents (filings, news, awards, web pages) are "artifacts".
// Entities have no layer and are always fetched, so an organization that is in the graph only
// through a hidden person would be left floating; graphLayers.hiddenNodeIds prunes those, and
// with the "indirect orgs" toggle off it prunes every organization no chain of contracts or
// ownership joins to a program or the root — affiliation edges (lobbying, memberships) do not
// count as that chain. A node scored over 20 that reaches a supplier survives all of it, a person
// over an off people layer included; the server sends those people whatever the layer says.
function applyLayers() {
  if (!cy) return
  const hidden = hiddenNodeIds(graph.nodeList, graph.edgeList, ws.ws.layers || {}, graph.focusId ? [graph.focusId] : [])
  const reveal = new Set([...graph.highlightIds, ...(graph.selectedId ? [graph.selectedId] : [])])
  const selectedEdge = graph.selectedEdgeId && graph.edges.get(graph.selectedEdgeId)
  if (selectedEdge) { reveal.add(selectedEdge.source); reveal.add(selectedEdge.target) }
  if (graph.filter.trim()) {
    const match = matcher(graph.filter)
    graph.nodeList.filter(match).forEach(n => reveal.add(n.id))
  }
  const visibility = groupingEnabled.value ? affiliationVisibility(affiliations.value, expandedGroups.value, reveal) : null
  cy.nodes().forEach(n => {
    n.toggleClass('layer-hide', hidden.has(n.id()) && !visibility?.visible.has(n.id()))
    n.toggleClass('affiliation-hide', !!visibility?.hidden.has(n.id()))
  })
}

// Layout strategy: fcose arranges a fresh canvas (it is the better static layout), then cola takes
// over in infinite mode — a force simulation that keeps running, so dragging a node pulls its
// neighbours through the edges and the rest of the graph relaxes, the way d3-force does in Neo4j
// Browser. Cola pins the grabbed node to the pointer itself; nothing here handles drag events.
//
// Cola models the canvas as a stress system: every pair of nodes is given an ideal separation taken
// from the shortest path between them, and a pair with no path at all is given Number.MAX_VALUE.
// One stranded node is therefore enough to make the whole simulation diverge — it is pushed towards
// a separation of 1e308, it drags its neighbours after it, and nothing ever comes to rest. Nodes get
// stranded routinely: a layer toggle that hides people leaves their organizations edgeless, and a
// subgraph can simply arrive without the edge that would join it. So the live layout runs one
// simulation per connected component of what is actually drawn, where every distance is finite. A
// node on its own has nothing to relax against and stays where the static layout put it.
let live: any[] = []
let liveKey = ''
function stopLive() {
  live.forEach(l => { try { l.stop() } catch {} })
  live = []
  liveKey = ''
}
function liveGroups() {
  if (!cy) return []
  return cy.elements().filter(e => e.visible()).components().filter(c => c.nodes().length > 1)
}
/** Restart the simulations when the drawn components change; `force` also picks up moved nodes. */
function startLive(force = false) {
  if (!cy) return
  const groups = liveGroups()
  const key = groups.map(g => g.map(e => e.id()).sort().join(',')).join('|')
  if (!force && live.length && key === liveKey) return
  stopLive()
  if (!props.active || restoringView || holdLayout) return
  if (!groups.length) return
  liveKey = key
  live = groups.map(group => {
    const l = group.layout({
      name: 'cola', infinite: true, fit: false, randomize: false, animate: true,
      edgeLength: 115, nodeSpacing: () => 26, avoidOverlap: true, convergenceThreshold: 0.02,
    } as any)
    l.run()
    return l
  })
}
// Nodes added to a running canvas would otherwise appear at the origin and fly across it; drop
// each one next to a neighbour that already has a position and let the simulation settle it.
// A node with no neighbour on the canvas — a program added from chat before anything supplies it —
// has nothing to anchor to, so it goes where the user is looking rather than at the origin.
function seedNearNeighbours(ids: string[]) {
  if (!cy) return
  const fresh = new Set(ids)
  const ext = cy.extent()
  const mid = { x: (ext.x1 + ext.x2) / 2, y: (ext.y1 + ext.y2) / 2 }
  const spread = Math.min(ext.w, ext.h) / 4
  for (const id of ids) {
    const n = cy.getElementById(id)
    const anchor = n.neighborhood('node').filter(m => !fresh.has(m.id()))[0]
    const p = anchor ? anchor.position() : mid
    const jitter = anchor ? 80 : spread
    n.position({ x: p.x + (Math.random() - 0.5) * jitter, y: p.y + (Math.random() - 0.5) * jitter })
  }
}

// What a live change touched, marked on the canvas and — if it landed off-screen — brought into view.
// Nothing here reloads: the delta already carried the elements.
function freshElements() {
  if (!cy) return null
  const eles = cy.collection(graph.fresh.map(id => cy!.getElementById(id)).filter(e => e && e.nonempty()) as any)
  return eles.nonempty() ? eles : null
}
function markFresh() {
  if (!cy) return
  cy.elements().removeClass('fresh')
  freshElements()?.addClass('fresh')
}
function revealFresh() {
  if (!props.active) return
  if (!cy) return
  markFresh()
  const eles = freshElements()
  if (!eles) return
  const visible = eles.nodes().filter(n => !n.hasClass('layer-hide'))
  if (visible.empty()) return
  const ext = cy.extent()
  const offscreen = visible.filter(n => { const p = n.position(); return p.x < ext.x1 || p.x > ext.x2 || p.y < ext.y1 || p.y > ext.y2 })
  if (offscreen.nonempty()) cy.animate({ center: { eles: visible }, duration: 350 })
}

/** Case-, accent- and punctuation-insensitive form: "Société L-3 Harris" → "societe l 3 harris". */
function fold(s: string) { return s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim() }
/** Everything searchable about a node, folded: name, label and every scalar prop (UEI, CAGE, aliases, country…). */
function haystack(n: any) {
  const parts = [n.name, n.label, ...Object.values(n.props || {}).filter(v => typeof v === 'string' || typeof v === 'number')]
  return ' ' + fold(parts.join(' ')) + ' '
}
/** Every typed word must appear somewhere, in any order; a run of words also matches with the spaces removed ("l3harris" ~ "L-3 Harris"). */
function matcher(query: string): ((n: any) => boolean) | null {
  const toks = fold(query).split(' ').filter(Boolean)
  if (!toks.length) return null
  const compact = toks.join('')
  return (n) => { const h = haystack(n); return toks.every(t => h.includes(t)) || h.replace(/ /g, '').includes(compact) }
}
/** Search-bar filter: dim nodes that don't match and edges that don't join two matches. Independent of chat style ops. */
function applyFilter() {
  if (!cy) return
  cy.elements().removeClass('q-dim q-match')
  const match = matcher(graph.filter)
  if (!match) return
  const hit = cy.nodes().filter(e => { const n = graph.nodes.get(e.id()); return !!n && match(n) })
  hit.addClass('q-match')
  cy.nodes().not(hit).addClass('q-dim')
  cy.edges().forEach(e => { e.addClass(e.source().hasClass('q-match') && e.target().hasClass('q-match') ? 'q-match' : 'q-dim') })
}
/** Mark the elements a risk dimension was computed from. Ids that are not on the canvas are
 *  simply absent — a trace is best-effort, never an error. */
function applyTrace() {
  if (!cy) return
  cy.elements().removeClass('trace')
  for (const id of graph.highlightIds) {
    const el = cy.getElementById(id)
    if (el && el.nonempty()) el.addClass('trace')
  }
}
function layout(fit = true) {
  holdLayout = false
  if (!cy || !props.active || cy.nodes().length === 0) return
  staticLayout?.stop()
  stopLive()
  // A fresh canvas has every node at the origin; fcose must randomise from there or it collapses to a line.
  const visible = cy.elements().filter(e => e.visible())
  if (!visible.nodes().length) return
  const l = visible.layout({ name: 'fcose', animate: true, animationDuration: 400, randomize: fit, fit, padding: 50, nodeRepulsion: () => 9000, idealEdgeLength: () => 120, quality: 'default' } as any)
  staticLayout = l
  l.one('layoutstop', () => { staticLayout = null; if (props.active && !restoringView) { startLive(); focusPendingEntity() } })
  l.run()
}
function fit() { if (cy) cy.fit(cy.elements().filter(e => e.visible()), 50) }

function focusPendingEntity() {
  if (!cy || !props.active || staticLayout || !pendingEntityFocus) return
  const target = cy.getElementById(pendingEntityFocus)
  if (!target.length) return
  pendingEntityFocus = null
  stopLive()
  holdLayout = true
  cy.elements().unselect()
  target.select()
  cy.stop(true, false)
  cy.animate({ center: { eles: target }, zoom: Math.max(cy.zoom(), 1.25), duration: 350 })
}

onMounted(() => {
  cy = cytoscape({ container: el.value!, style: styleSheet(), wheelSensitivity: 0.25, minZoom: 0.1, maxZoom: 4 })
  ;(window as any).__cy = cy
  cy.on('tap', 'node', (ev) => ev.target.data('affiliationGroup') ? toggleGroup(ev.target.id()) : graph.select(ev.target.id()))
  cy.on('tap', 'edge', (ev) => { if (!ev.target.data('affiliationGroup')) graph.selectEdge(ev.target.id()) })
  cy.on('tap', (ev) => { if (ev.target === cy) { graph.select(null); graph.selectEdge(null) } })
  cy.on('dbltap', 'node', (ev) => { const n = graph.nodes.get(ev.target.id()); if (n && (n.label === 'Entity' || n.label === 'Person')) emit('expand', ev.target.id()) })
  cy.on('grab', 'node', () => { holdLayout = false; startLive(true) })
  sync()
  // The side panel is drag-resizable, so the container changes width without a window
  // resize event — cytoscape would keep drawing to the old box until the next one.
  ro = new ResizeObserver(() => cy?.resize())
  ro.observe(el.value!)
})
onBeforeUnmount(() => { stopLive(); ro?.disconnect(); staticLayout?.stop(); cy?.destroy() })
watch(() => props.active, async active => {
  if (!cy) return
  if (!active) {
    pendingEntityFocus = null
    stopLive()
    staticLayout?.stop()
    cy.stop(true, false)
    savedView = { scope: renderedScope, zoom: cy.zoom(), pan: { ...cy.pan() },
      positions: new Map(cy.nodes().map(node => [node.id(), { ...node.position() }])) }
    return
  }
  await nextTick()
  if (!cy || !props.active) return
  pendingEntityFocus = graph.selected?.label === 'Entity' ? graph.selected.id : null
  cy.resize()
  const saved = savedView?.scope === scopeKey() ? savedView : null
  restoringView = !!saved && saved.positions.size > 0
  holdLayout = restoringView
  if (!saved && renderedScope !== scopeKey()) cy.elements().remove()
  sync()
  if (restoringView && saved) {
    cy.batch(() => {
      cy.nodes().forEach(node => {
        const position = saved.positions.get(node.id())
        if (!position) return
        const locked = node.locked()
        node.unlock().position(position)
        if (locked) node.lock()
      })
      cy.zoom(saved.zoom)
      cy.pan(saved.pan)
    })
  }
  restoringView = false
  focusPendingEntity()
})
watch(() => graph.version, sync)
watch(() => graph.freshVersion, revealFresh)
watch(() => graph.styleVersion, restyle)
watch(() => graph.filter, () => { applyFilter(); applyLayers(); startLive() })
watch(() => graph.highlightIds, () => { applyTrace(); applyLayers(); startLive() })
watch(() => ws.ws.layers, () => { sync(); startLive() }, { deep: true })
watch([grouped, expandedGroups], () => { sync(); layout(true) })
watch(() => graph.focusId, () => { expandedGroups.value = new Set(); affiliationQuery.value = ''; panelOpen.value = false })
watch(() => ws.theme, () => { cy?.style(styleSheet() as any); sync() })
// Halo and score badge are node data, so flipping the switch is a re-sync, not a reload.
watch(() => ws.riskEmphasis, sync)
watch(() => [graph.selectedId, graph.selectedEdgeId], ([id, eid]) => {
  if (!cy) return
  applyLayers()
  startLive()
  cy.elements().unselect()
  if (id) cy.getElementById(id).select()
  else if (eid) cy.getElementById(eid).select()
})
/** Keep a selected node clear of the properties card: when it would sit at or behind the
 *  card's left edge, slide the view so it lands in the middle of the strip still in view.
 *  Vertical position is left alone unless the node is off-screen, which would otherwise
 *  leave it "centred" somewhere the user cannot see. */
function panIntoView(id: string, rightBound: number) {
  if (!cy || rightBound <= 0) return
  const n = cy.getElementById(id)
  if (!n || n.empty()) return
  const pos = n.renderedPosition()
  if (!pos) return
  const height = cy.height()
  const offscreenY = pos.y < 0 || pos.y > height
  if (pos.x < rightBound && !offscreenY) return
  cy.animate({
    panBy: { x: pos.x >= rightBound ? rightBound / 2 - pos.x : 0, y: offscreenY ? height / 2 - pos.y : 0 },
  }, { duration: 250 })
}
defineExpose({ fit, layout, panIntoView })
</script>

<style scoped>
.canvas-wrap { position: relative; width: 100%; height: 100%; }
.cy { position: absolute; inset: 0; }
.loading { position: absolute; top: 12px; left: 12px; }
.affiliations { position: absolute; top: 112px; right: 12px; z-index: 6; max-width: calc(100% - 24px); max-height: calc(100% - 124px); display: flex; flex-direction: column; align-items: flex-end; }
.affiliation-panel { margin-top: 8px; padding: 14px; width: 310px; max-width: 100%; min-height: 0; display: flex; flex-direction: column; border: 1px solid rgba(128,128,128,.4); border-radius: 8px; background: rgb(var(--v-theme-surface)); box-shadow: 0 8px 24px #0003; }
.affiliation-panel p { font-size: 12px; line-height: 1.45; margin: 8px 0; opacity: .8; }
.group-switch { display: flex; gap: 8px; align-items: center; font-size: 13px; }
.affiliation-search { border: 1px solid #8888; border-radius: 4px; padding: 8px; width: 100%; font-size: 13px; color: inherit; }
.affiliation-results { max-height: min(48vh, 430px); min-height: 0; overflow-y: auto; margin-top: 8px; }
.affiliation-entry { border-bottom: 1px solid #8884; padding: 6px 0; }
.group-button { text-align: left; width: 100%; display: grid; gap: 3px; padding: 7px 4px; font-size: 12px; }
.group-button span { opacity: .8; }
.affiliation-results h3 { font-size: 13px; margin-top: 12px; }
.affiliation-results ul { list-style: none; padding: 0; }
.affiliation-results li button { text-align: left; font-size: 12px; padding: 7px 4px; width: 100%; text-decoration: underline; text-underline-offset: 3px; }
.affiliation-panel button:hover { background: #8882; }
.affiliation-panel button:focus-visible { outline: 2px solid rgb(var(--v-theme-primary)); }
@media (max-width: 1100px) { .affiliations { top: 148px; max-height: calc(100% - 160px); } }
</style>
