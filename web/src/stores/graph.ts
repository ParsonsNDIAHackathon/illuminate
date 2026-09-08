import { defineStore } from 'pinia'
import { api, qs } from '../api/client'
import type { StyleOp, LegendItem } from '../styles/styleOps'
import { deriveLegend } from '../styles/styleOps'

export interface GNode { id: string; label: string; labels?: string[]; name: string; props: Record<string, any> }
export interface GEdge { id: string; source: string; target: string; type: string; props: Record<string, any> }

export const useGraph = defineStore('graph', {
  state: () => ({
    nodes: new Map<string, GNode>(),
    edges: new Map<string, GEdge>(),
    selectedId: null as string | null,
    selectedEdgeId: null as string | null,
    styleOps: [] as StyleOp[],
    legend: [] as LegendItem[],
    lastCypher: null as { statement: string; params?: any } | null,
    loading: false,
    version: 0,          // bumped when elements change
    styleVersion: 0,     // bumped when style ops change
    highlightIds: [] as string[],
    filter: '',          // search-bar text; canvas dims nodes that don't match
  }),
  getters: {
    selected: (s) => (s.selectedId ? s.nodes.get(s.selectedId) || null : null),
    selectedEdge: (s) => (s.selectedEdgeId ? s.edges.get(s.selectedEdgeId) || null : null),
    nodeList: (s) => [...s.nodes.values()],
    edgeList: (s) => [...s.edges.values()],
  },
  actions: {
    merge(sub: { nodes: GNode[]; edges: GEdge[] } | null | undefined) {
      if (!sub) return
      for (const n of sub.nodes || []) this.nodes.set(n.id, n)
      for (const e of sub.edges || []) if (this.nodes.has(e.source) && this.nodes.has(e.target)) this.edges.set(e.id, e)
      this.version++
    },
    replace(sub: { nodes: GNode[]; edges: GEdge[] } | null | undefined) { this.nodes = new Map(); this.edges = new Map(); this.merge(sub) },
    clear() { this.nodes = new Map(); this.edges = new Map(); this.selectedId = null; this.selectedEdgeId = null; this.version++ },
    select(id: string | null) { this.selectedId = id; if (id) this.selectedEdgeId = null },
    selectEdge(id: string | null) { this.selectedEdgeId = id; if (id) this.selectedId = null },
    setFilter(q: string) { this.filter = (q || '').trim() },
    applyStyleOps(ops: StyleOp[], append = false) {
      this.styleOps = append ? [...this.styleOps, ...ops] : ops
      this.legend = deriveLegend(this.styleOps)
      this.styleVersion++
    },
    clearStyleOps() { this.styleOps = [{ op: 'clear', scope: 'all' }]; this.legend = []; this.styleVersion++ },
    async loadNeighbourhood(entityId: string, depth: number, layers: Record<string, boolean>, replace = false) {
      this.loading = true
      try {
        const r = await api.get(`/api/graph/subgraph?${qs({ entity_id: entityId, depth, people: !!layers.people, countries: !!layers.countries, artifacts: !!layers.artifacts, categories: !!layers.categories })}`)
        replace ? this.replace(r.subgraph) : this.merge(r.subgraph)
        this.lastCypher = { statement: r.cypher, params: r.params }
      } finally { this.loading = false }
    },
    async runTemplate(name: string, params: any, applyStyles = true) {
      const r = await api.post('/api/query/template', { name, params, apply_styles: applyStyles })
      if (r.subgraph) this.merge(r.subgraph)
      if (r.style_ops?.length) this.applyStyleOps(r.style_ops)
      if (r.cypher) this.lastCypher = { statement: r.cypher, params: r.params }
      return r
    },
  },
})
