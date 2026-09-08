import { defineStore } from 'pinia'
import { api, qs } from '../api/client'
import type { StyleOp, LegendItem } from '../styles/styleOps'
import { deriveLegend } from '../styles/styleOps'
import { restrictDeltaToFocus } from './graphDelta'

export interface GNode { id: string; label: string; labels?: string[]; layer?: string | null; name: string; props: Record<string, any> }
export interface GEdge { id: string; source: string; target: string; type: string; props: Record<string, any> }

/** How long an arriving node stays marked as new on the canvas. */
const FRESH_MS = 6000
/** The layer toggles the graph endpoints take. Entities are always fetched. */
export const LAYER_KEYS = ['people', 'countries', 'categories', 'artifacts', 'sources', 'claims'] as const
function layerParams(layers: Record<string, boolean>) {
  return Object.fromEntries(LAYER_KEYS.map(k => [k, !!layers[k]]))
}
const isProgram = (n: GNode) => n.label === 'Entity' && n.props?.kind === 'program'

export const useGraph = defineStore('graph', {
  state: () => ({
    nodes: new Map<string, GNode>(), edges: new Map<string, GEdge>(),
    selectedId: null as string | null, selectedEdgeId: null as string | null,
    styleOps: [] as StyleOp[], legend: [] as LegendItem[],
    lastCypher: null as { statement: string; params?: any } | null, loading: false,
    version: 0, styleVersion: 0, highlightIds: [] as string[],
    focusIds: [] as string[], reportFocusLabel: '', focusVendorId: '', focusFamily: '',
    focusUnavailableIds: [] as string[], filter: '',
    // The current program; null deliberately means the all-graph live view.
    focusId: null as string | null, focusLabel: null as string | null,
    programs: [] as { id: string; name: string }[],
    truncated: false, fresh: [] as string[], freshVersion: 0,
  }),
  getters: {
    selected: s => s.selectedId ? s.nodes.get(s.selectedId) || null : null,
    selectedEdge: s => s.selectedEdgeId ? s.edges.get(s.selectedEdgeId) || null : null,
    nodeList: s => [...s.nodes.values()], edgeList: s => [...s.edges.values()],
    // Scenario material is on the canvas: the app bar says so once, instead of an overlay
    // sitting on top of the graph.
    hasSimulated: s => [...s.nodes.values()].some(n => n.props?.simulated) || [...s.edges.values()].some(e => e.props?.simulated),
  },
  actions: {
    merge(sub: { nodes: GNode[]; edges: GEdge[] } | null | undefined) {
      if (!sub) return
      for (const n of sub.nodes || []) this.nodes.set(n.id, n)
      for (const e of sub.edges || []) if (this.nodes.has(e.source) && this.nodes.has(e.target)) this.edges.set(e.id, e)
      this.version++
    },
    replace(sub: { nodes: GNode[]; edges: GEdge[] } | null | undefined) {
      this.nodes = new Map(); this.edges = new Map(); this.fresh = []; this.merge(sub)
      if (this.focusIds.length && !this.focusIds.some(id => this.nodes.has(id) || this.edges.has(id))) this.clearFocus()
    },
    clear() { this.nodes = new Map(); this.edges = new Map(); this.selectedId = null; this.selectedEdgeId = null; this.fresh = []; this.clearFocus(); this.version++ },
    select(id: string | null) { this.selectedId = id; if (id) this.selectedEdgeId = null },
    selectEdge(id: string | null) { this.selectedEdgeId = id; if (id) this.selectedId = null },
    setFilter(q: string) { this.filter = (q || '').trim() },
    setFocus(ids: string[], label = '', vendorId = '', family = '') {
      this.focusIds = [...new Set((ids || []).filter(Boolean))].sort()
      this.reportFocusLabel = label; this.focusVendorId = vendorId; this.focusFamily = family
      this.focusUnavailableIds = []; this.styleVersion++
    },
    setFocusUnavailable(ids: string[]) { this.focusUnavailableIds = [...new Set(ids)].sort() },
    clearFocus() { this.focusIds = []; this.reportFocusLabel = ''; this.focusVendorId = ''; this.focusFamily = ''; this.focusUnavailableIds = []; this.styleVersion++ },
    applyStyleOps(ops: StyleOp[], append = false) {
      this.styleOps = append ? [...this.styleOps, ...ops] : ops
      this.legend = deriveLegend(this.styleOps); this.styleVersion++
    },
    clearStyleOps() { this.styleOps = [{ op: 'clear', scope: 'all' }]; this.legend = []; this.styleVersion++ },

    /** A change committed on the server — a new entity, an enrichment fact, an approved claim.
     *  Merge it and flag what is genuinely new so the canvas can place and reveal it. */
    applyDelta(sub: { nodes: GNode[]; edges: GEdge[] } | null | undefined, focus?: string[]) {
      if (!sub?.nodes?.length) return
      // A program in the delta belongs in the picker whether or not it is drawn here.
      this.notePrograms(sub.nodes)
      // A focused canvas is one program's supply chain: another program arriving live
      // must not sneak in through a supplier the two share.
      if (this.focusId) {
        sub = restrictDeltaToFocus(sub, { nodes: this.nodeList, edges: this.edgeList }, this.focusId)
        if (!sub.nodes.length) return
      }
      const newNodes = sub.nodes.filter(n => !this.nodes.has(n.id)).map(n => n.id)
      const newEdges = (sub.edges || []).filter(e => !this.edges.has(e.id)).map(e => e.id)
      this.merge(sub)
      // What to draw attention to: whatever is new, plus the node the change was about.
      const arrived = [...newNodes, ...newEdges, ...(focus || [])].filter(id => this.nodes.has(id) || this.edges.has(id))
      if (!arrived.length) return
      this.fresh = [...new Set([...this.fresh, ...arrived])]
      this.freshVersion++
      const stale = new Set(arrived)
      setTimeout(() => { this.fresh = this.fresh.filter(id => !stale.has(id)); this.freshVersion++ }, FRESH_MS)
    },

    /** The programs the canvas can be narrowed to. */
    async loadPrograms() {
      try { this.programs = (await api.get('/api/graph/programs')).items } catch { /* keep whatever the deltas have given us */ }
    },

    /** Fold programs seen in graph data into the picker, in place, by name order. A
     *  program created while the canvas is open is selectable immediately. */
    notePrograms(nodes: GNode[]) {
      let touched = false
      for (const n of nodes) {
        if (!isProgram(n)) continue
        const at = this.programs.findIndex(p => p.id === n.id)
        if (at < 0) { this.programs.push({ id: n.id, name: n.name }); touched = true }
        else if (this.programs[at].name !== n.name) { this.programs[at] = { id: n.id, name: n.name }; touched = true }
        if (n.id === this.focusId && this.focusLabel !== n.name) this.focusLabel = n.name
      }
      if (touched) this.programs = [...this.programs].sort((a, b) => a.name.localeCompare(b.name))
    },

    /** Everything in the graph, bounded by the active layers. The default view. */
    async loadAll(layers: Record<string, boolean>) {
      this.loading = true
      try {
        const r = await api.get(`/api/graph/all?${qs(layerParams(layers))}`)
        this.focusId = null
        this.focusLabel = null
        this.truncated = !!r.truncated
        this.replace(r.subgraph)
        this.notePrograms(this.nodeList)
        this.lastCypher = null
      } finally { this.loading = false }
    },

    /** Narrow the canvas to one program's supply chain — that program and what reaches it,
     *  with the other programs (and anything hanging off only them) left out. */
    async focus(entityId: string, label: string | null, depth: number, layers: Record<string, boolean>) {
      const was = { id: this.focusId, label: this.focusLabel }
      // Set before loading: the load is what confines the walk to this program, and it
      // reads the focus to do it.
      this.focusId = entityId
      this.focusLabel = label || this.programs.find(p => p.id === entityId)?.name || null
      try {
        await this.loadNeighbourhood(entityId, depth, layers, true)
      } catch (e) {
        this.focusId = was.id; this.focusLabel = was.label
        throw e
      }
      this.truncated = false
    },

    async loadNeighbourhood(entityId: string, depth: number, layers: Record<string, boolean>, replace = false) {
      this.loading = true
      try {
        const r = await api.get(`/api/graph/subgraph?${qs({ entity_id: entityId, depth, ...layerParams(layers), program_id: this.focusId })}`)
        replace ? this.replace(r.subgraph) : this.merge(r.subgraph)
        this.notePrograms(r.subgraph?.nodes || [])
        this.lastCypher = { statement: r.cypher, params: r.params }
      } finally { this.loading = false }
    },
    async runTemplate(name: string, params: any, applyStyles = true) {
      // A template's root is whatever the canvas is focused on unless the caller says otherwise.
      const r = await api.post('/api/query/template', { name, params: { root_id: this.focusId, ...params }, apply_styles: applyStyles })
      if (r.subgraph) this.merge(r.subgraph)
      if (r.style_ops?.length) this.applyStyleOps(r.style_ops)
      if (r.cypher) this.lastCypher = { statement: r.cypher, params: r.params }
      return r
    },
  },
})
