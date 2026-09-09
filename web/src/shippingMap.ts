import type { GNode, GEdge } from './stores/graph.ts'
export type TransportMode = 'ocean' | 'truck' | 'rail'
export type RouteStatus = 'confirmed' | 'inferred' | 'illustrative'
export interface ShippingPoint { latitude: number; longitude: number }
export interface ShippingPort extends ShippingPoint { id: string; name: string; country: string; kind?: 'port' | 'hub' | 'intermodal' }
export interface ShippingRoute {
  id: string; name: string; supplier_id: string; customer_id: string; relationship_id: string
  goods: string; status: RouteStatus; source: { title: string; reference: string }; updated_at: string; notes: string
  segments: ShippingSegment[]
}
export interface ShippingSegment { from_port: string; to_port: string; waypoints: ShippingPoint[]; passages: string[]; mode?: TransportMode; source?: { title: string; reference: string } }
export interface TransportCorridor { id: string; name: string; mode: 'truck' | 'rail'; stops: string[]; points: ShippingPoint[]; source: { title: string; reference: string }; updated_at: string; notes: string }
export interface ShippingCatalog { ports: ShippingPort[]; routes: ShippingRoute[] }
export interface LinkedRoute { route: ShippingRoute; supplier: GNode; customer: GNode; edge: GEdge }

/** Exact directional relationship matching prevents attaching a lane to a namesake or stale edge. */
export function linkedShippingRoutes(catalog: ShippingCatalog, nodes: GNode[], edges: GEdge[], query = ''): LinkedRoute[] {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const byEdge = new Map(edges.map(e => [e.id, e]))
  const ports = new Map(catalog.ports.map(p => [p.id, p]))
  return catalog.routes.flatMap(route => {
    const supplier = byId.get(route.supplier_id), customer = byId.get(route.customer_id), edge = byEdge.get(route.relationship_id)
    if (!supplier || !customer || !edge || edge.type !== 'SUPPLIES' || edge.source !== supplier.id || edge.target !== customer.id) return []
    const text = [supplier.name, customer.name, route.name, route.goods, ...route.segments.flatMap(s => [ports.get(s.from_port)?.name, ports.get(s.to_port)?.name, ...s.passages, s.mode || 'ocean'])].join(' ').toLowerCase()
    if (!query.toLowerCase().trim().split(/\s+/).every(word => text.includes(word))) return []
    return [{ route, supplier, customer, edge }]
  })
}

/** Break at ±180° so a Pacific lane never draws across the Atlantic. */
export function shippingPath(points: ShippingPoint[]): string {
  if (!points.length) return ''
  const project = (lon: number, lat: number) => `${(lon + 180) * 3},${(90 - lat) * 3}`
  let path = `M${project(points[0].longitude, points[0].latitude)}`
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i], delta = b.longitude - a.longitude
    if (Math.abs(delta) > 180) {
      const end = b.longitude + (delta > 0 ? -360 : 360)
      const boundary = delta > 0 ? -180 : 180
      const fraction = (boundary - a.longitude) / (end - a.longitude)
      const latitude = a.latitude + (b.latitude - a.latitude) * fraction
      path += ` L${project(boundary, latitude)} M${project(-boundary, latitude)}`
    }
    path += ` L${project(b.longitude, b.latitude)}`
  }
  return path
}

export function routePath(route: ShippingRoute, ports: ShippingPort[]): string {
  const byId = new Map(ports.map(p => [p.id, p]))
  return route.segments.map(s => {
    const a = byId.get(s.from_port), b = byId.get(s.to_port)
    return a && b ? shippingPath([a, ...s.waypoints, b]) : ''
  }).join(' ')
}
export function usesPort(route: ShippingRoute, port: string) {
  return route.segments.some(s => s.from_port === port || s.to_port === port)
}


export function segmentPath(segment: ShippingSegment, ports: ShippingPort[]): string {
  const a = ports.find(p => p.id === segment.from_port), b = ports.find(p => p.id === segment.to_port)
  return a && b ? shippingPath([a, ...segment.waypoints, b]) : ''
}
export function matchesMode(route: ShippingRoute, mode: TransportMode | '') {
  return !mode || route.segments.some(s => (s.mode || 'ocean') === mode)
}
export function safeSourceLink(reference: string | undefined): string {
  try { const url = new URL(reference || ''); return ['http:', 'https:'].includes(url.protocol) ? url.href : '' } catch { return '' }
}
