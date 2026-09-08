interface LayerNode {
  label: string
  layer?: string | null
  props?: Record<string, any>
}

export interface LayerGraphNode extends LayerNode { id: string }
export interface LayerGraphEdge { source: string; target: string }

export type GraphLayer =
  | 'people'
  | 'countries'
  | 'categories'
  | 'artifacts'
  | 'sources'
  | 'claims'

/** Workspace layer key for organizations that reach the canvas only through people, places,
 *  documents or claims — no chain of entity-to-entity edges joins them to a program. On (the
 *  default) draws them; off hides them however the other layers are set. */
export const INDIRECT_ORGS = 'indirect_orgs'

const SOURCE_KINDS = new Set(['record', 'registry'])
const LAYER_OF: Record<string, GraphLayer> = {
  Person: 'people',
  Location: 'countries',
  Category: 'categories',
  Artifact: 'artifacts',
  Claim: 'claims',
}
const LAYER_DEFAULT: Record<GraphLayer, boolean> = {
  people: true,
  countries: false,
  categories: false,
  artifacts: false,
  sources: false,
  claims: false,
}

export function layerOf(node: LayerNode): GraphLayer | null {
  if (node.layer !== undefined) return node.layer as GraphLayer | null
  if (node.label === 'Artifact') {
    return SOURCE_KINDS.has(node.props?.kind || 'record') ? 'sources' : 'artifacts'
  }
  return LAYER_OF[node.label] || null
}

/** Metadata copied into Cytoscape node data by GraphCanvas.toElements(). */
export function layerData(node: LayerNode): { layer: GraphLayer | null } {
  return { layer: layerOf(node) }
}

export function layerVisible(
  layer: GraphLayer | null | undefined,
  enabled: Partial<Record<GraphLayer, boolean>>,
): boolean {
  return !layer || (enabled[layer] ?? LAYER_DEFAULT[layer])
}

export function indirectOrgsVisible(enabled: Record<string, boolean>): boolean {
  return enabled[INDIRECT_ORGS] ?? true
}

/** An entity that is not a program: a company, group, agency or other organization. */
export function isOrganization(node: LayerNode): boolean {
  return node.label === 'Entity' && node.props?.kind !== 'program'
}

const isProgram = (node: LayerNode) => node.label === 'Entity' && node.props?.kind === 'program'

function adjacency(nodes: LayerGraphNode[], edges: LayerGraphEdge[]): Map<string, string[]> {
  const ids = new Set(nodes.map(n => n.id))
  const neighbours = new Map<string, string[]>()
  const link = (from: string, to: string) => {
    const list = neighbours.get(from)
    if (list) list.push(to)
    else neighbours.set(from, [to])
  }
  for (const e of edges) {
    if (e.source === e.target || !ids.has(e.source) || !ids.has(e.target)) continue
    link(e.source, e.target)
    link(e.target, e.source)
  }
  return neighbours
}

/**
 * Organizations left with nothing visible to hang off once the hidden layers are gone.
 *
 * Entities are never fetched by layer, so a company that is in the graph only because a
 * person on the people layer held a role there stays on the canvas when that layer is
 * hidden, as a lone dot. Those are pruned here: an organization is hidden when it has
 * edges in the loaded graph and every one of them leads to a hidden node. Programs and
 * `keep` are never hidden, and an organization with no edges at all is left alone, since
 * the layers did not orphan it. Two such companies joined to each other survive as an
 * island; the indirect-organizations filter is what clears those.
 */
export function orphanedOrganizations(
  nodes: LayerGraphNode[],
  edges: LayerGraphEdge[],
  hidden: Set<string>,
  keep: Iterable<string> = [],
): Set<string> {
  const kept = new Set(keep)
  const neighbours = adjacency(nodes, edges)
  const out = new Set<string>()
  for (const n of nodes) {
    if (!isOrganization(n) || kept.has(n.id) || hidden.has(n.id)) continue
    const around = neighbours.get(n.id)
    if (around && around.every(id => hidden.has(id))) out.add(n.id)
  }
  return out
}

/**
 * Organizations the supply, ownership and affiliation network does not reach: nothing
 * connects them to a program (or to `keep`, the root) except a person, a place, a document
 * or a claim. They are the other companies a supplier's director also sits on the board
 * of, the parent that a shared country pulled in, and so on — context that clutters the
 * chain. The walk goes from every visible program and kept node over edges whose both ends
 * are visible entities; every organization it never arrives at is returned, an organization
 * with no edges at all included. With nothing to be direct to — no program and no root on
 * the canvas — nothing is indirect.
 */
export function indirectOrganizations(
  nodes: LayerGraphNode[],
  edges: LayerGraphEdge[],
  hidden: Set<string>,
  keep: Iterable<string> = [],
): Set<string> {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const anchors = [...new Set([...nodes.filter(n => isProgram(n) && !hidden.has(n.id)).map(n => n.id), ...keep])].filter(id => byId.has(id))
  if (!anchors.length) return new Set()
  const neighbours = adjacency(nodes, edges)
  const reached = new Set(anchors)
  const queue = [...anchors]
  while (queue.length) {
    const id = queue.shift()!
    for (const next of neighbours.get(id) || []) {
      if (reached.has(next) || hidden.has(next) || byId.get(next)!.label !== 'Entity') continue
      reached.add(next)
      queue.push(next)
    }
  }
  return new Set(nodes.filter(n => isOrganization(n) && !hidden.has(n.id) && !reached.has(n.id)).map(n => n.id))
}

/** Every node the layer toggles hide: the off layers, the indirect organizations if that toggle
 *  is off, then whatever organizations the hiding stranded. */
export function hiddenNodeIds(
  nodes: LayerGraphNode[],
  edges: LayerGraphEdge[],
  enabled: Record<string, boolean>,
  keep: Iterable<string> = [],
): Set<string> {
  const hidden = new Set<string>()
  for (const n of nodes) if (!layerVisible(layerOf(n), enabled)) hidden.add(n.id)
  if (!indirectOrgsVisible(enabled)) indirectOrganizations(nodes, edges, hidden, keep).forEach(id => hidden.add(id))
  orphanedOrganizations(nodes, edges, hidden, keep).forEach(id => hidden.add(id))
  return hidden
}
