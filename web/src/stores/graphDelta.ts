export interface DeltaNode {
  id: string
  label: string
  props?: Record<string, any>
}

export interface DeltaEdge {
  id: string
  source: string
  target: string
  type: string
}

export interface GraphDelta<N extends DeltaNode = DeltaNode, E extends DeltaEdge = DeltaEdge> {
  nodes: N[]
  edges: E[]
}

function isProgram(node: DeltaNode) {
  return node.label === 'Entity' && node.props?.kind === 'program'
}

const CONTROL_UPSTREAM = new Set(['OWNS', 'ULTIMATE_PARENT_OF', 'BENEFICIAL_OWNER_OF'])

function supplyMembers<N extends DeltaNode, E extends DeltaEdge>(
  graph: GraphDelta<N, E>,
  focusId: string,
) {
  const nodeIds = new Set(graph.nodes.filter(node => !isProgram(node) || node.id === focusId).map(node => node.id))
  const keep = new Set(nodeIds.has(focusId) ? [focusId] : [])
  let changed = true
  while (changed) {
    changed = false
    for (const edge of graph.edges) {
      if (edge.type !== 'SUPPLIES' || !nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue
      if (keep.has(edge.target) && !keep.has(edge.source)) { keep.add(edge.source); changed = true }
    }
  }
  return keep
}

/**
 * Keep only the part of a live delta connected to the program already on a
 * focused canvas. Only SUPPLIES paths establish program membership; shared
 * countries, categories, people, or evidence can add context to a known member
 * but can never pull a different program's supplier into this canvas.
 */
export function restrictDeltaToFocus<N extends DeltaNode, E extends DeltaEdge>(
  delta: GraphDelta<N, E>,
  canvas: GraphDelta<N, E>,
  focusId: string,
): GraphDelta<N, E> {
  const nodes = delta.nodes.filter(node => !isProgram(node) || node.id === focusId)
  const nodeIds = new Set(nodes.map(node => node.id))
  const edges = (delta.edges || []).filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target))
  const knownMembers = supplyMembers(canvas, focusId)
  const keep = new Set(nodes.filter(node => knownMembers.has(node.id)).map(node => node.id))
  const byId = new Map(nodes.map(node => [node.id, node]))

  // A newly arrived entity becomes a member only through the focused program's
  // supply path, never through a shared metadata node.
  let changed = true
  while (changed) {
    changed = false
    for (const edge of edges) {
      if (edge.type !== 'SUPPLIES') continue
      if (keep.has(edge.target) && !keep.has(edge.source)) { keep.add(edge.source); changed = true }
    }
  }

  // Retain ancillary context for known members. Non-entity nodes may form
  // evidence chains; ownership entities are followed only upstream so a shared
  // owner cannot introduce an unrelated sibling supplier.
  changed = true
  while (changed) {
    changed = false
    for (const edge of edges) {
      if (edge.type === 'SUPPLIES') continue
      const source = byId.get(edge.source)
      const target = byId.get(edge.target)
      if (keep.has(edge.source) && target && !keep.has(edge.target) && target.label !== 'Entity') {
        keep.add(edge.target); changed = true
      }
      if (keep.has(edge.target) && source && !keep.has(edge.source) && (source.label !== 'Entity' || CONTROL_UPSTREAM.has(edge.type))) {
        keep.add(edge.source); changed = true
      }
    }
  }

  return {
    nodes: nodes.filter(node => keep.has(node.id)),
    edges: edges.filter(edge => keep.has(edge.source) && keep.has(edge.target)),
  }
}