import { defineStore } from 'pinia'
import { api, type EnrichmentJob } from '../api/client'

export const useJobs = defineStore('jobs', {
  state: () => ({ jobs: [] as EnrichmentJob[] }),
  getters: {
    running: (s) => s.jobs.filter(j => j.status === 'queued' || j.status === 'running'),
    latestFor: (s) => (entityId: string) => s.jobs.find(j => j.entity_id === entityId),
  },
  actions: {
    async load() { this.jobs = await api.get('/api/jobs') },
    update(j: any) { const i = this.jobs.findIndex(x => x.id === j.id); if (i >= 0) this.jobs[i] = j; else this.jobs.unshift(j) },
    async enqueue(entityId: string, connectors?: string[]) { const j = await api.post(`/api/enrich/${entityId}`, { connectors }); this.update(j); return j },
  },
})
