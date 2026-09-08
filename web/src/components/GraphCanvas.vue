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
import { LABEL_COLORS } from '../styles/palette'

cytoscape.use(fcose)
cytoscape.use(cola)
const el = ref<HTMLElement>()
const graph = useGraph()
const ws = useWorkspace()
let cy: Core | null = null
let sameNameCollapsed: boolean | null = null
const emit = defineEmits<{ (e: 'expand', id: string): void; (e: 'report', id: string): void }>()

const EDGE_COLORS: Record<string, string> = { SUPPLIES: '#64748b', OWNS: '#ea580c', ULTIMATE_PARENT_OF: '#ea580c', HELD_ROLE: '#0f766e', BENEFICIAL_OWNER_OF: '#0f766e', PROVIDES: '#7c3aed', SUBCATEGORY_OF: '#7c3aed', INCORPORATED_IN: '#92400e', OPERATES_IN: '#92400e', MANUFACTURES_IN: '#b45309', PARENT_SEATED_IN: '#b45309', EVIDENCES: '#9ca3af', ASSERTS: '#be185d', TARGETS: '#be185d', ABOUT: '#9ca3af' }
const SAME_NAME_COLLAPSE_ZOOM = 1

function baseColor(n: any) {
  const t = ws.theme
  if (n.props?.kind === 'program') return LABEL_COLORS.Program[t]
  return (LABEL_COLORS[n.label] || LABEL_COLORS.Entity)[t]
}
function shapeFor(n: any) {
  if (n.props?.kind === 'program') return 'round-rectangle'
  return ({ Entity: 'ellipse', Person: 'diamond', Category: 'hexagon', Location: 'round-triangle', Artifact: 'rectangle', Claim: 'tag' } as any)[n.label] || 'ellipse'
}
function badgeFor(n: any) {
  const p = n.props || {}
  const bits: string[] = []
  if (p.simulated) bits.push('SIM')
  if (p.flagged) bits.push('⚑')
  return bits.join(' ')
}

/** Case-, accent- and punctuation-insensitive form: "Société L-3 Harris" → "societe l 3 harris". */
function fold(s: string) { return s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim() }

function sameNameCollapsedGroups() {
  const beneficialOwnerIds = new Set(
    graph.edgeList.filter(e => e.type === 'BENEFICIAL_OWNER_OF').map(e => e.source),
  )
  const nodesByTypeAndName = new Map<string, string[]>()
  graph.nodeList.forEach(n => {
    const isCollapsible = n.label === 'Entity' || (n.label === 'Person' && beneficialOwnerIds.has(n.id))
    if (!isCollapsible) return
    const name = fold(n.name || '')
    if (!name) return
    const key = `${n.label}:${name}`
    const ids = nodesByTypeAndName.get(key) || []
    ids.push(n.id)
    nodesByTypeAndName.set(key, ids)
  })
  return [...nodesByTypeAndName.values()].filter(ids => ids.length > 1)
}

function styleSheet(): any[] {
  const dark = ws.theme === 'dark'
  const text = dark ? '#e5e7eb' : '#111827'
  const outline = dark ? '#0e1013' : '#ffffff'
  return [
    { selector: 'node', style: { 'background-color': 'data(baseColor)', shape: 'data(shape)', width: 'data(size)', height: 'data(size)', label: 'data(name)', color: text, 'font-size': 10, 'text-wrap': 'ellipsis', 'text-max-width': 120, 'text-valign': 'bottom', 'text-margin-y': 4, 'text-outline-color': outline, 'text-outline-width': 2, 'border-width': 1.5, 'border-color': dark ? '#374151' : '#cbd5e1', 'overlay-padding': 4 } },
    { selector: 'node[?isRoot]', style: { 'border-width': 3, 'border-color': dark ? '#60a5fa' : '#1d4ed8', 'font-weight': 'bold', 'font-size': 12 } },
    { selector: 'node[badge != ""]', style: { label: (e: any) => `${e.data('name')}\n${e.data('badge')}`, 'text-wrap': 'wrap' } },
    { selector: 'node[?simulated]', style: { 'border-style': 'dashed', 'border-color': dark ? '#facc15' : '#ca8a04', 'border-width': 2 } },
    { selector: 'edge', style: { width: 1.4, 'line-color': 'data(color)', 'target-arrow-color': 'data(color)', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: dark ? '#9ca3af' : '#4b5563', 'text-rotation': 'autorotate', 'text-outline-color': outline, 'text-outline-width': 2, 'text-background-opacity': 0 } },
    { selector: 'edge[type = "HELD_ROLE"]', style: { 'line-style': 'dashed' } },
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
    // search-bar filter: matches stay bright, everything else recedes
    { selector: '.q-dim', style: { opacity: 0.12, 'z-index': 0 } },
    { selector: 'node.q-match', style: { 'border-width': 3, 'border-color': dark ? '#fbbf24' : '#d97706', 'z-index': 20 } },
    { selector: 'edge.q-match', style: { width: 2.2, 'z-index': 20 } },
    // Layout-only links pull same-name entities and owners together without drawing or merging them.
    { selector: 'edge[?sameName]', style: { opacity: 0, width: 0, label: '', 'target-arrow-shape': 'none', events: 'no' } },
    // At low zoom, only one node is painted while every grouped record and its edges share its position.
    { selector: 'node.same-name-duplicate', style: { opacity: 0, label: '', events: 'no' } },
  ]
}

function toElements() {
  const root = ws.ws.root_id
  const nodes = graph.nodeList.map(n => ({ group: 'nodes', data: { id: n.id, name: n.name, label: n.label, baseColor: baseColor(n), shape: shapeFor(n), size: n.props?.kind === 'program' ? 56 : n.label === 'Entity' ? 34 : n.label === 'Person' ? 26 : 22, isRoot: n.id === root, simulated: !!n.props?.simulated, badge: badgeFor(n) } }))
  const edges = graph.edgeList.map(e => ({ group: 'edges', data: { id: e.id, source: e.source, target: e.target, type: e.type, color: EDGE_COLORS[e.type] || '#9ca3af', simulated: !!e.props?.simulated, label: e.type === 'SUPPLIES' && e.props?.tier ? `T${e.props.tier}${e.props.sole_source ? ' · sole' : ''}` : e.type === 'HELD_ROLE' ? (e.props?.title || '').slice(0, 18) : e.type === 'OWNS' && e.props?.pct ? `${e.props.pct}%` : '' } }))
  const sameNameEdges: any[] = []
  sameNameCollapsedGroups().forEach(ids => {
    const source = ids[0]
    ids.slice(1).forEach((target, index) => sameNameEdges.push({
      group: 'edges',
      data: { id: `__same-name__${encodeURIComponent(source)}__${index}`, source, target, sameName: true, color: 'transparent', label: '' },
    }))
  })
  return [...nodes, ...edges, ...sameNameEdges]
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
  applyZoomGrouping(true)
}
function restyle() { if (!cy) return; clearStyleOps(cy); applyStyleOps(cy, graph.styleOps, ws.theme); applyFilter(); applyLayers() }

// Layer toggles gate what the server sends, but nodes can arrive by other routes (chat results,
// generated Cypher, an API that predates the flag). The canvas enforces the toggles too, so an
// unchecked layer is never drawn. Edges to hidden nodes are hidden by Cytoscape automatically.
const LAYER_OF: Record<string, string> = { Person: 'people', Location: 'countries', Category: 'categories', Artifact: 'artifacts', Claim: 'artifacts' }
const LAYER_DEFAULT: Record<string, boolean> = { people: true, countries: false, categories: false, artifacts: false }
function applyLayers() {
  if (!cy) return
  const L = ws.ws.layers || {}
  cy.nodes().forEach(n => {
    const layer = LAYER_OF[n.data('label')]
    const on = !layer || (L[layer] ?? LAYER_DEFAULT[layer])
    n.toggleClass('layer-hide', !on)
  })
}

// Layout strategy: fcose arranges a fresh canvas (it is the better static layout), then cola takes
// over in infinite mode — a force simulation that keeps running, so dragging a node pulls its
// neighbours through the edges and the rest of the graph relaxes, the way d3-force does in Neo4j
// Browser. Cola pins the grabbed node to the pointer itself; nothing here handles drag events.
let live: any = null
function stopLive() { if (live) { try { live.stop() } catch {} live = null } }
function startLive() {
  stopLive()
  if (!cy || cy.nodes().length === 0) return
  live = cy.layout({
    name: 'cola', infinite: true, fit: false, randomize: false, animate: true,
    edgeLength: 115, nodeSpacing: () => 26, avoidOverlap: true, handleDisconnected: true, convergenceThreshold: 0.02,
  } as any)
  live.run()
}
// Nodes added to a running canvas would otherwise appear at the origin and fly across it; drop
// each one next to a neighbour that already has a position and let the simulation settle it.
function seedNearNeighbours(ids: string[]) {
  if (!cy) return
  const fresh = new Set(ids)
  for (const id of ids) {
    const n = cy.getElementById(id)
    const anchor = n.neighborhood('node').filter(m => !fresh.has(m.id()))[0]
    if (!anchor) continue
    const p = anchor.position()
    n.position({ x: p.x + (Math.random() - 0.5) * 80, y: p.y + (Math.random() - 0.5) * 80 })
  }
}

function applyZoomGrouping(force = false) {
  if (!cy) return
  const collapse = cy.zoom() < SAME_NAME_COLLAPSE_ZOOM
  if (!force && collapse === sameNameCollapsed) return
  const wasCollapsed = sameNameCollapsed
  sameNameCollapsed = collapse
  sameNameCollapsedGroups().forEach(ids => {
    const members = ids.map(id => cy!.getElementById(id)).filter(n => n.nonempty())
    if (members.length < 2) return
    if (collapse) {
      const position = members[0].position()
      members.forEach((node, index) => {
        node.position(position)
        node.lock()
        node.toggleClass('same-name-duplicate', index > 0)
      })
    } else {
      const center = members[0].position()
      members.forEach((node, index) => {
        const angle = (Math.PI * 2 * index) / members.length
        node.removeClass('same-name-duplicate')
        node.unlock()
        node.position({ x: center.x + Math.cos(angle) * 24, y: center.y + Math.sin(angle) * 24 })
      })
    }
  })
  if (wasCollapsed && !collapse) startLive()
}

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
function layout(fit = true) {
  if (!cy || cy.nodes().length === 0) return
  stopLive()
  // A fresh canvas has every node at the origin; fcose must randomise from there or it collapses to a line.
  const l = cy.layout({ name: 'fcose', animate: true, animationDuration: 400, randomize: fit, fit, padding: 40, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, quality: 'default' } as any)
  l.one('layoutstop', () => { applyZoomGrouping(true); startLive() })
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
  cy.on('zoom', () => applyZoomGrouping())
  sync()
})
onBeforeUnmount(() => { stopLive(); cy?.destroy() })
watch(() => graph.version, sync)
watch(() => graph.styleVersion, restyle)
watch(() => graph.filter, applyFilter)
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
