import { indirectOrganizations, RISK_PIN_FLOOR } from './stores/graphLayers.ts'
import type { GNode, GEdge } from './stores/graph'

export interface AffiliationPath { nodes: string[]; edges: string[] }
export interface AffiliationGroup {
  id: string
  anchorId: string
  anchorName: string
  title: string
  members: GNode[]
  paths: Map<string, AffiliationPath>
}
const TITLES: Record<string, string> = {
  LOBBIES: 'Lobbying', DONATED_TO: 'Donations', MEMBER_OF: 'Memberships',
  TRANSACTS_WITH: 'Transactions', OWNS: 'Related companies', ULTIMATE_PARENT_OF: 'Related companies',
  SUPPLIES: 'Related suppliers', HELD_ROLE: 'Shared people',
}
const risky = (n: GNode) => Number(n.props?.risk_score) > RISK_PIN_FLOOR

/** Presentation only: a group is a shortest recorded affiliation path to the supply
 * chain, never a new supply relationship. Places and documents cannot join groups.
 * Stable, multi-source BFS assigns a shared organization to one nearest anchor.
 */
export function affiliationGroups(nodes: GNode[], edges: GEdge[], keep: string[] = []) {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const indirect = indirectOrganizations(nodes, edges, new Set(), keep)
  const anchors = nodes.filter(n => n.label === 'Entity' && !indirect.has(n.id))
    .sort((a, b) => a.id.localeCompare(b.id))
  const adjacency = new Map<string, { id: string; edge: GEdge }[]>()
  for (const edge of edges) {
    if (!TITLES[edge.type] || edge.source === edge.target) continue
    const a = byId.get(edge.source), b = byId.get(edge.target)
    if (!a || !b || !['Entity', 'Person'].includes(a.label) || !['Entity', 'Person'].includes(b.label)) continue
    // Only recorded roles connect a person to an organization.
    if ((a.label === 'Person' || b.label === 'Person') && edge.type !== 'HELD_ROLE') continue
    for (const [from, to] of [[a.id, b.id], [b.id, a.id]]) {
      const list = adjacency.get(from) || []
      list.push({ id: to, edge }); adjacency.set(from, list)
    }
  }
  adjacency.forEach(list => list.sort((a, b) => a.edge.id.localeCompare(b.edge.id)))
  const reached = new Map<string, { anchor: GNode; title: string; path: AffiliationPath }>()
  const queue: string[] = []
  for (const anchor of anchors) {
    reached.set(anchor.id, { anchor, title: '', path: { nodes: [anchor.id], edges: [] } })
    queue.push(anchor.id)
  }
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i], prior = reached.get(id)!
    for (const next of adjacency.get(id) || []) {
      if (reached.has(next.id)) continue
      const board = next.edge.type === 'HELD_ROLE' && /board|director/i.test(`${next.edge.props?.role_type || ''} ${next.edge.props?.title || ''}`)
      const title = prior.title || (board ? 'Board affiliations' : TITLES[next.edge.type])
      reached.set(next.id, { anchor: prior.anchor, title, path: {
        nodes: [...prior.path.nodes, next.id], edges: [...prior.path.edges, next.edge.id],
      } })
      queue.push(next.id)
    }
  }
  const groups = new Map<string, AffiliationGroup>()
  const unconnected: GNode[] = []
  const protectedIds = new Set(nodes.filter(n => ['Entity', 'Person'].includes(n.label) && risky(n)).map(n => n.id))
  const protectedEdges = new Set<string>()
  // Keep the recorded explanation for a significant finding, including hidden people.
  for (const id of [...protectedIds]) {
    reached.get(id)?.path.nodes.forEach(n => protectedIds.add(n))
    reached.get(id)?.path.edges.forEach(e => protectedEdges.add(e))
  }
  for (const id of indirect) {
    const member = byId.get(id)!, route = reached.get(id)
    if (!route) { unconnected.push(member); continue }
    const groupId = `affiliation:${route.anchor.id}:${route.title}`
    let group = groups.get(groupId)
    if (!group) {
      group = { id: groupId, anchorId: route.anchor.id, anchorName: route.anchor.name, title: route.title, members: [], paths: new Map() }
      groups.set(groupId, group)
    }
    group.members.push(member); group.paths.set(id, route.path)
  }
  groups.forEach(g => g.members.sort((a, b) => a.name.localeCompare(b.name)))
  return {
    groups: [...groups.values()].sort((a, b) => a.anchorName.localeCompare(b.anchorName) || a.title.localeCompare(b.title)),
    unconnected: unconnected.sort((a, b) => a.name.localeCompare(b.name)),
    indirect, protectedIds, protectedEdges,
  }
}

/** An expanded group reveals actual nodes and edges, including role bridges while
 * People is off. A selected or searched organization is also revealed with its path.
 */
export function affiliationVisibility(model: ReturnType<typeof affiliationGroups>, expanded: Set<string>, reveal: Set<string> = new Set()) {
  const hidden = new Set(model.indirect)
  const visible = new Set(model.protectedIds)
  const pathEdges = new Set(model.protectedEdges)
  for (const group of model.groups) {
    for (const [member, path] of group.paths) {
      path.nodes.slice(1).forEach(id => hidden.add(id))
      if (expanded.has(group.id) || reveal.has(member) || path.nodes.some(id => reveal.has(id))) {
        path.nodes.forEach(id => visible.add(id))
        path.edges.forEach(id => pathEdges.add(id))
      }
    }
  }
  reveal.forEach(id => visible.add(id))
  visible.forEach(id => hidden.delete(id))
  return { hidden, visible, pathEdges }
}
