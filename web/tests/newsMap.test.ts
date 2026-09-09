import assert from 'node:assert/strict'
import test from 'node:test'
import { mapNews, newsDate, type NewsArticle } from '../src/newsMap.ts'
const countries = [
  { code: 'UA', name: 'Ukraine', latitude: 49, longitude: 32 },
  { code: 'RU', name: 'Russia', latitude: 60, longitude: 100 },
  { code: 'US', name: 'United States', latitude: 38, longitude: -97 },
]
const article = (title: string): NewsArticle => ({ title, url: `https://news.example/${title}`, domain: 'news.example', language: 'English', seendate: '20260909T121500Z' })
test('places multi-country coverage and counts each article once', () => {
  const result = mapNews([article('Russia and Ukraine hold talks'), article('Ukrainian flood response')], countries)
  assert.equal(result.mapped, 2)
  assert.equal(result.places.length, 2)
  assert.equal(result.places[0].articles.length, 2)
})
test('keeps unknown locations unplaced and avoids substring matches', () => {
  const result = mapNews([article('Flood in a small town'), article('Prussian history'), article('U.S. flood response')], countries)
  assert.equal(result.mapped, 1)
  assert.equal(result.unmapped.length, 2)
  assert.equal(result.places[0].code, 'US')
})
test('formats GDELT seen timestamps without inventing publication dates', () => {
  assert.equal(newsDate('20260909T121500Z'), '2026-09-09 12:15 UTC')
  assert.equal(newsDate(''), '')
})
