import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client.ts'
import type { TransportCorridor } from '../shippingMap.ts'

/** Reference infrastructure has no inferred supplier dependencies. */
export const useTransport = defineStore('transport', () => {
  const highways = ref(true), rail = ref(true), selectedId = ref(''), query = ref('')
  const corridors = ref<TransportCorridor[]>([])
  const loading = ref(false), attempted = ref(false), error = ref('')
  const visible = computed(() => corridors.value.filter(c => (c.mode === 'truck' ? highways.value : rail.value)
    && (query.value || '').toLowerCase().trim().split(/\s+/).every(word => [c.name, ...c.stops].join(' ').toLowerCase().includes(word))))
  const selected = computed(() => visible.value.find(c => c.id === selectedId.value))
  async function load() {
    if (loading.value) return
    loading.value = true; attempted.value = true; error.value = ''
    try { corridors.value = (await api.get<{ corridors: TransportCorridor[] }>('/api/shipping/network')).corridors }
    catch { error.value = 'US transport reference could not be loaded. Retry to load the corridors.' }
    finally { loading.value = false }
  }
  return { highways, rail, selectedId, query, corridors, visible, selected, loading, attempted, error, load }
})
