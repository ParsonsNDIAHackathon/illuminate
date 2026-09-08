type FocusNode = { id: string }
type FocusEdge = { id: string; source: string; target: string; type: string }

const FAMILY_EDGES: Record<string, Set<string>> = {
  ownership: new Set(['OWNS', 'ULTIMATE_PARENT_OF', 'BENEFICIAL_OWNER_OF', 'PARENT_SEATED_IN']),
  concentration: new Set(['SUPPLIES']),
  people: new Set(['HELD_ROLE']),
  sanctions: new Set(['EVIDENCES', 'ASSERTS', 'TARGETS', 'ABOUT']),
  financial: new Set(['EVIDENCES', 'ASSERTS', 'ABOUT']),
  media: new Set(['EVIDENCES', 'ASSERTS', 'ABOUT']),
}
type Step = { edge: string; node: string }

function stableSteps(edges: FocusEdge[], nodeId: string, allowed: Set<string>, supplyTowardVendor = false): Step[] {
  return edges
    .filter(e => allowed.has(e.type) && (supplyTowardVendor ? e.target === nodeId : (e.source === nodeId || e.target === nodeId)))
    .map(e => ({ edge: e.id, node: supplyTowardVendor ? e.source : (e.source === nodeId ? e.target : e.source) }))
    .sort((a, b) => `${a.node}\u0000${a.edge}`.localeCompare(`${b.node}\u0000${b.edge}`))
}

function stablePath(edges: FocusEdge[], from: string, to: string, allowed: Set<string>, supplyTowardVendor = false): string[] {
  if (from === to) return [from]
  const queue: { node: string; path: string[] }[] = [{ node: from, path: [from] }]
  const seen = new Set([from])
  while (queue.length) {
    const current = queue.shift()!
    for (const step of stableSteps(edges, current.node, allowed, supplyTowardVendor)) {
      if (seen.has(step.node)) continue
      const path = [...current.path, step.edge, step.node]
      if (step.node === to) return path
      seen.add(step.node); queue.push({ node: step.node, path })
    }
  }
  return []
}

function betterPath(paths: string[][]): string[] {
  return paths.filter(p => p.length).sort((a, b) => a.length - b.length || a.join('\u0000').localeCompare(b.join('\u0000')))[0] || []
}

export function deriveFindingPath(
  nodes: FocusNode[],
  edges: FocusEdge[],
  focusIds: string[],
  vendorId: string,
  rootId: string | null,
  family: string,
) {
  const nodeIds = new Set(nodes.map(n => n.id)); const edgeById = new Map(edges.map(e => [e.id, e]))
  const availableFocusIds = focusIds.filter(id => nodeIds.has(id) || edgeById.has(id))
  const unavailableIds = focusIds.filter(id => !nodeIds.has(id) && !edgeById.has(id))
  const pathIds = new Set<string>(vendorId ? [vendorId] : [])
  if (!vendorId || !nodeIds.has(vendorId)) return { pathIds, riskIds: new Set<string>(), unavailableIds }
  if (rootId && nodeIds.has(rootId)) stablePath(edges, rootId, vendorId, new Set(['SUPPLIES']), true).forEach(id => pathIds.add(id))
  const allowed = FAMILY_EDGES[family] || new Set<string>()
  const riskIds = new Set<string>()
  for (const id of availableFocusIds) {
    const edge = edgeById.get(id)
    const targets = edge ? [edge.source, edge.target].sort() : [id]
    betterPath(targets.map(target => stablePath(edges, vendorId, target, allowed))).forEach(part => pathIds.add(part))
    pathIds.add(id); riskIds.add(id)
    if (edge) { pathIds.add(edge.source); pathIds.add(edge.target) }
  }
  return { pathIds, riskIds, unavailableIds }
}