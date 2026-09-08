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
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { applyStyleOps, clearStyleOps } from '../styles/styleOps'
import { LABEL_COLORS } from '../styles/palette'

cytoscape.use(fcose)
const el = ref<HTMLElement>()
const graph = useGraph()
const ws = useWorkspace()
let cy: Core | null = null
const emit = defineEmits<{ (e: 'expand', id: string): void; (e: 'report', id: string): void }>()

const EDGE_COLORS: Record<string, string> = { SUPPLIES: '#64748b', OWNS: '#ea580c', ULTIMATE_PARENT_OF: '#ea580c', HELD_ROLE: '#0f766e', BENEFICIAL_OWNER_OF: '#0f766e', PROVIDES: '#7c3aed', SUBCATEGORY_OF: '#7c3aed', INCORPORATED_IN: '#92400e', OPERATES_IN: '#92400e', MANUFACTURES_IN: '#b45309', PARENT_SEATED_IN: '#b45309', EVIDENCES: '#9ca3af', ASSERTS: '#be185d', TARGETS: '#be185d', ABOUT: '#9ca3af' }

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
  ]
}

function toElements() {
  const root = ws.ws.root_id
  const nodes = graph.nodeList.map(n => ({ group: 'nodes', data: { id: n.id, name: n.name, label: n.label, baseColor: baseColor(n), shape: shapeFor(n), size: n.props?.kind === 'program' ? 56 : n.label === 'Entity' ? 34 : n.label === 'Person' ? 26 : 22, isRoot: n.id === root, simulated: !!n.props?.simulated, badge: badgeFor(n) } }))
  const edges = graph.edgeList.map(e => ({ group: 'edges', data: { id: e.id, source: e.source, target: e.target, type: e.type, color: EDGE_COLORS[e.type] || '#9ca3af', simulated: !!e.props?.simulated, label: e.type === 'SUPPLIES' && e.props?.tier ? `T${e.props.tier}${e.props.sole_source ? ' · sole' : ''}` : e.type === 'HELD_ROLE' ? (e.props?.title || '').slice(0, 18) : e.type === 'OWNS' && e.props?.pct ? `${e.props.pct}%` : '' } }))
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
    layout(fresh.length > 0 && existing.size === 0)
  }
  restyle()
}
function restyle() { if (!cy) return; clearStyleOps(cy); applyStyleOps(cy, graph.styleOps, ws.theme) }
function layout(fit = true) {
  if (!cy || cy.nodes().length === 0) return
  // A fresh canvas has every node at the origin; fcose must randomise from there or it collapses to a line.
  // Incremental additions keep existing positions so the user's mental map survives.
  const l = cy.layout({ name: 'fcose', animate: true, animationDuration: 400, randomize: fit, fit, padding: 40, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, quality: 'default' } as any)
  l.run()
}
function fit() { cy?.fit(undefined, 40) }

// Dragging: the graph is not frozen around the grabbed node. While it moves, its neighbours
// follow with damping (1 hop at 55 %, 2 hops at 20 %); on release the local neighbourhood
// re-settles with fcose, the dropped node pinned where the user left it.
const FOLLOW_1 = 0.55, FOLLOW_2 = 0.2
let dragPrev: { x: number; y: number } | null = null
function onGrab(ev: any) { const p = ev.target.position(); dragPrev = { x: p.x, y: p.y } }
function onDrag(ev: any) {
  const n = ev.target
  if (!dragPrev || !cy) return
  const p = n.position(); const dx = p.x - dragPrev.x, dy = p.y - dragPrev.y
  dragPrev = { x: p.x, y: p.y }
  if (!dx && !dy) return
  const moving = cy.nodes(':grabbed')                       // the dragged node plus any co-selected ones
  const hop1 = n.neighborhood('node').difference(moving)
  const hop2 = hop1.neighborhood('node').difference(hop1).difference(moving)
  hop1.shift({ x: dx * FOLLOW_1, y: dy * FOLLOW_1 })
  hop2.shift({ x: dx * FOLLOW_2, y: dy * FOLLOW_2 })
}
function onFree(ev: any) {
  dragPrev = null
  if (!cy) return
  const n = ev.target
  const local = n.closedNeighborhood().closedNeighborhood()
  if (local.nodes().length < 3) return
  const pos = n.position()
  local.layout({ name: 'fcose', animate: true, animationDuration: 250, randomize: false, fit: false, quality: 'draft',
    nodeRepulsion: () => 9000, idealEdgeLength: () => 90,
    fixedNodeConstraint: [{ nodeId: n.id(), position: { x: pos.x, y: pos.y } }] } as any).run()
}

onMounted(() => {
  cy = cytoscape({ container: el.value!, style: styleSheet(), wheelSensitivity: 0.25, minZoom: 0.1, maxZoom: 4 })
  ;(window as any).__cy = cy
  cy.on('tap', 'node', (ev) => graph.select(ev.target.id()))
  cy.on('tap', 'edge', (ev) => graph.selectEdge(ev.target.id()))
  cy.on('tap', (ev) => { if (ev.target === cy) { graph.select(null); graph.selectEdge(null) } })
  cy.on('dbltap', 'node', (ev) => { const n = graph.nodes.get(ev.target.id()); if (n && (n.label === 'Entity' || n.label === 'Person')) emit('expand', ev.target.id()) })
  cy.on('grab', 'node', onGrab)
  cy.on('drag', 'node', onDrag)
  cy.on('free', 'node', onFree)
  sync()
})
onBeforeUnmount(() => cy?.destroy())
watch(() => graph.version, sync)
watch(() => graph.styleVersion, restyle)
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
