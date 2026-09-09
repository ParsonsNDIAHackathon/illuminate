import { defineStore } from 'pinia'
import { api } from '../api/client'
import { readLayers, writeLayers } from './layerPrefs'

// No consumer here: which program is in view belongs to the canvas (see the graph store's
// focusId), not to the workspace, which holds every program at once.
export interface Workspace { permission_mode: string; model_strong: string | null; model_fast: string | null; openai_base_url: string | null; layers: Record<string, boolean>; defaults?: any }

// Layers are this browser's, not the workspace's — see stores/layerPrefs.ts for why, and for
// what an unset one draws.

export const useWorkspace = defineStore('workspace', {
  state: () => ({
    ws: { permission_mode: 'ask_always', model_strong: null, model_fast: null, openai_base_url: null, layers: readLayers() } as Workspace,
    theme: (localStorage.getItem('illuminate.theme') as 'light' | 'dark') || 'dark',
    depth: Number(localStorage.getItem('illuminate.depth') || 2),
    // Does the canvas mark risk on its own — the halo under a scored node and the score on
    // its label? Off by default, and deliberately so: a supply chain drawn without it is
    // what everyone already has, and the point of this tool is how little that picture
    // tells you. Turning it on is the demonstration. Per-browser, like the theme and the
    // depth; it changes what you are looking at, not what the workspace holds.
    riskEmphasis: localStorage.getItem('illuminate.riskEmphasis') === '1',
    modelKey: false,
    loaded: false,
    // Does this workspace hold scenario material at all? Scenario records are drawn and
    // scored exactly like observed ones, so the app-bar badge is the only disclosure —
    // which means it has to be a fact about the data, true on every page, not a property
    // of whatever the canvas happens to have loaded.
    simulated: false,
  }),
  actions: {
    // The server's copy of the layers is a fallback for callers without a browser; this
    // browser's own choice outranks it on every load, including the first one.
    async load() { this.ws = { ...(await api.get('/api/workspace')), layers: readLayers() }; this.loaded = true; this.loadSimulated() },
    async loadSimulated() { try { this.simulated = Boolean((await api.get('/api/graph/stats')).simulated) } catch { /* the badge stays off rather than guessing */ } },
    async save(patch: Partial<Workspace>) { const body = { ...this.ws, ...patch }; delete (body as any).defaults; this.ws = { ...(await api.put('/api/workspace', body)), layers: this.ws.layers } },
    setLayer(k: string, v: boolean) {
      this.ws.layers = { ...this.ws.layers, [k]: v }
      writeLayers(this.ws.layers)
      this.save({ layers: this.ws.layers })
    },
    setTheme(t: 'light' | 'dark') { this.theme = t; localStorage.setItem('illuminate.theme', t) },
    setDepth(d: number) { this.depth = d; localStorage.setItem('illuminate.depth', String(d)) },
    setRiskEmphasis(on: boolean) { this.riskEmphasis = on; localStorage.setItem('illuminate.riskEmphasis', on ? '1' : '0') },
  },
})
