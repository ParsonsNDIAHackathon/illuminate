import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client.ts'
import { usesPort, type ShippingPort, type ShippingSegment } from '../shippingMap.ts'
export interface EstablishedLane {
  id: string; name: string; service: string; source: { title: string; reference: string }
  published_at: string; segments: ShippingSegment[]
}
export const useShippingLanes = defineStore('shippingLanes', () => {
  const enabled = ref(true), query = ref(''), port = ref(''), selectedId = ref('')
  const catalog = ref<{ ports: ShippingPort[]; lanes: EstablishedLane[] }>({ ports: [], lanes: [] })
  const loading = ref(false), loaded = ref(false), error = ref('')
  const lanes = computed(() => catalog.value.lanes.filter(lane =>
    (!port.value || usesPort(lane, port.value)) && (query.value || '').toLowerCase().trim().split(/\s+/)
      .every(word => `${lane.name} ${lane.service}`.toLowerCase().includes(word))))
  const ports = computed(() => catalog.value.ports.filter(p => lanes.value.some(l => usesPort(l, p.id))))
  const selected = computed(() => lanes.value.find(l => l.id === selectedId.value))
  async function load() {
    if (loading.value) return
    loading.value = true; error.value = ''
    try { catalog.value = await api.get('/api/shipping/lanes'); loaded.value = true }
    catch { error.value = 'Established lanes could not be loaded. Retry to load the reference catalog.' }
    finally { loading.value = false }
  }
  return { enabled, query, port, selectedId, catalog, loading, loaded, error, lanes, ports, selected, load }
})
