import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia } from 'pinia'
import { useNews } from '../src/stores/news.ts'
import { newsPreview } from '../src/newsMap.ts'
const article = { url: 'https://example.com/news', title: 'Flood in Nepal', domain: 'example.com', language: 'English', seendate: '20260909T121500Z' }

test('remounting shares in-flight requests, query, results and selection', async t => {
  let finish!: (value: Response) => void
  let requests = 0
  t.mock.method(globalThis, 'fetch', () => { requests++; return new Promise<Response>(resolve => { finish = resolve }) })
  const pinia = createPinia()
  const first = useNews(pinia)
  first.query = 'flood'
  const pending = first.ensureLoaded()
  const remounted = useNews(pinia)
  await remounted.ensureLoaded()
  assert.equal(requests, 1)
  assert.equal(remounted.loading, true)
  finish(Response.json({ articles: [article], query: 'flood', timespan: '24h' }))
  await pending
  remounted.location = 'NP'
  remounted.selectedUrl = article.url
  remounted.visible = false
  await first.ensureLoaded()
  assert.equal(first.query, 'flood')
  assert.equal(first.location, 'NP')
  assert.equal(first.visible, false)
  assert.equal(first.selected?.url, article.url)
  assert.equal(requests, 1)
})

test('failed searches preserve labelled results and do not retry on remount', async t => {
  let requests = 0
  t.mock.method(globalThis, 'fetch', async () => { requests++; return Response.json({ detail: 'GDELT is rate limiting requests.' }, { status: 503 }) })
  const news = useNews(createPinia())
  news.result = { articles: [article], query: 'flood', timespan: '24h' }
  news.selectedUrl = article.url
  news.query = 'earthquake'
  await news.search()
  await news.ensureLoaded()
  assert.equal(news.result?.query, 'flood')
  assert.equal(news.selected?.url, article.url)
  assert.match(news.error, /rate limiting/)
  assert.equal(news.loading, false)
  assert.equal(requests, 1)
})

test('replacing results clears a selection that is no longer present', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ articles: [], query: 'flood', timespan: '24h' }))
  const news = useNews(createPinia())
  news.selectedUrl = article.url
  news.location = 'NP'
  await news.search()
  assert.equal(news.selectedUrl, null)
  assert.equal(news.location, '')
})

test('preview preserves provenance without inventing an artifact id or publication date', () => {
  const preview = newsPreview(article, ['Nepal'])
  assert.equal(preview.artifact.source, 'GDELT')
  assert.equal('id' in preview.artifact, false)
  assert.equal('published_at' in preview.artifact, false)
  assert.equal(preview.raw[0].body, article)
  assert.equal(preview.summary.sections[0].fields[1].value, '2026-09-09 12:15 UTC')
})
