<template>
  <div ref="container" class="cesium-map" aria-label="Interactive Cesium globe. Drag to rotate, scroll to zoom. Use the detail selectors to inspect locations with a keyboard." />
  <div v-if="error" class="globe-error" role="alert">{{ error }} <v-btn size="small" @click="initialize">Retry globe</v-btn></div>
  <div v-else-if="loading" class="globe-loading" role="status">Loading globe…</div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import {
  Viewer, Cartesian2, Cartesian3, Color, Credit, CreditDisplay, CustomDataSource, DistanceDisplayCondition,
  LabelStyle, PolylineDashMaterialProperty, ScreenSpaceEventHandler, ScreenSpaceEventType,
  SingleTileImageryProvider, OpenStreetMapImageryProvider, ProviderViewModel,
  ArcGisMapServerImageryProvider, TileMapServiceImageryProvider, buildModuleUrl,
  BingMapsImageryProvider, BingMapsStyle,
} from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { visibleMarkerIds } from '../mapVisibility'
import activeNewsMarker from '../assets/news-marker-active.svg'
import markerHighlight from '../assets/marker-highlight.svg'
import newsMarker from '../assets/news-marker.svg'
import regions from '../data/mapRegions.json'
import type { GlobeMarker, GlobeRoute } from '../cesiumMap'

const props = defineProps<{ markers: GlobeMarker[]; routes: GlobeRoute[]; showRegions: boolean }>()
const emit = defineEmits<{ pick: [id: string]; 'visible-markers': [ids: string[]] }>()
const container = ref<HTMLElement>()
const error = ref('')
const loading = ref(true)
let viewer: Viewer | undefined
let clicks: ScreenSpaceEventHandler | undefined
let observer: ResizeObserver | undefined
let disposed = false
let removeVisibilityListener: (() => void) | undefined
let lastVisible = ''
function updateVisibility() {
  if (!viewer) return
  const canvas = viewer.scene.canvas
  const ids = visibleMarkerIds(props.markers, viewer.camera, canvas.clientWidth, canvas.clientHeight)
  const signature = JSON.stringify(ids)
  if (signature !== lastVisible) { lastVisible = signature; emit('visible-markers', ids) }
}
let boundaries: ReturnType<Viewer['imageryLayers']['addImageryProvider']> | undefined
const overlay = new CustomDataSource('Illuminate')

function focus(longitude: number, latitude: number, height = 18000000) {
  viewer?.camera.flyTo({ destination: Cartesian3.fromDegrees(longitude, latitude, height), duration: 1.2 })
}
function reset() { focus(-65, 25) }
function zoomIn() { if (viewer) { viewer.camera.zoomIn(viewer.camera.positionCartographic.height * .35); viewer.scene.requestRender() } }
function zoomOut() { if (viewer) { viewer.camera.zoomOut(viewer.camera.positionCartographic.height * .5); viewer.scene.requestRender() } }
defineExpose({ focus, reset, zoomIn, zoomOut })

function draw() {
  if (!viewer) return
  const entities = overlay.entities
  // Publish removals before reusing IDs so Cesium rebinds each visualizer.
  entities.removeAll()
  entities.suspendEvents()
  for (const route of props.routes) {
    if (route.points.length < 2) continue
    const color = Color.fromCssColorString(route.selected ? '#ffffff' : route.color)
    entities.add({ id: route.id, name: route.name, polyline: {
      positions: Cartesian3.fromDegreesArray(route.points.flatMap(p => [p.longitude, p.latitude])),
      width: route.selected ? 5 : 3,
      material: route.dashed ? new PolylineDashMaterialProperty({ color, dashLength: 14 }) : color,
    } })
  }
  for (const marker of props.markers) {
    entities.add({ id: marker.id, name: marker.name,
      position: Cartesian3.fromDegrees(marker.longitude, marker.latitude, 1500),
      billboard: marker.news ? {
        image: marker.inspected ? activeNewsMarker : newsMarker,
        width: marker.inspected ? 44 : 28, height: marker.inspected ? 44 : 28,
        scale: !marker.inspected && marker.selected ? 1.2 : 1,
        pixelOffset: new Cartesian2(0, -26), eyeOffset: new Cartesian3(0, 0, -10000),
      } : marker.inspected ? {
        image: markerHighlight, width: 48, height: 48, eyeOffset: new Cartesian3(0, 0, -10000),
      } : undefined,
      point: marker.news ? undefined : { pixelSize: marker.inspected ? 30 : marker.text ? 25 : 10, color: Color.fromCssColorString(marker.color),
        outlineColor: marker.selected ? Color.WHITE : Color.fromCssColorString('#102b38'), outlineWidth: marker.selected ? 3 : 2,
      },
      label: { show: !marker.news || !!marker.selected || !!marker.inspected,
        text: marker.news ? `${marker.text} ${marker.text === '1' ? 'article' : 'articles'}` : marker.text || marker.name,
        font: 'bold 12px sans-serif', eyeOffset: new Cartesian3(0, 0, -10000), fillColor: marker.text && !marker.news ? Color.fromCssColorString('#102b38') : Color.WHITE,
        style: marker.text && !marker.news ? LabelStyle.FILL : LabelStyle.FILL_AND_OUTLINE,
        outlineColor: Color.fromCssColorString('#102b38'), outlineWidth: 3,
        pixelOffset: new Cartesian2(0, marker.news ? (marker.inspected ? -61 : -53) : marker.text ? 0 : -19),
        showBackground: !!marker.news, backgroundColor: Color.fromCssColorString('#183440'),
        distanceDisplayCondition: new DistanceDisplayCondition(0, marker.text || marker.selected ? 1e9 : 8e6),
      },
    })
  }
  entities.resumeEvents()
  viewer.scene.requestRender()
}

async function initialize() {
  if (!container.value || disposed) return
  error.value = ''; loading.value = true
  clicks?.destroy(); observer?.disconnect(); removeVisibilityListener?.()
  lastVisible = ''; emit('visible-markers', [])
  if (viewer && !viewer.isDestroyed()) viewer.destroy()
  viewer = undefined; boundaries = undefined
  try {
    // This viewer uses no ion services; retain an accurate engine credit.
    CreditDisplay.cesiumCredit = new Credit('<a href="https://cesium.com/cesiumjs/" target="_blank" rel="noopener">CesiumJS</a>', true)
    const imageryChoices = [
      new ProviderViewModel({
        name: 'OpenStreetMap', tooltip: 'Street map with roads and place names',
        iconUrl: buildModuleUrl('Widgets/Images/ImageryProviders/openStreetMap.png'),
        creationFunction: () => new OpenStreetMapImageryProvider({
          url: 'https://tile.openstreetmap.org/', maximumLevel: 19,
          credit: new Credit('&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>', true),
        }),
      }),
      new ProviderViewModel({
        name: 'Satellite', tooltip: 'Esri World Imagery — satellite and aerial photography',
        iconUrl: buildModuleUrl('Widgets/Images/ImageryProviders/ArcGisMapServiceWorldImagery.png'),
        creationFunction: () => ArcGisMapServerImageryProvider.fromUrl('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'),
      }),
      new ProviderViewModel({
        name: 'Natural Earth', tooltip: 'Bundled physical world map — no external tile service',
        iconUrl: buildModuleUrl('Widgets/Images/ImageryProviders/naturalEarthII.png'),
        creationFunction: () => TileMapServiceImageryProvider.fromUrl(buildModuleUrl('Assets/Textures/NaturalEarthII')),
      }),
    ]
    const bingKey = import.meta.env.VITE_BING_MAPS_KEY?.trim()
    if (bingKey) imageryChoices.unshift(new ProviderViewModel({
      name: 'Bing Maps', tooltip: 'Bing aerial imagery with road and place labels',
      iconUrl: buildModuleUrl('Widgets/Images/ImageryProviders/bingAerialLabels.png'),
      creationFunction: () => BingMapsImageryProvider.fromUrl('https://dev.virtualearth.net', {
        key: bingKey, mapStyle: BingMapsStyle.AERIAL_WITH_LABELS_ON_DEMAND,
      }),
    }))
    viewer = new Viewer(container.value, {
      baseLayerPicker: true, imageryProviderViewModels: imageryChoices,
      selectedImageryProviderViewModel: imageryChoices[0], terrainProviderViewModels: [],
      geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: true, navigationInstructionsInitiallyVisible: false, animation: false, timeline: false,
      fullscreenButton: false, infoBox: false, selectionIndicator: false,
      requestRenderMode: true, maximumRenderTimeChange: Infinity,
    })
    viewer.scene.backgroundColor = Color.fromCssColorString('#07121d')
    viewer.scene.globe.baseColor = Color.fromCssColorString('#294653')
    viewer.camera.setView({ destination: Cartesian3.fromDegrees(-65, 25, 18000000) })
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = 10000
    viewer.scene.screenSpaceCameraController.maximumZoomDistance = 40000000
    await viewer.dataSources.add(overlay)
    if (disposed) return
    clicks = new ScreenSpaceEventHandler(viewer.scene.canvas)
    clicks.setInputAction((event: { position: Cartesian2 }) => {
      const picked = viewer?.scene.pick(event.position)
      if (picked?.id?.id) emit('pick', picked.id.id)
    }, ScreenSpaceEventType.LEFT_CLICK)
    observer = new ResizeObserver(() => { viewer?.resize(); viewer?.scene.requestRender() })
    observer.observe(container.value)
    removeVisibilityListener = viewer.scene.postRender.addEventListener(updateVisibility)
    draw()
    // Rasterize the existing geographic boundaries once, rather than creating thousands of entities.
    const canvas = document.createElement('canvas'); canvas.width = 4096; canvas.height = 2048
    const context = canvas.getContext('2d')!
    context.scale(canvas.width / 1080, canvas.height / 540)
    context.strokeStyle = '#d4e3ea'; context.lineWidth = .22
    for (const region of regions) context.stroke(new Path2D(region.path))
    const provider = await SingleTileImageryProvider.fromUrl(canvas.toDataURL())
    if (disposed) return
    boundaries = viewer.imageryLayers.addImageryProvider(provider)
    boundaries.alpha = .65; boundaries.show = props.showRegions
    viewer.scene.requestRender()
  } catch (cause) {
    if (!disposed) error.value = 'The globe could not load. Check that WebGL is enabled in your browser.'
    console.error('Cesium initialization failed', cause)
  } finally { loading.value = false }
}
watch(() => [props.markers, props.routes], draw)
watch(() => props.showRegions, show => { if (boundaries) boundaries.show = show; viewer?.scene.requestRender() })
onMounted(initialize)
onBeforeUnmount(() => {
  disposed = true; observer?.disconnect(); clicks?.destroy(); removeVisibilityListener?.()
  if (viewer && !viewer.isDestroyed()) viewer.destroy()
  viewer = undefined
})
</script>

<style scoped>
.cesium-map { position:absolute; inset:0; }
.globe-error,.globe-loading { position:absolute; top:45%; left:15%; right:15%; padding:16px; background:#102b38eb; color:white; border-radius:8px; text-align:center; }
.cesium-map :deep(.cesium-viewer-toolbar) { top:52px; right:10px; }
.cesium-map :deep(.cesium-baseLayerPicker-dropDown) { max-width:calc(100vw - 110px); }
.cesium-map :deep(.cesium-widget-credits) { font-size:10px; }
</style>
