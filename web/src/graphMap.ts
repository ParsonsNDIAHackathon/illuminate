import type { GNode, GEdge } from './stores/graph.ts'

export interface Country { code: string; name: string; latitude: number; longitude: number }
export interface MapEntry { node: GNode; edge?: GEdge; location?: GNode }
export interface MapPlace { key: string; name: string; latitude: number; longitude: number; precise: boolean; region?: boolean; entries: MapEntry[] }
const locationRelations = new Set(['OPERATES_IN', 'INCORPORATED_IN', 'PARENT_SEATED_IN', 'MANUFACTURES_IN', 'LOCATED_IN', 'HEADQUARTERED_IN'])

function coordinates(props: Record<string, unknown>): [number, number] | null {
  const { latitude, longitude } = props
  if ([latitude, longitude].some(v => v === null || v === undefined || typeof v === 'boolean' || String(v).trim() === '')) return null
  const lat = Number(latitude), lon = Number(longitude)
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lat, lon] : null
}

/** Only explicit coordinates and geographic relationships place entities on the map. */
export function buildMapPlaces(nodes: GNode[], edges: GEdge[], countries: Country[], regions: Country[] = []) {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const countryByCode = new Map(countries.map(c => [c.code, c]))
  const regionByCode = new Map(regions.filter(r => r.code && r.code !== '-99').map(r => [r.code, r]))
  const places = new Map<string, MapPlace>()
  const mapped = new Set<string>()
  function add(location: GNode, entry: MapEntry) {
    const coords = coordinates(location.props)
    const code = String(location.props.code || '').toUpperCase()
    const country = countryByCode.get(code.split('-')[0])
    const region = regionByCode.get(code)
    const area = region || country
    if (!coords && !area) return
    const key = coords ? `point:${coords.join(',')}` : `${region ? 'region' : 'country'}:${area!.code}`
    if (!places.has(key)) places.set(key, {
      key, name: coords ? location.name : region ? `${region.name}, ${country?.name || code.split('-')[0]}` : country!.name,
      latitude: coords?.[0] ?? area!.latitude, longitude: coords?.[1] ?? area!.longitude,
      precise: !!coords, region: !coords && !!region, entries: [],
    })
    const place = places.get(key)!
    if (!place.entries.some(e => e.node.id === entry.node.id && e.edge?.id === entry.edge?.id)) place.entries.push(entry)
    mapped.add(entry.node.id)
  }
  for (const node of nodes) {
    if (['Entity', 'Person'].includes(node.label) && coordinates(node.props)) add(node, { node })
  }
  for (const edge of edges) {
    if (!locationRelations.has(edge.type)) continue
    const source = byId.get(edge.source), target = byId.get(edge.target)
    if (!source || !target || target.label !== 'Location') continue
    add(target, { node: source, edge, location: target })
  }
  const eligible = nodes.filter(n => ['Entity', 'Person'].includes(n.label))
  return { places: [...places.values()].sort((a, b) => a.name.localeCompare(b.name)),
    mappedCount: eligible.filter(n => mapped.has(n.id)).length,
    unmappedCount: eligible.filter(n => !mapped.has(n.id)).length }
}

export function matchesMapEntry(entry: MapEntry, query: string) {
  const text = [entry.node.name, ...Object.values(entry.node.props), entry.location?.name, entry.location?.props.code, entry.edge?.type].join(' ').toLowerCase()
  return query.toLowerCase().trim().split(/\s+/).every(word => text.includes(word))
}
