interface LayerNode {
  label: string
  layer?: string | null
  props?: Record<string, any>
}

export type GraphLayer =
  | 'people'
  | 'countries'
  | 'categories'
  | 'artifacts'
  | 'sources'
  | 'claims'

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