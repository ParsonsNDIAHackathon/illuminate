import assert from 'node:assert/strict'
import test from 'node:test'
import { mapNews, nearbyNews, newsDate, type NewsArticle } from '../src/newsMap.ts'
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

const regions = [
  { code: 'US-MD', country: 'US', name: 'Maryland', latitude: 39, longitude: -77 },
  { code: 'US-VA', country: 'US', name: 'Virginia', latitude: 37, longitude: -79 },
  { code: 'US-WV', country: 'US', name: 'West Virginia', latitude: 39, longitude: -80 },
  { code: 'US-GA', country: 'US', name: 'Georgia', latitude: 32, longitude: -83 },
]
test('local headlines map to state centroids without publisher-based guesses', () => {
  const r = mapNews([article('Earthquake in Maryland'), article('West Virginia flood recovery'), article('An unspecified town floods')], countries, regions)
  assert.equal(r.mapped, 2)
  assert.deepEqual(r.places.map(p => p.code), ['US-MD', 'US-WV'])
  assert.equal(r.unmapped.length, 1)
})
test('state precision supersedes a same-country marker; ambiguous states need country context', () => {
  const r = mapNews([article('United States: flood in Maryland'), article('Georgia protests')], countries, regions)
  assert.deepEqual(r.places.map(p => p.code), ['US-MD'])
  assert.equal(r.mapped, 1)
})
test('country abbreviations and names respect real Unicode boundaries', () => {
  const r = mapNews([article('US flood recovery'), article('Help us recover'), article('Prussian history'), article('U.S. flood response')], countries)
  assert.equal(r.mapped, 2)
  assert.equal(mapNews([article('UAS flood response')], countries).mapped, 0)
})

test('nearby news excludes distant and unplaced articles and keeps only nearby placements', () => {
  const data = mapNews([article('Russia and Ukraine hold talks'), article('US flood'), article('Unknown town')], countries)
  const filtered = nearbyNews(data, [{ latitude: 49, longitude: 33 }], [])
  assert.deepEqual(filtered.places.map(p => p.code), ['UA'])
  assert.equal(filtered.mapped, 1)
  assert.equal(filtered.urls.has(article('US flood').url), false)
  assert.equal(nearbyNews(data, [], []).mapped, 0)
})
test('route proximity includes segment interiors and respects the radius and endpoints', () => {
  const points = [
    { code: 'A', name: 'Alpha', latitude: 1, longitude: 0 },
    { code: 'B', name: 'Bravo', latitude: 3, longitude: 0 },
    { code: 'C', name: 'Charlie', latitude: 0, longitude: 14 },
  ]
  const data = mapNews(points.map(p => article(p.name)), points)
  const route = [{ latitude: 0, longitude: -10 }, { latitude: 0, longitude: 10 }]
  assert.deepEqual(nearbyNews(data, [], [route]).places.map(p => p.code), ['A'])
  assert.equal(nearbyNews(data, [], [route], 50).mapped, 0)
  assert.equal(nearbyNews(data, [], []).mapped, 0)
})
test('Pacific routes do not match news across the Atlantic and duplicate placements count once', () => {
  const points = [
    { code: 'A', name: 'Alpha', latitude: 0, longitude: 179 },
    { code: 'B', name: 'Bravo', latitude: 0, longitude: -179 },
    { code: 'C', name: 'Charlie', latitude: 0, longitude: 0 },
  ]
  const data = mapNews([article('Alpha and Bravo'), article('Charlie')], points)
  const result = nearbyNews(data, [], [[{ latitude: 0, longitude: 170 }, { latitude: 0, longitude: -170 }]])
  assert.deepEqual(result.places.map(p => p.code), ['A', 'B'])
  assert.equal(result.mapped, 1)
})

test('identified locality replaces state and country centers and drives proximity filtering', () => {
  const local = { code: 'geonames:1', name: 'Silver Spring, Maryland', country: 'US', latitude: 38.99, longitude: -77.03, precision: 'locality' as const, source: 'GeoNames', evidence: 'silver spring' }
  const story = { ...article('Earthquake near Silver Spring, Maryland, United States'), locations: [local] }
  const result = mapNews([story], countries, regions)
  assert.deepEqual(result.places.map(p => p.code), ['geonames:1'])
  assert.equal(result.places[0].latitude, 38.99)
  assert.equal(nearbyNews(result, [{ latitude: 38.99, longitude: -77.03 }], [], 1).mapped, 1)
  assert.equal(nearbyNews(result, [{ latitude: 39, longitude: -77 }], [], 1).mapped, 0)
})
test('invalid locality coordinates retain the regional fallback', () => {
  const result = mapNews([{ ...article('Maryland earthquake'), locations: [{ code: 'invalid', name: 'Invalid', country: 'US', latitude: 999, longitude: 0, precision: 'locality', source: '', evidence: '' }] }], countries, regions)
  assert.deepEqual(result.places.map(p => p.code), ['US-MD'])
})
