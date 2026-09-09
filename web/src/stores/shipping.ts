import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client.ts'
import { useGraph } from './graph.ts'
import { linkedShippingRoutes, usesPort, type ShippingCatalog, type RouteStatus, type TransportMode, matchesMode } from '../shippingMap.ts'

export const useShipping = defineStore('shipping', () => {
  const graph = useGraph()
  const visible = ref(true)
  const status = ref<RouteStatus | ''>('')
  const mode = ref<TransportMode | ''>('')
  const port = ref('')
  const selectedId = ref('')
  const loading = ref(false), error = ref(''), attempted = ref(false)
  const catalog = ref<ShippingCatalog>({ ports: [], routes: [] })
  const scoped = computed(() => linkedShippingRoutes(catalog.value, graph.nodeList, graph.edgeList, graph.filter))
  const filtered = computed(() => scoped.value.filter(x => (!status.value || x.route.status === status.value) && matchesMode(x.route, mode.value)))
  const routes = computed(() => filtered.value.filter(x => !port.value || usesPort(x.route, port.value)))
  const ports = computed(() => catalog.value.ports.filter(p => filtered.value.some(x => usesPort(x.route, p.id))))
  const selected = computed(() => routes.value.find(x => x.route.id === selectedId.value))
  function select(id: string) { selectedId.value = id }
  async function load() {
    if (loading.value) return
    loading.value = true; attempted.value = true; error.value = ''
    try { catalog.value = await api.get<ShippingCatalog>('/api/shipping') }
    catch (e) { error.value = e instanceof Error ? e.message : 'Unable to load shipping routes.' }
    finally { loading.value = false }
  }
  return { visible, status, mode, port, selectedId, loading, error, attempted, catalog, scoped, filtered, routes, ports, selected, select, load }
})
