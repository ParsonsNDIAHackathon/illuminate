<template>
  <section class="geo-view" aria-label="Geographic view of the loaded graph">
    <header class="map-summary">
      <h2>{{ graph.focusLabel || 'Across the graph' }}</h2>
      <span class="counts"><strong>{{ data.mappedCount }}</strong> mapped · {{ data.unmappedCount }} unplaced</span>
    </header>
    <nav class="map-tools" aria-label="Map layers and filters">
      <div class="layer-buttons">
        <v-btn size="small" variant="text" :color="lanes.enabled ? 'primary' : undefined" :aria-pressed="lanes.enabled" prepend-icon="mdi-ferry" @click="lanes.enabled = !lanes.enabled">Shipping</v-btn>
        <v-btn size="small" variant="text" :color="shipping.visible ? 'primary' : undefined" :aria-pressed="shipping.visible" prepend-icon="mdi-truck-outline" @click="shipping.visible = !shipping.visible">Suppliers</v-btn>
        <v-btn size="small" variant="text" :color="news.visible ? 'primary' : undefined" :aria-pressed="news.visible" prepend-icon="mdi-newspaper-variant-outline" @click="news.visible = !news.visible">News</v-btn>
      </div>
      <div class="filter-buttons">
        <v-btn size="small" variant="text" :active="controlsPanel === 'news'" :aria-expanded="controlsPanel === 'news'" aria-controls="map-news-search" @click="controlsPanel = controlsPanel === 'news' ? '' : 'news'">News search <v-icon end icon="mdi-chevron-down" /></v-btn>
        <v-btn size="small" variant="text" :active="controlsPanel === 'transport'" :aria-expanded="controlsPanel === 'transport'" aria-controls="map-transport-controls" @click="controlsPanel = controlsPanel === 'transport' ? '' : 'transport'">Transport <v-icon end icon="mdi-chevron-down" /></v-btn>
        <v-btn size="small" variant="text" prepend-icon="mdi-map-marker-radius" @click="globe?.focus(-95.5, 37, 6500000)">US</v-btn>
      </div>
    </nav>
    <form id="map-news-search" v-show="controlsPanel === 'news'" class="news-search" @submit.prevent="news.search()">
      <v-text-field v-model="news.query" label="News topic" placeholder="Search recent news…" density="compact" variant="outlined" hide-details maxlength="250" class="news-topic" />
      <v-select v-model="news.timespan" :items="timeWindows" label="Time window" density="compact" variant="outlined" hide-details class="news-window" />
      <v-btn type="submit" size="small" color="primary" variant="tonal" prepend-icon="mdi-magnify" :loading="news.loading" :disabled="news.loading || news.query.trim().length < 2">Search</v-btn>
    </form>
    <v-alert v-if="news.error" type="warning" variant="tonal" density="compact" class="mb-2 news-error" role="alert">
      {{ news.error }} <span v-if="news.result">Previous results are still shown below.</span>
    </v-alert>
    <details v-if="news.visible && news.result?.notice" class="coverage-notice">
      <summary><v-icon icon="mdi-information-outline" size="14" /> News coverage notice</summary>
      <p>{{ news.result.notice }}</p>
    </details>
    <TransportControls id="map-transport-controls" v-show="controlsPanel === 'transport'" @focus-us="globe?.focus(-95.5, 37, 6500000)" />
    <div class="map-stage">
      <CesiumMap ref="globe" :markers="globeMarkers" :routes="globeRoutes" :show-regions="showRegions" @pick="pickGlobe" @visible-markers="visibleMarkers = new Set($event)" />
      <v-sheet class="detail-toggle" rounded>
        <v-checkbox v-model="showRegions" label="States & provinces" density="compact" hide-details />
      </v-sheet>
      <v-btn-group class="zoom-tools" density="compact" aria-label="Map zoom controls">
        <v-btn icon="mdi-plus" aria-label="Zoom in" size="small" @click="globe?.zoomIn()" />
        <v-btn icon="mdi-minus" aria-label="Zoom out" size="small" @click="globe?.zoomOut()" />
        <v-btn size="small" @click="globe?.reset()">Reset</v-btn>
      </v-btn-group>
      <p v-if="!places.length && !(news.visible && newsData.places.length) && !(shipping.visible && shipping.routes.length) && !(lanes.enabled && lanes.lanes.length) && !transport.visible.length" class="map-empty" role="status">{{ graph.loading ? 'Loading locations…' : graph.filter ? 'No mapped entities match your search.' : 'No geographic locations in this graph scope. Try a deeper traversal or another program.' }}</p>
      <a class="attribution" href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener">Natural Earth · illustrative boundaries</a>
      <a class="news-attribution" href="https://www.geonames.org/" target="_blank" rel="noopener">Town locations: GeoNames</a>
    </div>
    <nav class="map-detail-tabs" aria-label="Map details">
      <v-btn v-if="news.visible" size="small" variant="text" :active="detailPanel === 'news'" :aria-expanded="detailPanel === 'news'" aria-controls="map-news-details" @click="toggleDetails('news')">News · {{ visibleNewsUrls.size }}</v-btn>
      <v-btn size="small" variant="text" :active="detailPanel === 'entities'" :aria-expanded="detailPanel === 'entities'" aria-controls="map-entity-details" @click="toggleDetails('entities')">Entities · {{ visibleEntityCount }}</v-btn>
      <v-btn v-if="lanes.enabled || shipping.visible" size="small" variant="text" :active="detailPanel === 'routes'" :aria-expanded="detailPanel === 'routes'" aria-controls="map-route-details" @click="toggleDetails('routes')">Route details</v-btn>
      <span class="detail-hint">In current view · Select a marker</span>
      <v-btn v-if="detailPanel" size="small" variant="text" icon="mdi-chevron-down" aria-label="Collapse map details" @click="detailPanel = ''" />
    </nav>
    <div id="map-route-details" v-show="detailPanel === 'routes'" class="route-details">
      <ShippingLanesPanel />
      <ShippingPanel />
    </div>
    <div id="map-news-details" v-show="news.visible && detailPanel === 'news'" class="news-details">
      <div class="detail-heading">
        <v-select v-model="news.location" :items="newsLocations" label="News location" density="compact" variant="outlined" hide-details class="location-select" />
        <v-btn size="small" variant="tonal" :disabled="!newsData.places.length" @click="globe?.reset()">Show news on map</v-btn>
        <details class="news-source-details">
          <summary>Coverage &amp; sources</summary>
          <p>Within {{ NEWS_PROXIMITY_KM }} km of visible entities or routes. Locations use identified towns/cities, otherwise approximate region centers.</p>
          <p v-if="news.result">“{{ news.result.query }}” · past {{ news.result.timespan }} · {{ newsData.mapped }} nearby articles.</p>
          <p v-for="source in news.result?.sources || []" :key="source.name">{{ source.name }} · {{ source.status }}<template v-if="source.fetched_at"> · {{ source.cached ? 'Cached' : 'Retrieved' }} {{ new Date(source.fetched_at).toLocaleString() }}</template></p>
        </details>
      </div>
      <v-progress-linear v-if="news.loading" indeterminate color="primary" aria-label="Searching recent coverage" />
      <p v-if="news.result && !newsArticles.length" class="text-caption pa-2" role="status">No news in the current map view for this selection. Pan or zoom out to see more.</p>
      <v-list class="entry-list" density="compact" aria-label="News articles">
        <v-list-item v-for="article in newsArticles" :key="article.url" class="news-article" :active="news.selectedUrl === article.url" color="primary"
                     :title="article.title || article.url" :subtitle="`${article.domain || article.publisher} · ${article.providers?.join(' + ') || article.provider || 'GDELT'} · ${article.published_at ? 'Published' : 'Seen'} ${newsDate(article.published_at || article.seendate) || 'date unavailable'}`"
                     @click="emit('select-news', article)">
          <template #append><v-icon icon="mdi-chevron-right" size="small" /></template>
        </v-list-item>
      </v-list>
    </div>
    <div id="map-entity-details" v-show="detailPanel === 'entities'" class="map-details">
      <div class="detail-heading">
        <v-select v-model="selectedKey" :items="entityLocations" label="Map location" density="compact" variant="outlined" hide-details class="location-select" />
        <span>Gold: country · Blue: state/province · Teal: coordinates. Area markers are approximate.</span>
      </div>
      <p v-if="!entries.length" class="text-caption pa-2" role="status">No entities in the current map view. Pan or zoom out to see more.</p>
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
import { computed, ref, watch, onMounted } from 'vue'
import CesiumMap from './CesiumMap.vue'
import type { GlobeMarker, GlobeRoute } from '../cesiumMap'
import TransportControls from './TransportControls.vue'
import { useTransport } from '../stores/transport'
import ShippingLanesPanel from './ShippingLanesPanel.vue'
import { useShippingLanes } from '../stores/shippingLanes'
import ShippingPanel from './ShippingPanel.vue'
import { useShipping } from '../stores/shipping'
import type { ShippingSegment, ShippingPort } from '../shippingMap'
import { useNews } from '../stores/news'
import { mapNews, nearbyNews, NEWS_PROXIMITY_KM, newsDate, type NewsArticle } from '../newsMap'
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
const visibleMarkers = ref(new Set<string>())
const controlsPanel = ref<'news' | 'transport' | ''>('')
const selectedKey = ref('')
const detailPanel = ref<'news' | 'entities' | 'routes' | ''>('')
function toggleDetails(panel: 'news' | 'entities' | 'routes') { detailPanel.value = detailPanel.value === panel ? '' : panel }
const news = useNews()
const shipping = useShipping()
const lanes = useShippingLanes()
const transport = useTransport()
watch(() => [lanes.port, shipping.port], () => { if (lanes.port || shipping.port) detailPanel.value = 'routes' })
watch(() => news.visible, visible => { if (!visible && detailPanel.value === 'news') detailPanel.value = '' })
watch(() => [lanes.enabled, shipping.visible], () => { if (!lanes.enabled && !shipping.visible && detailPanel.value === 'routes') detailPanel.value = '' })
const timeWindows = [{ title: 'Past 24 hours', value: '24h' }, { title: 'Past 3 days', value: '3d' }, { title: 'Past 7 days', value: '7d' }]
function routePoints(segments: ShippingSegment[], ports: ShippingPort[]) {
  return segments.flatMap(segment => {
    const from = ports.find(port => port.id === segment.from_port)
    const to = ports.find(port => port.id === segment.to_port)
    return from && to ? [[from, ...segment.waypoints, to]] : []
  })
}
const newsData = computed(() => nearbyNews(mapNews(news.result?.articles || [], world, regions), places.value, [
  ...transport.visible.map(corridor => corridor.points),
  ...(lanes.enabled ? lanes.lanes.flatMap(lane => routePoints(lane.segments, lanes.catalog.ports)) : []),
  ...(shipping.visible ? shipping.routes.flatMap(item => routePoints(item.route.segments, shipping.catalog.ports)) : []),
]))
const visibleNewsPlaces = computed(() => newsData.value.places.filter(place => visibleMarkers.value.has(`news:${place.code}`)))
const visibleNewsUrls = computed(() => new Set(visibleNewsPlaces.value.flatMap(place => place.articles.map(article => article.url))))
const newsArticles = computed(() => news.location
  ? visibleNewsPlaces.value.find(place => place.code === news.location)?.articles || []
  : (news.result?.articles || []).filter(article => visibleNewsUrls.value.has(article.url)))
const newsLocations = computed(() => [{ title: 'All news in view', value: '' },
  ...visibleNewsPlaces.value.map(place => ({ title: `${place.name} (${place.articles.length})`, value: place.code }))])
onMounted(() => news.ensureLoaded())
const globe = ref<InstanceType<typeof CesiumMap>>()
const showRegions = ref(true)
const data = computed(() => {
  const hidden = hiddenNodeIds(graph.nodeList, graph.edgeList, { ...workspace.ws.layers, countries: true }, graph.focusId ? [graph.focusId] : [])
  return buildMapPlaces(graph.nodeList.filter(node => !hidden.has(node.id)), graph.edgeList, world, regions)
})
const places = computed(() => data.value.places.map(place => ({ ...place, entries: place.entries.filter(entry => matchesMapEntry(entry, graph.filter)) })).filter(place => place.entries.length))
const visiblePlaces = computed(() => places.value.filter(place => visibleMarkers.value.has(`entity:${place.key}`)))
const visibleEntityCount = computed(() => new Set(visiblePlaces.value.flatMap(place => place.entries.map(entry => entry.node.id))).size)
const entityLocations = computed(() => [{ title: `Locations in view (${visiblePlaces.value.length})`, value: '' }, ...visiblePlaces.value.map(place => ({ title: `${place.name} (${entityCount(place)})`, value: place.key }))])
const entries = computed(() => visiblePlaces.value.filter(p => !selectedKey.value || p.key === selectedKey.value).flatMap(place => place.entries.map(entry => ({ entry, place }))))
watch(() => [props.locationCode, globe.value] as const, ([code]) => {
  if (!code) return
  const normalized = code.toUpperCase()
  const region = regions.find(r => r.code === normalized)
  const country = world.find(c => c.code === normalized.split('-')[0])
  const location = region || country
  if (!location) return
  globe.value?.focus(location.longitude, location.latitude, region ? 1400000 : 5500000)
  selectedKey.value = `${region ? 'region' : 'country'}:${location.code}`
  detailPanel.value = 'entities'
}, { immediate: true })
function entityCount(place: MapPlace) { return new Set(place.entries.map(e => e.node.id)).size }
function traced(place: MapPlace) { return place.entries.some(e => graph.highlightIds.includes(e.node.id) || (e.edge && graph.highlightIds.includes(e.edge.id)) || graph.selectedId === e.node.id) }
function inspect(id: string) { graph.select(id); emit('select') }
watch(visibleNewsPlaces, value => { if (!value.some(place => place.code === news.location)) news.location = '' })
watch(visiblePlaces, value => { if (!value.some(p => p.key === selectedKey.value)) selectedKey.value = '' })
const globeMarkers = computed<GlobeMarker[]>(() => [
  ...places.value.map(place => ({ id: `entity:${place.key}`, longitude: place.longitude, latitude: place.latitude,
    name: place.name, text: String(entityCount(place)), color: place.precise ? '#79dac7' : place.region ? '#99bfff' : '#f3c97c',
    selected: selectedKey.value === place.key || traced(place),
    inspected: !news.selected && !!graph.selected && place.entries.some(entry => entry.node.id === graph.selectedId) })),
  ...(news.visible ? newsData.value.places.map(place => ({ id: `news:${place.code}`, longitude: place.longitude, latitude: place.latitude,
    name: `${place.name} · news`, text: String(place.articles.length), color: '#ff927f', selected: news.location === place.code, inspected: !!news.selected && place.articles.some(article => article.url === news.selectedUrl), news: true })) : []),
  ...(lanes.enabled ? lanes.ports.map(port => ({ ...port, id: `lane-port:${port.id}`, color: '#65dfcf', selected: lanes.port === port.id })) : []),
  ...(shipping.visible ? shipping.ports.map(port => ({ ...port, id: `shipping-port:${port.id}`, color: '#c7a7ff', selected: shipping.port === port.id })) : []),
])
const globeRoutes = computed<GlobeRoute[]>(() => [
  ...transport.visible.map(c => ({ id: `transport:${c.id}`, name: c.name, points: c.points, color: c.mode === 'truck' ? '#59c8f0' : '#ffb76c', dashed: c.mode === 'rail', selected: transport.selectedId === c.id })),
  ...(lanes.enabled ? lanes.lanes.flatMap(lane => routePoints(lane.segments, lanes.catalog.ports).map((points, i) => ({ id: `lane:${lane.id}:${i}`, name: lane.name, points, color: '#65dfcf', selected: lanes.selectedId === lane.id }))) : []),
  ...(shipping.visible ? shipping.routes.flatMap(({ route }) => routePoints(route.segments, shipping.catalog.ports).map((points, i) => ({ id: `shipping:${route.id}:${i}`, name: route.name, points,
    color: route.status === 'confirmed' ? '#65dfcf' : route.status === 'inferred' ? '#ffca80' : '#c7a7ff', dashed: route.status !== 'confirmed', selected: shipping.selectedId === route.id }))) : []),
])
function pickGlobe(id: string) {
  const split = id.indexOf(':'); const kind = id.slice(0, split); const key = id.slice(split + 1)
  if (kind === 'entity') { selectedKey.value = key; detailPanel.value = 'entities' }
  if (kind === 'news') { news.location = key; detailPanel.value = 'news' }
  if (kind === 'transport') transport.selectedId = key
  if (kind === 'lane') { lanes.selectedId = key.slice(0, key.lastIndexOf(':')); detailPanel.value = 'routes' }
  if (kind === 'shipping') { shipping.select(key.slice(0, key.lastIndexOf(':'))); detailPanel.value = 'routes' }
  if (kind === 'lane-port') { lanes.port = lanes.port === key ? '' : key; detailPanel.value = 'routes' }
  if (kind === 'shipping-port') { shipping.port = shipping.port === key ? '' : key; shipping.selectedId = ''; detailPanel.value = 'routes' }
}
</script>

<style scoped>
.map-detail-tabs { display:flex; align-items:center; gap:6px; flex-shrink:0; min-height:44px; border-bottom:1px solid rgba(128,128,128,.18); }
.detail-hint { margin-left:auto; font-size:11px; opacity:.6; }
.route-details { flex:0 0 auto; max-height:260px; overflow-y:auto; }
.news-source-details { font-size:11px; margin-left:auto; max-width:480px; }
.news-source-details summary { cursor:pointer; opacity:.75; padding:6px 0; }
.news-source-details p { margin:4px 0; }
@media(max-width:600px) { .detail-hint { display:none; } .map-detail-tabs { flex-wrap:wrap; } }

.news-search { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:10px; margin-bottom:8px; border:1px solid rgba(128,128,128,.2); border-radius:8px; flex-shrink:0; }
.news-toggle { flex:0 0 auto; }
.news-topic { flex:1 1 180px; }
.news-window { flex:0 1 170px; min-width:150px; }
.news-error { flex-shrink:0; }
.news-details { flex:0 0 210px; max-height:260px; min-height:90px; display:flex; flex-direction:column; padding-top:10px; font-size:12px; }
.news-article :deep(.v-list-item-title) { white-space:normal; font-size:12px; }
.geo-view { height:calc(100% - 112px); margin-top:112px; overflow-y:auto; padding:0 16px 12px; display:flex; flex-direction:column; background:rgb(var(--v-theme-background)); }
.map-summary { display:flex; align-items:center; gap:12px; padding:2px 2px 4px; flex-shrink:0; flex-wrap:wrap; }
 .map-tools { display:flex; align-items:center; justify-content:space-between; gap:4px; flex-wrap:wrap; flex-shrink:0; padding:0 0 8px; }
.layer-buttons,.filter-buttons { display:flex; align-items:center; gap:2px; flex-wrap:wrap; }
.map-tools :deep(.v-btn) { text-transform:none; letter-spacing:0; padding:0 8px; }
.layer-buttons :deep(.v-btn[aria-pressed="true"]) { background:rgba(var(--v-theme-primary),.1); }
.coverage-notice { flex-shrink:0; font-size:11px; color:rgb(var(--v-theme-warning)); margin:0 2px 8px; }
.coverage-notice summary { cursor:pointer; }
.coverage-notice p { margin:6px 0; }
@media(max-width:600px) { .counts { margin-left:0; } .map-tools { gap:6px; } }
h2 { font-size:15px; font-weight:600; }.counts { font-size:11px; opacity:.65; margin-left:auto; }.counts strong { font-weight:600; }
.map-stage { position:relative; flex:1 0 320px; min-height:320px; border:1px solid rgba(128,128,128,.25); border-radius:10px; overflow:hidden; background:#102b38; }
.detail-toggle { position:absolute; left:8px; top:8px; padding:0 8px; max-width:230px; }
.detail-toggle .text-caption { padding:0 8px 6px; }
.zoom-tools { position:absolute; right:10px; top:10px; }
.news-attribution { position:absolute; bottom:30px; left:8px; font-size:9px; color:#d6e4e8; }
.attribution { position:absolute; bottom:30px; right:8px; font-size:9px; color:#d6e4e8; }.map-empty { position:absolute; left:15%; right:15%; top:40%; padding:15px; background:#102b38e8; color:#fff; text-align:center; font-size:13px; }
.map-details { flex:0 0 210px; max-height:260px; min-height:100px; display:flex; flex-direction:column; padding-top:12px; }
.detail-heading { display:flex; align-items:center; gap:12px; padding-bottom:8px; }
.location-select { flex:0 0 230px; max-width:100%; }
.detail-heading span { font-size:10px; opacity:.7; }
.entry-list { overflow:auto; min-height:0; padding:0; }
@media(max-width:900px) { .geo-view { height:calc(100% - 212px); margin-top:212px; min-height:500px; }.detail-heading { flex-wrap:wrap; gap:4px; }.map-summary { padding-bottom:4px; } h2 { font-size:16px; } .map-details { flex-basis:150px; } }
</style>
