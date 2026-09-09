<template>
  <section class="geo-view" aria-label="Geographic view of the loaded graph">
    <div class="map-summary">
      <div><span class="eyebrow">GEOGRAPHIC EXPOSURE</span><h2>{{ graph.focusLabel || 'Across the graph' }}</h2></div>
      <div class="counts"><strong>{{ data.mappedCount }}</strong> entities placed <span>·</span> <strong>{{ data.unmappedCount }}</strong> not placed</div>
    </div>
    <form class="news-search" @submit.prevent="news.search()">
      <v-checkbox v-model="shipping.visible" label="Shipping" density="compact" hide-details class="news-toggle" />
      <v-checkbox v-model="news.visible" label="News" density="compact" hide-details class="news-toggle" />
      <v-text-field v-model="news.query" label="News topic" placeholder="Search recent news…" density="compact" variant="outlined" hide-details maxlength="250" class="news-topic" />
      <v-select v-model="news.timespan" :items="timeWindows" label="News time window" density="compact" variant="outlined" hide-details class="news-window" />
      <v-btn type="submit" size="small" color="primary" variant="tonal" prepend-icon="mdi-magnify" :loading="news.loading" :disabled="news.loading || news.query.trim().length < 2">Search GDELT</v-btn>
    </form>
    <v-alert v-if="news.error" type="warning" variant="tonal" density="compact" class="mb-2 news-error" role="alert">
      {{ news.error }} <span v-if="news.result">Previous results are still shown below.</span>
    </v-alert>
    <v-alert v-if="news.visible && news.result?.stale" type="warning" variant="tonal" density="compact" class="mb-2" role="status">
      {{ news.result.notice }} Saved {{ new Date(news.result.fetched_at!).toLocaleString() }}.
    </v-alert>
    <TransportControls @focus-us="zoom = 4.8; center = [253.5, 159]" />
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
        <TransportLayer />
        <g v-for="place in places" :key="place.key" :transform="`translate(${(place.longitude + 180) * 3},${(90 - place.latitude) * 3})`"
           class="marker" :class="{ active: selectedKey === place.key, precise: place.precise, regional: place.region, traced: traced(place) }" tabindex="0" role="button"
           :aria-label="`${place.name}: ${entityCount(place)} entities, ${place.precise ? 'supplied coordinates' : place.region ? 'state/province-level placement' : 'country-level placement'}`"
           @pointerdown.stop @click.stop="selectedKey = place.key" @keydown.enter.prevent="selectedKey = place.key" @keydown.space.prevent="selectedKey = place.key">
          <title>{{ place.name }} · {{ entityCount(place) }} entities</title>
          <circle :r="(selectedKey === place.key ? 13 : 10) / (zoom * mapScale)" />
          <text :font-size="11 / (zoom * mapScale)" text-anchor="middle" dominant-baseline="central">{{ entityCount(place) }}</text>
        </g>
        <g v-for="place in news.visible ? newsData.places : []" :key="`news:${place.code}`"
           :transform="`translate(${(place.longitude + 180) * 3},${(90 - place.latitude) * 3})`"
           class="marker news-marker" :class="{ active: news.location === place.code }" tabindex="0" role="button"
           :aria-label="`${place.name}: ${place.articles.length} news articles; approximate country mention`"
           @pointerdown.stop @click.stop="news.location = place.code" @keydown.enter.prevent="news.location = place.code" @keydown.space.prevent="news.location = place.code">
          <title>{{ place.name }} · {{ place.articles.length }} news articles · Country mentioned in headline</title>
          <path :d="`M0,${-25 / (zoom * mapScale)} l${7 / (zoom * mapScale)},${7 / (zoom * mapScale)} l${-7 / (zoom * mapScale)},${7 / (zoom * mapScale)} l${-7 / (zoom * mapScale)},${-7 / (zoom * mapScale)} Z`" />
        </g>
        <ShippingLayer :scale="zoom * mapScale" :show-labels="zoom >= 2" />
      </svg>
      <v-sheet class="detail-toggle" rounded>
        <v-checkbox v-model="showRegions" label="States & provinces" density="compact" hide-details />
        <div v-if="showRegions && zoom < 2" class="text-caption">Zoom in to see boundaries</div>
      </v-sheet>
      <v-btn-group class="zoom-tools" density="compact" aria-label="Map zoom controls">
        <v-btn icon="mdi-plus" aria-label="Zoom in" size="small" :disabled="zoom >= 20" @click="zoom = Math.min(20, zoom + .5)" />
        <v-btn icon="mdi-minus" aria-label="Zoom out" size="small" :disabled="zoom <= 1" @click="zoom = Math.max(1, zoom - .5)" />
        <v-btn size="small" @click="zoom = 1; center = [540, 270]">Reset</v-btn>
      </v-btn-group>
      <p v-if="!places.length && !(news.visible && newsData.places.length) && !(shipping.visible && shipping.routes.length) && !transport.visible.length" class="map-empty" role="status">{{ graph.loading ? 'Loading locations…' : graph.filter ? 'No mapped entities match your search.' : 'No geographic locations in this graph scope. Try a deeper traversal or another program.' }}</p>
      <a class="attribution" href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener">Natural Earth · illustrative boundaries</a>
    </div>
    <ShippingPanel />
    <div v-if="news.visible" class="news-details">
      <div class="detail-heading">
        <v-select v-model="news.location" :items="newsLocations" label="News location" density="compact" variant="outlined" hide-details class="location-select" />
        <span>Coral diamonds: approximate country mentions. <template v-if="news.result">“{{ news.result.query }}” · past {{ news.result.timespan }} · {{ newsData.mapped }} mapped, {{ newsData.unmapped.length }} unplaced.</template></span>
        <span v-if="news.result?.fetched_at" class="text-caption">{{ news.result.cached ? 'Cached' : 'Retrieved' }} {{ new Date(news.result.fetched_at).toLocaleString() }} · reused for 15 minutes.</span>
      </div>
      <v-progress-linear v-if="news.loading" indeterminate color="primary" aria-label="Searching recent coverage" />
      <p v-if="news.result && !newsArticles.length" class="text-caption pa-2" role="status">No articles found for this selection. Try another topic or a longer time window.</p>
      <v-list class="entry-list" density="compact" aria-label="News articles">
        <v-list-item v-for="article in newsArticles" :key="article.url" class="news-article" :active="news.selectedUrl === article.url" color="primary"
                     :title="article.title || article.url" :subtitle="`${article.domain} · Seen ${newsDate(article.seendate) || 'date unavailable'}`"
                     @click="emit('select-news', article)">
          <template #append><v-icon icon="mdi-chevron-right" size="small" /></template>
        </v-list-item>
      </v-list>
    </div>
    <div class="map-details">
      <div class="detail-heading">
        <v-select v-model="selectedKey" :items="entityLocations" label="Map location" density="compact" variant="outlined" hide-details class="location-select" />
        <span>Gold: country · Blue: state/province · Teal: coordinates. Area markers are approximate.</span>
      </div>
      <v-list class="entry-list" density="compact" aria-label="Mapped entities">
        <v-list-item v-for="{ entry, place } in entries" :key="`${place.key}:${entry.node.id}:${entry.edge?.id || ''}`" :active="graph.selectedId === entry.node.id"
                     :title="entry.node.name" :subtitle="`${place.name} · ${entry.location?.props.code || (place.precise ? 'Supplied coordinates' : 'Country-level')}${entry.node.props.simulated || entry.edge?.props.simulated ? ' · Simulated' : ''}`"
                     @click="inspect(entry.node.id)">
          <template #append>
            <v-btn v-if="entry.edge" size="x-small" variant="text" @click.stop="graph.selectEdge(entry.edge.id); emit('select')">{{ entry.edge.type.replaceAll('_', ' ').toLowerCase() }} ↗</v-btn>
          </template>
        </v-list-item>
      </v-list>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import TransportControls from './TransportControls.vue'
import TransportLayer from './TransportLayer.vue'
import { useTransport } from '../stores/transport'
import ShippingLayer from './ShippingLayer.vue'
import ShippingPanel from './ShippingPanel.vue'
import { useShipping } from '../stores/shipping'
import { useNews } from '../stores/news'
import { mapNews, newsDate, type NewsArticle } from '../newsMap'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import { hiddenNodeIds } from '../stores/graphLayers'
import { buildMapPlaces, matchesMapEntry, type MapPlace } from '../graphMap'
import world from '../data/worldMap.json'
import regions from '../data/mapRegions.json'
const graph = useGraph()
const workspace = useWorkspace()
const props = defineProps<{ locationCode?: string }>()
const emit = defineEmits<{ select: []; 'select-news': [article: NewsArticle] }>()
const selectedKey = ref('')
const news = useNews()
const shipping = useShipping()
const transport = useTransport()
const timeWindows = [{ title: 'Past 24 hours', value: '24h' }, { title: 'Past 3 days', value: '3d' }, { title: 'Past 7 days', value: '7d' }]
const newsData = computed(() => mapNews(news.result?.articles || [], world))
const newsArticles = computed(() => news.location === 'unplaced' ? newsData.value.unmapped
  : news.location ? newsData.value.places.find(place => place.code === news.location)?.articles || [] : news.result?.articles || [])
const newsLocations = computed(() => [{ title: 'All news', value: '' }, { title: `Unplaced (${newsData.value.unmapped.length})`, value: 'unplaced' },
  ...newsData.value.places.map(place => ({ title: `${place.name} (${place.articles.length})`, value: place.code }))])
onMounted(() => news.ensureLoaded())
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
const entityLocations = computed(() => [{ title: `All locations (${places.value.length})`, value: '' }, ...places.value.map(place => ({ title: `${place.name} (${entityCount(place)})`, value: place.key }))])
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
.news-search { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:8px; }
.news-toggle { flex:0 0 auto; }
.news-topic { flex:1 1 180px; }
.news-window { flex:0 1 170px; min-width:150px; }
.news-error { flex-shrink:0; }
.news-marker path { fill:#ff927f; stroke:#102b38; stroke-width:1.5; vector-effect:non-scaling-stroke; }
.news-marker.active path,.news-marker:focus path { stroke:white; stroke-width:3; }
.news-details { flex:0 1 170px; min-height:90px; display:flex; flex-direction:column; padding-top:10px; font-size:12px; }
.news-article :deep(.v-list-item-title) { white-space:normal; font-size:12px; }
.geo-view { height:calc(100% - 112px); margin-top:112px; overflow-y:auto; padding:0 16px 12px; display:flex; flex-direction:column; background:rgb(var(--v-theme-background)); }
.map-summary { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:6px 4px 12px; flex-wrap:wrap; }
.eyebrow { font-size:10px; letter-spacing:.14em; color:rgb(var(--v-theme-primary)); font-weight:800; }
h2 { font-size:20px; font-weight:600; }.counts { font-size:12px; opacity:.85; }.counts strong { font-size:18px; }.counts span { margin:0 8px; }
.map-stage { position:relative; flex:1; min-height:300px; border:1px solid rgba(128,128,128,.25); border-radius:10px; overflow:hidden; background:#102b38; }
.world { width:100%; height:100%; display:block; touch-action:none; cursor:grab; }.world:active { cursor:grabbing; }
.ocean { fill:#102b38; }.country { fill:#294653; stroke:#6c8490; stroke-width:.5; }.country.occupied { fill:#346f78; }
.marker { cursor:pointer; outline:none; }.marker circle { fill:#f3c97c; stroke:#102b38; stroke-width:2; vector-effect:non-scaling-stroke; }.marker.regional circle { fill:#99bfff; }.marker.precise circle { fill:#79dac7; }.marker.active circle,.marker:focus circle,.marker.traced circle { stroke:#fff; stroke-width:3; }.marker text { fill:#102b38; font-weight:800; pointer-events:none; }
.region { fill:transparent; stroke:#94afbb; stroke-width:.65; vector-effect:non-scaling-stroke; }
.region.occupied { fill:#5f8eaa44; }
.region-label { fill:#d8e5ed; text-anchor:middle; pointer-events:none; paint-order:stroke; stroke:#102b38; stroke-width:2px; vector-effect:non-scaling-stroke; }
.detail-toggle { position:absolute; left:8px; top:8px; padding:0 8px; max-width:230px; }
.detail-toggle .text-caption { padding:0 8px 6px; }
.zoom-tools { position:absolute; right:10px; top:10px; }
.attribution { position:absolute; bottom:4px; right:8px; font-size:9px; color:#d6e4e8; }.map-empty { position:absolute; left:15%; right:15%; top:40%; padding:15px; background:#102b38e8; color:#fff; text-align:center; font-size:13px; }
.map-details { flex:0 1 180px; min-height:100px; display:flex; flex-direction:column; padding-top:12px; }
.detail-heading { display:flex; align-items:center; gap:12px; padding-bottom:8px; }
.location-select { flex:0 0 230px; max-width:100%; }
.detail-heading span { font-size:10px; opacity:.7; }
.entry-list { overflow:auto; min-height:0; padding:0; }
@media(max-width:900px) { .geo-view { height:calc(100% - 212px); margin-top:212px; min-height:500px; }.detail-heading { flex-wrap:wrap; gap:4px; }.map-summary { padding-bottom:4px; } h2 { font-size:16px; } .map-details { flex-basis:150px; } }
</style>
