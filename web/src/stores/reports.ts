import { defineStore } from 'pinia'
import { api, qs } from '../api/client'

export interface ReportRow {
  id: string
  kind: string
  title: string
  subject_id: string
  subject_name: string
  subject_kind?: string
  generated_at: string
  generated_by?: string
  model?: string | null
  summary?: string
  finding_count?: number
  top_band?: string | null
  cited_count?: number
  simulated?: boolean
}

export interface ReportKind { kind: string; label: string; description: string }

/** The document and its citations, as the reader and the properties card ask for them. */
export interface Report extends ReportRow {
  html?: string
  element_ids?: string[]
  cites?: { id: string; name: string; label: string }[]
}

export const useReports = defineStore('reports', {
  state: () => ({
    items: [] as ReportRow[],
    kinds: [] as ReportKind[],
    defaultKind: 'risk_assessment',
    loading: false,
    // The id currently being generated or regenerated, so every surface that can start one
    // — the Reports tab, the properties card — can show it is busy without its own flag.
    busy: null as string | null,
    error: '' as string,
  }),
  getters: {
    byId: (s) => (id: string) => s.items.find(r => r.id === id) || null,
    forSubject: (s) => (subjectId: string) => s.items.filter(r => r.subject_id === subjectId),
  },
  actions: {
    async load() {
      this.loading = true
      try {
        const r = await api.get('/api/reports')
        this.items = r.items
        this.kinds = r.kinds
        this.defaultKind = r.default_kind || this.defaultKind
      } finally { this.loading = false }
    },
    /** Generate (or regenerate — the id is stable per kind and subject) and return the row. */
    async generate(kind: string, subjectId: string): Promise<ReportRow> {
      this.busy = `${kind}:${subjectId}`
      this.error = ''
      try {
        const row = await api.post('/api/reports', { kind, subject_id: subjectId })
        await this.load()
        return row
      } catch (e: any) {
        this.error = e?.message || String(e)
        throw e
      } finally { this.busy = null }
    },
    async regenerate(id: string): Promise<ReportRow> {
      this.busy = id
      this.error = ''
      try {
        const row = await api.post(`/api/reports/${encodeURIComponent(id)}/regenerate`)
        await this.load()
        return row
      } catch (e: any) {
        this.error = e?.message || String(e)
        throw e
      } finally { this.busy = null }
    },
    async remove(id: string) {
      await api.del(`/api/reports/${encodeURIComponent(id)}`)
      this.items = this.items.filter(r => r.id !== id)
    },
    /** One report. `html: false` is the properties card, which wants the date and the
     *  citations and has no use for 100 KB of document. */
    async fetch(id: string, withHtml = true): Promise<Report> {
      return api.get(`/api/reports/${encodeURIComponent(id)}?${qs({ html: withHtml })}`)
    },
  },
})
