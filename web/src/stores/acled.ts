import { defineStore } from 'pinia'
import { acledPlaces, type AcledSnapshot, type AcledPeriod } from '../acledMap.ts'

export const useAcled = defineStore('acled', {
  state: () => ({ visible: true, period: '1m' as AcledPeriod, eventType: '', country: '', selectedId: '',
    data: null as AcledSnapshot | null, loading: false, error: '' }),
  getters: {
    places: state => acledPlaces(state.data, state.period, state.eventType, state.country),
    mapped() { return this.places.filter(p => p.latitude !== null && p.longitude !== null) },
    countries: state => [...new Set(state.data?.places.map(p => p.country) || [])].sort(),
    eventTypes: state => [...new Set(state.data?.places.flatMap(p => Object.keys(p.periods['12m'] || {})) || [])].sort(),
    selected() { return this.places.find(p => p.id === this.selectedId) || null },
  },
  actions: {
    async load() {
      if (this.data || this.loading) return
      this.loading = true
      this.error = ''
      try { this.data = (await import('../data/acledMap.json')).default as AcledSnapshot }
      catch { this.error = 'Unable to load the ACLED snapshot. Retry to load the local data.' }
      finally { this.loading = false }
    },
  },
})
