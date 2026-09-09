<template>
  <div class="canvas-wrap">
    <div ref="el" class="cy"></div>
    <div v-if="graph.loading" class="loading"><v-progress-circular indeterminate size="28" /></div>
    <div class="canvas-tools">
      <v-btn icon="mdi-fit-to-screen" variant="text" title="Fit" @click="fit" />
      <v-btn icon="mdi-graph-outline" variant="text" title="Re-layout" @click="layout" />
      <v-btn icon="mdi-format-color-fill" variant="text" title="Clear styles" @click="graph.clearStyleOps()" />
      <v-btn icon="mdi-broom" variant="text" title="Clear canvas" @click="graph.clear()" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
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

cytoscape.use(fcose)
cytoscape.use(cola)
const el = ref<HTMLElement>()
const graph = useGraph()
const ws = useWorkspace()
let cy: Core | null = null
const emit = defineEmits<{ (e: 'expand', id: string): void; (e: 'report', id: string): void }>()


function badgeFor(n: any) {
  const p = n.props || {}
  const bits: string[] = []
  if (p.simulated) bits.push('SIM')
  if (p.flagged) bits.push('⚑')
  // The number, not just the halo: two nodes in the same band still rank against each
  // other, and a thin score is marked so nobody acts on 100/2-of-7 as if it were settled.
  if (p.risk_score != null && p.risk_band && p.risk_band !== 'low') {
    bits.push(`${p.risk_score}${isThin(p.risk_confidence) ? '?' : ''}`)
  }
  return bits.join(' ')
}

/** Risk halo data for a node, or nulls when it is unscored — unscored gets no ink at all. */
function haloData(n: any, theme: 'light' | 'dark') {
  const halo = haloFor(n.props?.risk_band, theme)
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
  return [...nodes, ...edges]
}

function sync() {
  if (!cy) return
  const existing = new Set(cy.elements().map(e => e.id()))
  const wanted = toElements()
  const wantedIds = new Set(wanted.map(w => w.data.id))
  cy.elements().filter(e => !wantedIds.has(e.id())).remove()
  const fresh = wanted.filter(w => !existing.has(w.data.id))
  wanted.filter(w => existing.has(w.data.id)).forEach(w => cy!.getElementById(w.data.id).data(w.data))
  if (fresh.length) {
    cy.add(fresh as any)
    if (existing.size === 0) layout(true)
    else { seedNearNeighbours(fresh.filter(w => w.group === 'nodes').map(w => w.data.id)); startLive() }
  } else if (cy.elements().length === 0) {
    stopLive()
  }
  restyle()
}
function restyle() {
  if (!cy) return
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
  cy.nodes().forEach(n => n.toggleClass('layer-hide', hidden.has(n.id())))
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
  if (!cy || cy.nodes().length === 0) return
  stopLive()
  // A fresh canvas has every node at the origin; fcose must randomise from there or it collapses to a line.
  const l = cy.layout({ name: 'fcose', animate: true, animationDuration: 400, randomize: fit, fit, padding: 40, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, quality: 'default' } as any)
  l.one('layoutstop', () => startLive())
  l.run()
}
function fit() { cy?.fit(undefined, 40) }

onMounted(() => {
  cy = cytoscape({ container: el.value!, style: styleSheet(), wheelSensitivity: 0.25, minZoom: 0.1, maxZoom: 4 })
  ;(window as any).__cy = cy
  cy.on('tap', 'node', (ev) => graph.select(ev.target.id()))
  cy.on('tap', 'edge', (ev) => graph.selectEdge(ev.target.id()))
  cy.on('tap', (ev) => { if (ev.target === cy) { graph.select(null); graph.selectEdge(null) } })
  cy.on('dbltap', 'node', (ev) => { const n = graph.nodes.get(ev.target.id()); if (n && (n.label === 'Entity' || n.label === 'Person')) emit('expand', ev.target.id()) })
  sync()
})
onBeforeUnmount(() => { stopLive(); cy?.destroy() })
watch(() => graph.version, sync)
watch(() => graph.freshVersion, revealFresh)
watch(() => graph.styleVersion, restyle)
watch(() => graph.filter, applyFilter)
watch(() => graph.highlightIds, applyTrace)
watch(() => ws.ws.layers, applyLayers, { deep: true })
watch(() => ws.theme, () => { cy?.style(styleSheet() as any); sync() })
watch(() => [graph.selectedId, graph.selectedEdgeId], ([id, eid]) => {
  if (!cy) return
  cy.elements().unselect()
  if (id) cy.getElementById(id).select()
  else if (eid) cy.getElementById(eid).select()
})
defineExpose({ fit, layout })
</script>

<style scoped>
.canvas-wrap { position: relative; width: 100%; height: 100%; }
.cy { position: absolute; inset: 0; }
.loading { position: absolute; top: 12px; left: 12px; }
.canvas-tools { position: absolute; right: 8px; top: 8px; display: flex; flex-direction: column; gap: 2px; opacity: .85; }
</style>
