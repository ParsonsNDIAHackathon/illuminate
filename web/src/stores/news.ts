import { defineStore } from 'pinia'
import { api, qs } from '../api/client.ts'
import type { NewsArticle } from '../newsMap.ts'

export interface NewsResult { articles: NewsArticle[]; query: string; timespan: string; cached?: boolean; stale?: boolean; fetched_at?: string; notice?: string | null; sources?: { name: string; status: string; cached?: boolean; fetched_at?: string }[] }

/** Session state survives map unmounts, including an in-flight search. */
export const useNews = defineStore('news', {
  state: () => ({
    query: '(conflict OR earthquake OR flood OR protest)',
    timespan: '24h',
    visible: true,
    location: '',
    selectedUrl: null as string | null,
    result: null as NewsResult | null,
    loading: false,
    error: '',
    attempted: false,
  }),
  getters: {
    selected: state => state.result?.articles.find(article => article.url === state.selectedUrl) || null,
  },
  actions: {
    async ensureLoaded() {
      if (!this.attempted) await this.search()
    },
    async search() {
      if (this.loading || this.query.trim().length < 2) return
      this.loading = true
      this.attempted = true
      this.error = ''
      this.visible = true
      const query = this.query.trim(), timespan = this.timespan
      try {
        const result = await api.get<NewsResult>(`/api/news/search?${qs({ query, timespan })}`)
        this.result = result
        this.location = ''
        if (!result.articles.some(article => article.url === this.selectedUrl)) this.selectedUrl = null
      } catch (error) {
        this.error = error instanceof Error ? error.message.split(': ').slice(1).join(': ') || error.message : 'Unable to load news.'
        // Keep the previous, explicitly labelled result when the service is unavailable.
      } finally {
        this.loading = false
      }
    },
  },
})
