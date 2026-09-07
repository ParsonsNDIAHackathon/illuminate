import { defineStore } from 'pinia'
import { api } from '../api/client'

export interface PermissionRequest { id: string; statement: string; params: any; classification: string; preview: { counters: Record<string, number>; sample_rows: any[]; error?: string | null }; source: string; tool?: string; rationale?: string; status: string; created_at: number; decision_note?: string }

export const usePermissions = defineStore('permissions', {
  state: () => ({ pending: [] as PermissionRequest[], history: [] as PermissionRequest[] }),
  getters: { current: (s) => s.pending[0] || null },
  actions: {
    async load() { const r = await api.get('/api/permissions'); this.pending = r.pending; this.history = r.history },
    push(req: PermissionRequest) { if (!this.pending.find(p => p.id === req.id)) this.pending.push(req) },
    resolve(req: PermissionRequest) { this.pending = this.pending.filter(p => p.id !== req.id); this.history.unshift(req) },
    async approve(id: string, opts: { edited_statement?: string; edited_params?: any; remember_shape?: boolean; acknowledge_count?: number } = {}) {
      return api.post(`/api/permissions/${id}/approve`, opts)
    },
    async refuse(id: string, reason?: string) { return api.post(`/api/permissions/${id}/refuse`, { reason }) },
  },
})
