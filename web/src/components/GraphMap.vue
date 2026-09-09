<template>
  <section class="geo-view" aria-label="Geographic view of the loaded graph">
    <div class="map-summary">
      <div><span class="eyebrow">GEOGRAPHIC EXPOSURE</span><h2>{{ graph.focusLabel || 'Across the graph' }}</h2></div>
      <div class="counts"><strong>{{ data.mappedCount }}</strong> entities placed <span>·</span> <strong>{{ data.unmappedCount }}</strong> not placed</div>
    </div>
    <div class="map-stage">
      <svg ref="svg" :viewBox="viewBox" class="world" aria-label="World map. Scroll to zoom, drag to pan, or select a marker to review its entities." @wheel.prevent="wheelZoom" @pointerdown="startPan" @pointermove="movePan" @pointerup="drag = null" @pointercancel="drag = null">
        <rect x="0" y="0" width="1080" height="540" class="ocean" />
        <path v-for="country in world" :key="country.name" :d="country.path" class="country" :class="{ occupied: occupied.has(country.code) }"><title>{{ country.name }}</title></path>
        <g v-if="showRegions && zoom >= 2" class="subdivisions">
          <path v-for="region in visibleRegions" :key="region.id" :d="region.path" class="region" :class="{ occupied: occupiedRegions.has(region.code) }"><title>{{ region.name }} ({{ region.code || region.country }})</title></path>
          <template v-if="zoom >= 4">
            <text v-for="region in regionLabels" :key="`label:${region.id}`" :x="(region.longitude + 180) * 3" :y="(90 - region.latitude) * 3" :font-size="10.5 / (zoom * mapScale)" class="region-label">{{ region.name }}</text>
          </template>
        </g>
        <g v-for="place in places" :key="place.key" :transform="`translate(${(place.longitude + 180) * 3},${(90 - place.latitude) * 3})`"
           class="marker" :class="{ active: selectedKey === place.key, precise: place.precise, regional: place.region, traced: traced(place) }" tabindex="0" role="button"
           :aria-label="`${place.name}: ${entityCount(place)} entities, ${place.precise ? 'supplied coordinates' : place.region ? 'state/province-level placement' : 'country-level placement'}`"
           @pointerdown.stop @click.stop="selectedKey = place.key" @keydown.enter.prevent="selectedKey = place.key" @keydown.space.prevent="selectedKey = place.key">
          <title>{{ place.name }} · {{ entityCount(place) }} entities</title>
          <circle :r="(selectedKey === place.key ? 13 : 10) / (zoom * mapScale)" />
          <text :font-size="11 / (zoom * mapScale)" text-anchor="middle" dominant-baseline="central">{{ entityCount(place) }}</text>
        </g>
      </svg>
      <label class="detail-toggle"><input v-model="showRegions" type="checkbox" /> States &amp; provinces <small v-if="showRegions && zoom < 2">Zoom in to see boundaries</small></label>
      <div class="zoom-tools" aria-label="Map zoom controls">
        <button aria-label="Zoom in" :disabled="zoom >= 20" @click="zoom = Math.min(20, zoom + .5)">+</button>
        <button aria-label="Zoom out" :disabled="zoom <= 1" @click="zoom = Math.max(1, zoom - .5)">−</button>
        <button @click="zoom = 1; center = [540, 270]">Reset</button>
      </div>
      <p v-if="!places.length" class="map-empty" role="status">{{ graph.loading ? 'Loading locations…' : graph.filter ? 'No mapped entities match your search.' : 'No geographic locations in this graph scope. Try a deeper traversal or another program.' }}</p>
      <a class="attribution" href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener">Natural Earth · illustrative boundaries</a>
    </div>
    <div class="map-details">
      <div class="detail-heading">
        <label>Location <select v-model="selectedKey" aria-label="Map location"><option value="">All locations ({{ places.length }})</option><option v-for="place in places" :key="place.key" :value="place.key">{{ place.name }} ({{ entityCount(place) }})</option></select></label>
        <span>Gold: country · Blue: state/province · Teal: coordinates. Area markers are approximate.</span>
      </div>
      <div class="entry-list">
        <div v-for="{ entry, place } in entries" :key="`${place.key}:${entry.node.id}:${entry.edge?.id || ''}`" class="entry" :class="{ selected: graph.selectedId === entry.node.id }">
          <button class="entity-button" @click="inspect(entry.node.id)"><strong>{{ entry.node.name }}</strong><small>{{ place.name }} · {{ entry.location?.props.code || (place.precise ? 'Supplied coordinates' : 'Country-level') }}<span v-if="entry.node.props.simulated || entry.edge?.props.simulated"> · Simulated</span></small></button>
          <button v-if="entry.edge" class="relation-button" @click="graph.selectEdge(entry.edge.id); emit('select')">{{ entry.edge.type.replaceAll('_', ' ').toLowerCase() }} ↗</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { hiddenNodeIds } from '../stores/graphLayers'
import { buildMapPlaces, matchesMapEntry, type MapPlace } from '../graphMap'
import world from '../data/worldMap.json'
import regions from '../data/mapRegions.json'
const graph = useGraph()
const workspace = useWorkspace()
const props = defineProps<{ locationCode?: string }>()
const emit = defineEmits<{ select: [] }>()
const selectedKey = ref('')
const zoom = ref(1)
const showRegions = ref(true)
const center = ref<[number, number]>([540, 270])
const svg = ref<SVGSVGElement>()
const mapScale = ref(1)
let mapObserver: ResizeObserver | undefined
onMounted(() => {
  mapObserver = new ResizeObserver(() => {
    if (svg.value) mapScale.value = Math.max(.01, Math.min(svg.value.clientWidth / 1080, svg.value.clientHeight / 540))
  })
  if (svg.value) mapObserver.observe(svg.value)
})
onBeforeUnmount(() => mapObserver?.disconnect())
const drag = ref<{ x: number; y: number; center: [number, number] } | null>(null)
const viewBox = computed(() => `${center.value[0] - 540 / zoom.value} ${center.value[1] - 270 / zoom.value} ${1080 / zoom.value} ${540 / zoom.value}`)
const data = computed(() => {
  const hidden = hiddenNodeIds(graph.nodeList, graph.edgeList, { ...workspace.ws.layers, countries: true }, graph.focusId ? [graph.focusId] : [])
  return buildMapPlaces(graph.nodeList.filter(node => !hidden.has(node.id)), graph.edgeList, world, regions)
})
const places = computed(() => data.value.places.map(place => ({ ...place, entries: place.entries.filter(entry => matchesMapEntry(entry, graph.filter)) })).filter(place => place.entries.length))
const occupied = computed(() => new Set(places.value.filter(p => p.key.startsWith('country:')).map(p => p.key.slice(8))))
const occupiedRegions = computed(() => new Set(places.value.filter(p => p.region).map(p => p.key.slice(7))))
const visibleRegions = computed(() => regions.filter(region => {
  const [left, top, right, bottom] = region.bounds
  return right >= center.value[0] - 540 / zoom.value && left <= center.value[0] + 540 / zoom.value
    && bottom >= center.value[1] - 270 / zoom.value && top <= center.value[1] + 270 / zoom.value
}))
const regionLabels = computed(() => {
  const boxes: number[][] = []
  const unit = 1 / (zoom.value * mapScale.value)
  return [...visibleRegions.value].sort((a,b) => Number(occupiedRegions.value.has(b.code)) - Number(occupiedRegions.value.has(a.code))).filter(region => {
    const x = (region.longitude + 180) * 3, y = (90 - region.latitude) * 3
    if (x < center.value[0] - 540 / zoom.value || x > center.value[0] + 540 / zoom.value || y < center.value[1] - 270 / zoom.value || y > center.value[1] + 270 / zoom.value) return false
    const halfWidth = (region.name.length * 3 + 5) * unit
    const box = [x - halfWidth, y - 12 * unit, x + halfWidth, y + 4 * unit]
    if (boxes.some(b => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) return false
    boxes.push(box)
    return true
  })
})
const entries = computed(() => places.value.filter(p => !selectedKey.value || p.key === selectedKey.value).flatMap(place => place.entries.map(entry => ({ entry, place }))))
watch(() => props.locationCode, code => {
  if (!code) return
  const normalized = code.toUpperCase()
  const region = regions.find(r => r.code === normalized)
  const country = world.find(c => c.code === normalized.split('-')[0])
  const location = region || country
  if (!location) return
  center.value = [(location.longitude + 180) * 3, (90 - location.latitude) * 3]
  if (region) {
    const [left, top, right, bottom] = region.bounds
    zoom.value = Math.max(2, Math.min(20, Math.min(1080 / Math.max(right - left, 1), 540 / Math.max(bottom - top, 1)) * .65))
    showRegions.value = true
  } else {
    const points = country!.path.match(/-?\d+(?:\.\d+)?/g)!.map(Number)
    const xs = points.filter((_, i) => i % 2 === 0), ys = points.filter((_, i) => i % 2 === 1)
    zoom.value = Math.max(2, Math.min(12, Math.min(1080 / Math.max(Math.max(...xs) - Math.min(...xs), 1), 540 / Math.max(Math.max(...ys) - Math.min(...ys), 1)) * .8))
  }
  selectedKey.value = `${region ? 'region' : 'country'}:${location.code}`
}, { immediate: true })
function entityCount(place: MapPlace) { return new Set(place.entries.map(e => e.node.id)).size }
function traced(place: MapPlace) { return place.entries.some(e => graph.highlightIds.includes(e.node.id) || (e.edge && graph.highlightIds.includes(e.edge.id)) || graph.selectedId === e.node.id) }
function inspect(id: string) { graph.select(id); emit('select') }
watch(places, value => { if (!value.some(p => p.key === selectedKey.value)) selectedKey.value = '' })
function wheelZoom(event: WheelEvent) {
  const matrix = svg.value?.getScreenCTM()
  if (!matrix || !event.deltaY) return
  // Convert the cursor through the SVG transform, including its letterboxing.
  const anchor = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? svg.value!.clientHeight : 1
  const delta = Math.max(-100, Math.min(100, event.deltaY * unit))
  const nextZoom = Math.max(1, Math.min(20, zoom.value * Math.exp(-delta * .002)))
  const ratio = zoom.value / nextZoom
  center.value = [anchor.x + (center.value[0] - anchor.x) * ratio, anchor.y + (center.value[1] - anchor.y) * ratio]
  zoom.value = nextZoom
  drag.value = null
}
function startPan(event: PointerEvent) {
  if (event.button !== 0 || !svg.value) return
  svg.value.setPointerCapture(event.pointerId)
  drag.value = { x: event.clientX, y: event.clientY, center: [...center.value] }
}
function movePan(event: PointerEvent) {
  if (!drag.value || !svg.value) return
  const rect = svg.value.getBoundingClientRect()
  const scale = Math.min(rect.width / (1080 / zoom.value), rect.height / (540 / zoom.value))
  center.value = [Math.max(0, Math.min(1080, drag.value.center[0] - (event.clientX - drag.value.x) / scale)), Math.max(0, Math.min(540, drag.value.center[1] - (event.clientY - drag.value.y) / scale))]
}
</script>

<style scoped>
.geo-view { height:100%; padding:112px 16px 12px; display:flex; flex-direction:column; background:rgb(var(--v-theme-background)); }
.map-summary { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:6px 4px 12px; flex-wrap:wrap; }
.eyebrow { font-size:10px; letter-spacing:.14em; color:rgb(var(--v-theme-primary)); font-weight:800; }
h2 { font-size:20px; font-weight:600; }.counts { font-size:12px; opacity:.85; }.counts strong { font-size:18px; }.counts span { margin:0 8px; }
.map-stage { position:relative; flex:1; min-height:180px; border:1px solid rgba(128,128,128,.25); border-radius:10px; overflow:hidden; background:#102b38; }
.world { width:100%; height:100%; display:block; touch-action:none; cursor:grab; }.world:active { cursor:grabbing; }
.ocean { fill:#102b38; }.country { fill:#294653; stroke:#6c8490; stroke-width:.5; }.country.occupied { fill:#346f78; }
.marker { cursor:pointer; outline:none; }.marker circle { fill:#f3c97c; stroke:#102b38; stroke-width:2; vector-effect:non-scaling-stroke; }.marker.regional circle { fill:#99bfff; }.marker.precise circle { fill:#79dac7; }.marker.active circle,.marker:focus circle,.marker.traced circle { stroke:#fff; stroke-width:3; }.marker text { fill:#102b38; font-weight:800; pointer-events:none; }
.region { fill:transparent; stroke:#94afbb; stroke-width:.65; vector-effect:non-scaling-stroke; }
.region.occupied { fill:#5f8eaa44; }
.region-label { fill:#d8e5ed; text-anchor:middle; pointer-events:none; paint-order:stroke; stroke:#102b38; stroke-width:2px; vector-effect:non-scaling-stroke; }
.detail-toggle { position:absolute; left:8px; top:8px; padding:5px 7px; background:#102b38e8; color:#edf5f7; font-size:11px; border-radius:4px; }
.detail-toggle input { vertical-align:middle; margin-right:4px; accent-color:#99bfff; }
.detail-toggle small { display:block; padding-left:17px; color:#b5ccd6; }
.zoom-tools { position:absolute; right:10px; top:10px; display:flex; gap:2px; }.zoom-tools button { padding:5px 10px; background:#f5f6ef; color:#183943; border-radius:3px; font-weight:700; }.zoom-tools button:disabled { opacity:.45; }
.attribution { position:absolute; bottom:4px; right:8px; font-size:9px; color:#d6e4e8; }.map-empty { position:absolute; left:15%; right:15%; top:40%; padding:15px; background:#102b38e8; color:#fff; text-align:center; font-size:13px; }
.map-details { flex:0 1 210px; min-height:100px; display:flex; flex-direction:column; padding-top:12px; }.detail-heading { display:flex; align-items:center; gap:16px; padding-bottom:8px; }.detail-heading label { font-size:12px; font-weight:700; white-space:nowrap; }.detail-heading select { margin-left:6px; padding:5px; border:1px solid #8886; border-radius:4px; color:inherit; max-width:220px; }.detail-heading option { color:#172f35; background:#fff; }.detail-heading span { font-size:10px; opacity:.7; }
.entry-list { overflow:auto; }.entry { display:flex; justify-content:space-between; align-items:center; border-top:1px solid #8883; gap:10px; }.entry.selected { background:rgba(var(--v-theme-primary),.12); }.entity-button { padding:8px 6px; text-align:left; flex:1; min-width:0; }.entity-button strong { display:block; font-size:12px; }.entity-button small { display:block; font-size:10px; opacity:.7; }.relation-button { font-size:10px; color:rgb(var(--v-theme-primary)); text-align:right; padding:8px; }
button:focus-visible,select:focus-visible { outline:2px solid rgb(var(--v-theme-primary)); outline-offset:2px; }
@media(max-width:900px) { .geo-view { padding-top:212px; min-height:710px; }.detail-heading { flex-wrap:wrap; gap:4px; }.map-summary { padding-bottom:4px; } h2 { font-size:16px; } .map-details { flex-basis:150px; } }
</style>
