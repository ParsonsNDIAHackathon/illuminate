import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { acledPlaces, type AcledSnapshot } from '../src/acledMap.ts'

const snapshot = JSON.parse(readFileSync(new URL('../src/data/acledMap.json', import.meta.url), 'utf8'))

test('ACLED totals reconcile to the generated source controls for all periods', () => {
  for (const period of ['7d', '1m', '3m', '12m'] as const) {
    const places = acledPlaces(snapshot, period)
    assert.deepEqual([places.reduce((n, p) => n + p.events, 0), places.reduce((n, p) => n + p.fatalities, 0)], snapshot.totals[period])
    assert.ok(places.length > 0)
    assert.equal(new Set(places.map(p => p.id)).size, places.length)
    assert.ok(places.every(p => (p.latitude === null && p.longitude === null) || (p.latitude! >= -90 && p.latitude! <= 90 && p.longitude! >= -180 && p.longitude! <= 180)))
  }
  assert.equal(snapshot.sources.length, 6)
  assert.equal(snapshot.through, snapshot.sources.map((s: { through: string }) => s.through).sort()[0])
})

test('country and event type filters retain only matching activity', () => {
  const data = { places: [
    { id: 'one', country: 'A', periods: { '7d': { Battles: [4, 2], Protests: [3, 0] } } },
    { id: 'two', country: 'B', periods: { '7d': { Battles: [9, 8] } } },
  ] } as unknown as AcledSnapshot
  const results = acledPlaces(data, '7d', 'Protests', 'A')
  assert.equal(results.length, 1)
  assert.equal(results[0]?.events, 3)
  assert.equal(results[0]?.fatalities, 0)
  assert.deepEqual(results[0]?.breakdown, [{ type: 'Protests', events: 3, fatalities: 0 }])
  assert.deepEqual(acledPlaces(data, '1m'), [])
  assert.deepEqual(acledPlaces(data, '7d', '', 'Missing'), [])
  assert.deepEqual(acledPlaces(null, '7d'), [])
})

test('snapshot includes source provenance for every area and no country-summary totals', () => {
  for (const place of snapshot.places) {
    assert.ok(place.sources.length)
    for (const index of place.sources) assert.match(snapshot.sources[index].filename, /_aggregated_data_/)
  }
  assert.ok(snapshot.overlappingRowsExcluded > 0)
})

// Independently checked against the US workbook with openpyxl (45 source rows).
test('United States latest-week total matches the workbook', () => {
  const places = acledPlaces(snapshot, '7d', '', 'United States')
  assert.equal(places.reduce((n, p) => n + p.events, 0), 126)
  assert.equal(places.reduce((n, p) => n + p.fatalities, 0), 0)
})
