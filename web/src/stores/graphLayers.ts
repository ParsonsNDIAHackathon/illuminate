interface LayerNode {
  label: string
  layer?: string | null
  props?: Record<string, any>
}

export interface LayerGraphNode extends LayerNode { id: string }
export interface LayerGraphEdge { source: string; target: string; type?: string | null }

export type GraphLayer =
  | 'people'
  | 'countries'
  | 'categories'
  | 'artifacts'
  | 'sources'
  | 'claims'

/** Workspace layer key for organizations no chain of contracts or ownership joins to a program —
 *  they reach the canvas through a person, a place, a document, a claim, or through another
 *  company they merely lobby or share a trade association with. On (the default) draws them; off
 *  hides them however the other layers are set, except for the risky ones (RISK_PIN_FLOOR). */
export const INDIRECT_ORGS = 'indirect_orgs'

/** Relationship types that carry a program's chain from one organization to the next: it supplies
 *  into the chain, or it owns something that does. Every other entity-to-entity edge is
 *  affiliation, not contract — MEMBER_OF a trade council, LOBBIES a government body, DONATED_TO,
 *  TRANSACTS_WITH — and a company reached only that way is as indirect as one reached through a
 *  person. RTX alone brings hundreds of those, none of them on an award. */
const CHAIN_RELS = new Set(['SUPPLIES', 'OWNS', 'ULTIMATE_PARENT_OF'])

/** Chain edges that count only when they point *at* the chain. OWNS runs parent -> child, and who
 *  owns a supplier is material — it controls a company on the contract — while that owner's other
 *  subsidiaries are not: Raytheon Visual Analytics is on the V-22 canvas because its parent sells
 *  to the program, which says nothing about the V-22. So ownership is walked upwards only, from a
 *  company in the chain to its owner, and the siblings stay off unless they are risky in their own
 *  right, where the pin holds them. SUPPLIES is walked both ways: the direction recorded on it is
 *  not reliable enough to hang the supply base on — a one-way walk drops two dozen real V-22
 *  suppliers, Rolls-Royce and Northrop Grumman among them. */
const INWARD_CHAIN_RELS = new Set(['OWNS', 'ULTIMATE_PARENT_OF'])

/** Risk score above which a node overrides every other rule on this page — the indirect filter,
 *  orphan pruning, and for a person the people layer itself. Just under the floor of the
 *  "elevated" band (styles/risk.ts), and mirrored by config.RISK_PIN_FLOOR, which is what makes
 *  the server send a risky person over an off people layer. A lobbying counterparty or a director
 *  scored this high is the whole reason to look at the affiliation network, so no filter takes
 *  them away. */
export const RISK_PIN_FLOOR = 20

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

/** Who is next to whom, over the edges `accept` takes. Edges are two-way unless `inward` claims
 *  one, which then leads from its target to its source only — the way an edge that points at the
 *  chain brings in what it points from, and nothing else. */
function adjacency(
  nodes: LayerGraphNode[],
  edges: LayerGraphEdge[],
  accept: (edge: LayerGraphEdge) => boolean = () => true,
  inward: (edge: LayerGraphEdge) => boolean = () => false,
): Map<string, string[]> {
  const ids = new Set(nodes.map(n => n.id))
  const neighbours = new Map<string, string[]>()
  const link = (from: string, to: string) => {
    const list = neighbours.get(from)
    if (list) list.push(to)
    else neighbours.set(from, [to])
  }
  for (const e of edges) {
    if (e.source === e.target || !ids.has(e.source) || !ids.has(e.target) || !accept(e)) continue
    link(e.target, e.source)
    if (!inward(e)) link(e.source, e.target)
  }
  return neighbours
}

/** Breadth-first over `neighbours` from `starts`, entering only nodes `enter` accepts. */
function reachable(starts: string[], neighbours: Map<string, string[]>, enter: (id: string) => boolean): Set<string> {
  const reached = new Set(starts)
  const queue = [...starts]
  while (queue.length) {
    const id = queue.shift()!
    for (const next of neighbours.get(id) || []) {
      if (reached.has(next) || !enter(next)) continue
      reached.add(next)
      queue.push(next)
    }
  }
  return reached
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
 * Organizations the supply and ownership network does not reach: nothing connects them to a
 * program (or to `keep`, the root) by a chain of contracts and ownership. They are the other
 * companies a supplier's director also sits on the board of, the parent that a shared country
 * pulled in, and — the bulk of them — the trade councils, government bodies and donation
 * recipients a prime is tied to by affiliation alone, and the sister companies that share its
 * owner. RTX's LOBBIES and MEMBER_OF network is hundreds of organizations that no award touches,
 * and hanging off a supplier is not what makes a company part of the chain; a contract, or an
 * ownership stake in something on one, is (CHAIN_RELS, INWARD_CHAIN_RELS).
 *
 * The walk goes from every visible program and kept node over CHAIN_RELS edges whose both ends
 * are visible entities; every organization it never arrives at is returned, an organization with
 * no edges at all included. With nothing to be direct to — no program and no root on the canvas —
 * nothing is indirect.
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
  const neighbours = adjacency(nodes, edges, e => CHAIN_RELS.has(e.type || ''), e => INWARD_CHAIN_RELS.has(e.type || ''))
  const reached = reachable(anchors, neighbours, id => !hidden.has(id) && byId.get(id)!.label === 'Entity')
  return new Set(nodes.filter(n => isOrganization(n) && !hidden.has(n.id) && !reached.has(n.id)).map(n => n.id))
}

const riskScore = (node: LayerNode): number | null => {
  const raw = Number(node.props?.risk_score)
  return Number.isFinite(raw) ? raw : null
}

/**
 * The nodes too risky to filter away: scored above RISK_PIN_FLOOR and joined to a supplier by
 * some path, of any relationship type. This is the one override to everything else the canvas
 * hides — a sanctioned counterparty two hops off a prime, or the director who sits inside both,
 * is the finding, not the clutter — and a pin holds even if the node ends up floating on its own.
 *
 * A pinned person overrides the people layer as well: turning people off is how the canvas gets
 * readable, and it must not be how a designated director disappears. Ordinary people the layer
 * hid conduct nothing (they are not on the canvas, and the server does not even send them), so
 * with people off the path to a supplier has to run through companies and pinned people alone —
 * an org whose only route to the chain was an unremarkable director goes with the layer.
 *
 * Places, categories, documents and claims never conduct: half the canvas is incorporated in the
 * same country and cites the same registry, and a shared attribute is not a connection.
 */
export function riskPinnedNodes(
  nodes: LayerGraphNode[],
  edges: LayerGraphEdge[],
  hidden: Set<string>,
  floor: number = RISK_PIN_FLOOR,
): Set<string> {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const isRisky = (n: LayerNode) => (riskScore(n) ?? 0) > floor
  const conducts = (id: string) => {
    const n = byId.get(id)
    if (!n) return false
    if (n.label === 'Person') return !hidden.has(id) || isRisky(n)
    return n.label === 'Entity' && !hidden.has(id)
  }
  const risky = nodes.filter(n => (isOrganization(n) || n.label === 'Person') && isRisky(n))
  if (!risky.length) return new Set()
  const suppliers = [...new Set(edges.filter(e => e.type === 'SUPPLIES' && byId.has(e.target)).map(e => e.source))].filter(conducts)
  if (!suppliers.length) return new Set()
  const reached = reachable(suppliers, adjacency(nodes, edges), conducts)
  return new Set(risky.filter(n => reached.has(n.id)).map(n => n.id))
}

/** Every node the canvas hides: the off layers, the indirect organizations if that toggle is off,
 *  then whatever organizations the hiding stranded — less the risky ones, which come back at the
 *  end, a pinned person over an off people layer included.
 *
 *  The pins are lifted last, after every rule has run over the graph the layer toggles left. That
 *  order is what keeps a pin to itself: a pinned node is still "hidden" while the prunings look at
 *  its neighbours, so a designated director drawn over an off people layer does not drag their
 *  other three board seats back onto the canvas. */
export function hiddenNodeIds(
  nodes: LayerGraphNode[],
  edges: LayerGraphEdge[],
  enabled: Record<string, boolean>,
  keep: Iterable<string> = [],
): Set<string> {
  const hidden = new Set<string>()
  for (const n of nodes) if (!layerVisible(layerOf(n), enabled)) hidden.add(n.id)
  const pinned = riskPinnedNodes(nodes, edges, hidden)
  if (!indirectOrgsVisible(enabled)) indirectOrganizations(nodes, edges, hidden, keep).forEach(id => hidden.add(id))
  orphanedOrganizations(nodes, edges, hidden, keep).forEach(id => hidden.add(id))
  pinned.forEach(id => hidden.delete(id))
  return hidden
}
