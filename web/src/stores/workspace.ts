import { defineStore } from 'pinia'
import { api } from '../api/client'

// No consumer here: which program is in view belongs to the canvas (see the graph store's
// focusId), not to the workspace, which holds every program at once.
export interface Workspace { root_id: string | null; root_label: string | null; permission_mode: string; model_strong: string | null; model_fast: string | null; openai_base_url: string | null; layers: Record<string, boolean>; defaults?: any }

export const useWorkspace = defineStore('workspace', {
  state: () => ({
    ws: { root_id: null, root_label: null, permission_mode: 'ask_always', model_strong: null, model_fast: null, openai_base_url: null, layers: { entities: true, indirect_orgs: true, people: true, countries: false, categories: false, artifacts: false, sources: false, claims: false } } as Workspace,
    theme: (localStorage.getItem('illuminate.theme') as 'light' | 'dark') || 'dark',
    depth: Number(localStorage.getItem('illuminate.depth') || 2),
    modelKey: false,
    loaded: false,
    // Does this workspace hold scenario material at all? Scenario records are drawn and
    // scored exactly like observed ones, so the app-bar badge is the only disclosure —
    // which means it has to be a fact about the data, true on every page, not a property
    // of whatever the canvas happens to have loaded.
    simulated: false,
  }),
  actions: {
    async load() { this.ws = await api.get('/api/workspace'); this.loaded = true; this.loadSimulated() },
    async loadSimulated() { try { this.simulated = Boolean((await api.get('/api/graph/stats')).simulated) } catch { /* the badge stays off rather than guessing */ } },
    async save(patch: Partial<Workspace>) { const body = { ...this.ws, ...patch }; delete (body as any).defaults; this.ws = await api.put('/api/workspace', body) },
    setLayer(k: string, v: boolean) { this.ws.layers = { ...this.ws.layers, [k]: v }; this.save({ layers: this.ws.layers }) },
    setTheme(t: 'light' | 'dark') { this.theme = t; localStorage.setItem('illuminate.theme', t) },
    setDepth(d: number) { this.depth = d; localStorage.setItem('illuminate.depth', String(d)) },
  },
})
