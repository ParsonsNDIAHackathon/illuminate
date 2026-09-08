<template>
  <div class="canvas-wrap">
    <div ref="el" class="cy"></div>
    <div v-if="hasSimulation" class="simulation-notice">
      <strong>SIMULATION DATA</strong>
      <span>Scenario material for analysis — not an allegation or verified finding.</span>
    </div>
    <div v-if="graph.loading" class="loading"><v-progress-circular indeterminate size="28" /></div>
    <div class="canvas-tools">
      <v-btn icon="mdi-fit-to-screen" variant="text" title="Fit" @click="fit" />
      <v-btn icon="mdi-graph-outline" variant="text" title="Re-layout" @click="layout" />
      <v-btn icon="mdi-format-color-fill" variant="text" title="Clear findings focus and styles" @click="clearVisualFocus" />
      <v-btn icon="mdi-broom" variant="text" title="Clear canvas" @click="graph.clear()" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import cytoscape, { type Core } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import cola from 'cytoscape-cola'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { applyStyleOps, clearStyleOps } from '../styles/styleOps'
import { LABEL_COLORS } from '../styles/palette'
import { relationshipFamily } from '../styles/relationshipFamilies'

cytoscape.use(fcose)
cytoscape.use(cola)
const el = ref<HTMLElement>()
const graph = useGraph()
const ws = useWorkspace()
const hasSimulation = computed(() => graph.nodeList.some(n => n.props?.simulated) || graph.edgeList.some(e => e.props?.simulated))
let cy: Core | null = null
let sameNameCollapsed: boolean | null = null
const groupingLockedIds = new Set<string>()
const emit = defineEmits<{ (e: 'expand', id: string): void; (e: 'report', id: string): void }>()

const SAME_NAME_COLLAPSE_ZOOM = 1

function baseColor(n: any) {
  const t = ws.theme
  if (n.props?.kind === 'program') return LABEL_COLORS.Program[t]
  if (layerOf(n) === 'sources') return LABEL_COLORS.Source[t]
  return (LABEL_COLORS[n.label] || LABEL_COLORS.Entity)[t]
}
function shapeFor(n: any) {
  if (n.props?.kind === 'program') return 'round-rectangle'
  if (layerOf(n) === 'sources') return 'barrel'
  return ({ Entity: 'ellipse', Person: 'diamond', Category: 'hexagon', Location: 'round-triangle', Artifact: 'rectangle', Claim: 'tag' } as any)[n.label] || 'ellipse'
}
function badgeFor(n: any) {
  const p = n.props || {}
  const bits: string[] = []
  if (p.simulated) bits.push('SIM')
  if (p.flagged) bits.push('REVIEW')
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
  const simulation = dark ? '#f6c453' : '#b77900'
  return [
    { selector: 'node', style: { 'background-color': 'data(baseColor)', shape: 'data(shape)', width: 'data(size)', height: 'data(size)', label: 'data(name)', color: text, 'font-size': 10, 'text-wrap': 'ellipsis', 'text-max-width': 120, 'text-valign': 'bottom', 'text-margin-y': 4, 'text-outline-color': outline, 'text-outline-width': 2, 'border-width': 1.5, 'border-color': dark ? '#374151' : '#cbd5e1', 'overlay-padding': 4 } },
    { selector: 'node[?isRoot]', style: { 'border-width': 3, 'border-color': dark ? '#60a5fa' : '#1d4ed8', 'font-weight': 'bold', 'font-size': 12 } },
    { selector: 'node[badge != ""]', style: { label: (e: any) => `${e.data('name')}\n${e.data('badge')}`, 'text-wrap': 'wrap' } },
    { selector: 'node[?simulated]', style: { width: 'data(simSize)', height: 'data(simSize)', 'font-size': 'data(simFont)', 'border-style': 'dashed', 'border-color': simulation, 'border-width': 'data(simBorder)', 'background-opacity': .55 } },
    { selector: 'edge', style: { width: 1.8, 'line-color': 'data(color)', 'target-arrow-color': 'data(color)', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.95, 'curve-style': 'bezier', label: 'data(label)', 'font-size': 9, color: dark ? '#d1d5db' : '#374151', 'text-rotation': 'autorotate', 'text-outline-color': outline, 'text-outline-width': 2, 'text-background-opacity': 0 } },
    { selector: 'edge[family = "supply"]', style: { width: 3.2, 'arrow-scale': 1.15 } },
    { selector: 'edge[family = "control"]', style: { width: 2.6, 'arrow-scale': 1.05 } },
    { selector: 'edge[family = "people"]', style: { width: 2.2, 'line-style': 'dashed' } },
    { selector: 'edge[family = "affiliation"]', style: { width: 1.8, 'line-style': 'dashed', 'line-dash-pattern': [2, 3] } },
    { selector: 'edge[family = "location"]', style: { width: 2, 'line-style': 'dashed' } },
    { selector: 'edge[family = "evidence"]', style: { width: 2.2, 'line-style': 'dotted' } },
    { selector: 'edge[family = "classification"]', style: { 'line-style': 'dotted' } },
    { selector: 'edge[?simulated]', style: { 'line-style': 'dotted', width: 'data(simWidth)', 'line-color': simulation, 'target-arrow-color': simulation } },
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
    { selector: '.layer-hide.focus-path', style: { display: 'element' } },
    { selector: '.focus-context', style: { opacity: 0.22, 'z-index': 0 } },
    { selector: 'node.focus-path', style: { opacity: 1, 'z-index': 30, 'border-width': 4, 'border-color': dark ? '#7dd3c7' : '#006b62', 'font-size': 13, 'font-weight': 'bold', 'text-max-width': 170 } },
    { selector: 'edge.focus-path', style: { opacity: 1, 'z-index': 29, width: 5, 'line-color': dark ? '#7dd3c7' : '#006b62', 'target-arrow-color': dark ? '#7dd3c7' : '#006b62', 'font-size': 10, color: text } },
    { selector: 'node.focus-risk', style: { 'border-color': dark ? '#ff9b80' : '#a93622', 'border-width': 5 } },
    // a node or edge that arrived from a live change — held for a few seconds, then released
    { selector: 'node.fresh', style: { 'border-width': 5, 'border-color': dark ? '#34d399' : '#059669', 'z-index': 30 } },
    { selector: 'edge.fresh', style: { width: 3.4, 'line-color': dark ? '#34d399' : '#059669', 'target-arrow-color': dark ? '#34d399' : '#059669', 'z-index': 30 } },
    // search-bar filter: matches stay bright, everything else recedes
    { selector: '.q-dim', style: { opacity: 0.12, 'z-index': 0 } },
    { selector: 'node.q-match', style: { 'border-width': 3, 'border-color': dark ? '#fbbf24' : '#d97706', 'z-index': 20 } },
    { selector: 'edge.q-match', style: { width: 2.2, 'z-index': 20 } },
    // Layout-only links pull same-name entities and owners together without drawing or merging them.
    { selector: 'edge[?sameName]', style: { opacity: 0, width: 0, label: '', 'target-arrow-shape': 'none', events: 'no' } },
    // At low zoom, only one node is painted while every grouped record and its edges share its position.
    { selector: 'node.same-name-duplicate', style: { opacity: 0, label: '', events: 'no' } },
    // Keep simulation identity in screen-space and above every focus/selection/style override.
    { selector: 'node[?simulated]', style: { width: 'data(simSize)', height: 'data(simSize)', 'font-size': 'data(simFont)', 'border-style': 'dashed', 'border-color': simulation, 'border-width': 'data(simBorder)', label: (e: any) => `${e.data('name')}\nSIM${e.data('opBadge') ? ` · ${e.data('opBadge')}` : ''}`, 'text-wrap': 'wrap' } },
    { selector: 'edge[?simulated]', style: { width: 'data(simWidth)', 'line-style': 'dotted', 'line-color': simulation, 'target-arrow-color': simulation, label: 'data(simLabel)', 'font-size': 'data(simEdgeFont)', 'font-weight': 'bold', color: simulation, 'text-outline-color': outline, 'text-outline-width': 'data(simEdgeOutline)', 'text-background-color': outline, 'text-background-opacity': .9 } },
    { selector: 'edge.focus-path[?simulated]', style: { 'underlay-color': dark ? '#7dd3c7' : '#006b62', 'underlay-opacity': 1, 'underlay-padding': 'data(simEdgeHalo)' } },
    { selector: 'edge:selected[?simulated]', style: { 'underlay-color': dark ? '#f472b6' : '#be185d', 'underlay-opacity': 1, 'underlay-padding': 'data(simEdgeHalo)' } },
  ]
}

function toElements() {
  const root = graph.focusId
  const zoom = cy?.zoom() || 1
  const nodes = graph.nodeList.map(n => {
    const size = n.props?.kind === 'program' ? 56 : n.label === 'Entity' ? 34 : n.label === 'Person' ? 26 : 22
    return { group: 'nodes', data: { id: n.id, name: n.name, label: n.label, layer: layerOf(n), baseColor: baseColor(n), shape: shapeFor(n), size, simSize: size / zoom, simFont: 11 / zoom, simBorder: 3 / zoom, isRoot: n.id === root, simulated: !!n.props?.simulated, badge: badgeFor(n) } }
  })
  const edges = graph.edgeList.map(e => {
    const family = relationshipFamily(e.type)
    const label = e.type === 'SUPPLIES' && e.props?.tier ? `T${e.props.tier}${e.props.sole_source ? ' · sole' : ''}` : e.type === 'HELD_ROLE' ? (e.props?.title || '').slice(0, 18) : e.type === 'OWNS' && e.props?.pct ? `${e.props.pct}%` : ''
    return { group: 'edges', data: { id: e.id, source: e.source, target: e.target, type: e.type, family: family.key, color: ws.theme === 'dark' ? family.darkColor : family.color, simWidth: 3.5 / zoom, simEdgeFont: 10 / zoom, simEdgeOutline: 2 / zoom, simEdgeHalo: 2.5 / zoom, simulated: !!e.props?.simulated, label, simLabel: label ? `${label} · SIM` : 'SIM' } }
  })
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
}
function restyle() {
  if (!cy) return
  clearStyleOps(cy)
  applyStyleOps(cy, graph.styleOps, ws.theme)
  applyFilter()
  applyLayers()
  applyFindingFocus()
  // Focus classes determine which same-name members must remain visible when collapsed.
  applyZoomGrouping(true)
  markFresh()
}
const FAMILY_EDGES: Record<string, Set<string>> = {
  ownership: new Set(['OWNS', 'ULTIMATE_PARENT_OF', 'BENEFICIAL_OWNER_OF', 'PARENT_SEATED_IN']),
  concentration: new Set(['SUPPLIES']),
  people: new Set(['HELD_ROLE']),
  sanctions: new Set(['EVIDENCES', 'ASSERTS', 'TARGETS', 'ABOUT']),
  financial: new Set(['EVIDENCES', 'ASSERTS', 'ABOUT']),
  media: new Set(['EVIDENCES', 'ASSERTS', 'ABOUT']),
}
type Step = { edge: string; node: string }
function stableSteps(nodeId: string, allowed: Set<string>, supplyTowardVendor = false): Step[] {
  return graph.edgeList
    .filter(e => allowed.has(e.type) && (supplyTowardVendor ? e.target === nodeId : (e.source === nodeId || e.target === nodeId)))
    .map(e => ({ edge: e.id, node: supplyTowardVendor ? e.source : (e.source === nodeId ? e.target : e.source) }))
    .sort((a, b) => `${a.node}\u0000${a.edge}`.localeCompare(`${b.node}\u0000${b.edge}`))
}
function stablePath(from: string, to: string, allowed: Set<string>, supplyTowardVendor = false): string[] {
  if (from === to) return [from]
  const queue: { node: string; path: string[] }[] = [{ node: from, path: [from] }]
  const seen = new Set([from])
  while (queue.length) {
    const current = queue.shift()!
    for (const step of stableSteps(current.node, allowed, supplyTowardVendor)) {
      if (seen.has(step.node)) continue
      const path = [...current.path, step.edge, step.node]
      if (step.node === to) return path
      seen.add(step.node)
      queue.push({ node: step.node, path })
    }
  }
  return []
}
function betterPath(paths: string[][]): string[] {
  return paths.filter(p => p.length).sort((a, b) => a.length - b.length || a.join('\u0000').localeCompare(b.join('\u0000')))[0] || []
}
function applyFindingFocus() {
  if (!cy) return
  cy.elements().removeClass('focus-context focus-path focus-risk')
  const ids = graph.focusIds.filter(id => graph.nodes.has(id) || graph.edges.has(id))
  graph.setFocusUnavailable(graph.focusIds.filter(id => !graph.nodes.has(id) && !graph.edges.has(id)))
  const vendor = graph.focusVendorId
  if (!vendor || !graph.nodes.has(vendor)) return
  const rootId = ws.ws.root_id
  const pathIds = new Set<string>([vendor])
  if (rootId && graph.nodes.has(rootId)) {
    stablePath(rootId, vendor, new Set(['SUPPLIES']), true).forEach(id => pathIds.add(id))
  }
  const allowed = FAMILY_EDGES[graph.focusFamily] || new Set<string>()
  const riskIds = new Set<string>()
  for (const id of ids) {
    const edge = graph.edges.get(id)
    const targets = edge ? [edge.source, edge.target].sort() : [id]
    const connector = betterPath(targets.map(target => stablePath(vendor, target, allowed)))
    connector.forEach(part => pathIds.add(part))
    pathIds.add(id)
    riskIds.add(id)
    if (edge) { pathIds.add(edge.source); pathIds.add(edge.target) }
  }
  const path = cy.collection([...pathIds].map(id => cy!.getElementById(id)).filter(e => e.length))
  cy.elements().not(path).addClass('focus-context')
  path.addClass('focus-path')
  path.filter('.layer-hide').removeClass('layer-hide')
  cy.collection([...riskIds].map(id => cy!.getElementById(id))).addClass('focus-risk')
  window.setTimeout(() => { if (cy && path.length) cy.animate({ fit: { eles: path, padding: 90 }, duration: 450 }) }, 0)
}
function clearVisualFocus() { graph.clearFocus(); graph.clearStyleOps() }
function keepSimulationVisible() {
  if (!cy) return
  const zoom = cy.zoom()
  cy.nodes('[?simulated]').forEach(n => {
    n.data('simSize', Number(n.data('size')) / zoom)
    n.data('simFont', 11 / zoom)
    n.data('simBorder', 3 / zoom)
  })
  cy.edges('[?simulated]').forEach(e => {
    e.data('simWidth', 3.5 / zoom)
    e.data('simEdgeFont', 10 / zoom)
    e.data('simEdgeOutline', 2 / zoom)
    e.data('simEdgeHalo', 2.5 / zoom)
  })
}

// Layer toggles gate what the server sends, but nodes can arrive by other routes (chat results,
// generated Cypher, an API that predates the flag). The canvas enforces the toggles too, so an
// unchecked layer is never drawn. Edges to hidden nodes are hidden by Cytoscape automatically.
// The server names each node's layer (graphio.layer_of); the fallback mirrors it for nodes from
// a route that predates the field. Artifacts split by kind: registry entries and source records
// are "sources", documents (filings, news, awards, web pages) are "artifacts".
const SOURCE_KINDS = new Set(['record', 'registry'])
const LAYER_OF: Record<string, string> = { Person: 'people', Location: 'countries', Category: 'categories', Artifact: 'artifacts', Claim: 'claims' }
const LAYER_DEFAULT: Record<string, boolean> = { people: true, countries: false, categories: false, artifacts: false, sources: false, claims: false }
function layerOf(n: any): string | null {
  if (n.layer !== undefined) return n.layer
  if (n.label === 'Artifact') return SOURCE_KINDS.has(n.props?.kind || 'record') ? 'sources' : 'artifacts'
  return LAYER_OF[n.label] || null
}
function applyLayers() {
  if (!cy) return
  const L = ws.ws.layers || {}
  cy.nodes().forEach(n => {
    const layer = n.data('layer')
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

function applyZoomGrouping(force = false) {
  if (!cy) return
  const collapse = cy.zoom() < SAME_NAME_COLLAPSE_ZOOM
  if (!force && collapse === sameNameCollapsed) return
  const wasCollapsed = sameNameCollapsed
  sameNameCollapsed = collapse
  // Reset only locks/classes owned by this grouping behavior. This also restores nodes that
  // belonged to a group before a graph replacement but are no longer duplicated.
  groupingLockedIds.forEach(id => {
    const node = cy!.getElementById(id)
    if (node.nonempty()) {
      node.removeClass('same-name-duplicate')
      node.unlock()
    }
  })
  groupingLockedIds.clear()
  sameNameCollapsedGroups().forEach(ids => {
    const members = ids.map(id => cy!.getElementById(id)).filter(n => n.nonempty())
    if (members.length < 2) return
    if (collapse) {
      const position = members[0].position()
      const visible = members.filter(node =>
        node.hasClass('focus-path') || node.hasClass('focus-risk') || node.selected() || Boolean(node.data('simulated')),
      )
      if (!visible.some(node => node.id() === members[0].id())) visible.unshift(members[0])
      const visibleIds = new Set(visible.map(node => node.id()))
      const radius = visible.length > 1 ? 10 / cy!.zoom() : 0
      const visibleIndex = new Map(visible.map((node, index) => [node.id(), index]))
      members.forEach((node, index) => {
        const shownIndex = visibleIndex.get(node.id()) || 0
        const angle = visible.length > 1 ? (Math.PI * 2 * shownIndex) / visible.length : 0
        node.position(visibleIds.has(node.id())
          ? { x: position.x + Math.cos(angle) * radius, y: position.y + Math.sin(angle) * radius }
          : position)
        node.lock()
        groupingLockedIds.add(node.id())
        node.toggleClass('same-name-duplicate', index > 0 && !visibleIds.has(node.id()))
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
  cy.on('zoom', () => { applyZoomGrouping(); keepSimulationVisible() })
  sync()
})
onBeforeUnmount(() => { stopLive(); cy?.destroy() })
watch(() => graph.version, sync)
watch(() => graph.freshVersion, revealFresh)
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
.simulation-notice { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 6; display: flex; align-items: center; gap: 10px; padding: 8px 14px; border: 2px solid #9a6700; border-radius: 4px; background: #fff4cf; color: #563b00; box-shadow: 0 3px 12px rgba(60,45,0,.16); font-size: 12px; letter-spacing: .01em; }
.simulation-notice strong { font-size: 11px; letter-spacing: .12em; white-space: nowrap; }
@media (max-width: 760px) { .simulation-notice { left: 10px; right: 54px; transform: none; align-items: flex-start; flex-direction: column; gap: 2px; } }
</style>
