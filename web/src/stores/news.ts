import { defineStore } from 'pinia'
import { api, qs, ApiError } from '../api/client.ts'
import type { NewsArticle } from '../newsMap.ts'

export interface NewsResult { articles: NewsArticle[]; query: string; timespan: string }

/** Session state survives map unmounts, including an in-flight search. */
export const useNews = defineStore('news', {
  state: () => ({
    query: '(conflict OR earthquake OR flood OR protest)',
    timespan: '7d',
    visible: true,
    location: '',
    selectedUrl: null as string | null,
    result: null as NewsResult | null,
    loading: false,
    error: '',
    attempted: false,
    retryAt: 0,
  }),
  getters: {
    selected: state => state.result?.articles.find(article => article.url === state.selectedUrl) || null,
  },
  actions: {
    async ensureLoaded() {
      if (!this.attempted) await this.search()
    },
    async search() {
      if (this.loading || Date.now() < this.retryAt || this.query.trim().length < 2) return
      this.loading = true
      this.attempted = true
      this.error = ''
      this.visible = true
      const query = this.query.trim(), timespan = this.timespan
      try {
        const result = await api.get<NewsResult>(`/api/news?${qs({ query, timespan })}`)
        this.retryAt = 0
        this.result = result
        this.location = ''
        if (!result.articles.some(article => article.url === this.selectedUrl)) this.selectedUrl = null
      } catch (error) {
        if (error instanceof ApiError && error.retryAfter) this.retryAt = Date.now() + error.retryAfter * 1000
        this.error = error instanceof Error ? error.message.split(': ').slice(1).join(': ') || error.message : 'Unable to load GDELT news.'
        // Keep the previous, explicitly labelled result when the service is unavailable.
      } finally {
        this.loading = false
      }
    },
  },
})
