export interface DeltaNode {
  id: string
  label: string
  props?: Record<string, any>
}

export interface DeltaEdge {
  id: string
  source: string
  target: string
}

export interface GraphDelta<N extends DeltaNode = DeltaNode, E extends DeltaEdge = DeltaEdge> {
  nodes: N[]
  edges: E[]
}

const isProgram = (node: DeltaNode) =>
  node.label === 'Entity' && node.props?.kind === 'program'

/**
 * Keep only the part of a live delta connected to the currently displayed
 * focused graph. New node IDs alone are not evidence that they belong there.
 */
export function filterFocusedDelta<N extends DeltaNode, E extends DeltaEdge>(
  delta: GraphDelta<N, E>,
  existingIds: Set<string>,
  focusId: string,
): GraphDelta<N, E> {
  const foreignPrograms = new Set(
    delta.nodes
      .filter(node => isProgram(node) && node.id !== focusId)
      .map(node => node.id),
  )
  const nodes = delta.nodes.filter(node => !foreignPrograms.has(node.id))
  const edges = (delta.edges || []).filter(
    edge => !foreignPrograms.has(edge.source) && !foreignPrograms.has(edge.target),
  )
  const deltaIds = new Set(nodes.map(node => node.id))
  const keep = new Set(nodes.filter(node => existingIds.has(node.id)).map(node => node.id))

  let changed = true
  while (changed) {
    changed = false
    for (const edge of edges) {
      if (keep.has(edge.source) && deltaIds.has(edge.target) && !keep.has(edge.target)) {
        keep.add(edge.target)
        changed = true
      }
      if (keep.has(edge.target) && deltaIds.has(edge.source) && !keep.has(edge.source)) {
        keep.add(edge.source)
        changed = true
      }
    }
  }

  const visible = (id: string) => existingIds.has(id) || keep.has(id)
  return {
    nodes: nodes.filter(node => keep.has(node.id)),
    edges: edges.filter(edge => visible(edge.source) && visible(edge.target)),
  }
}