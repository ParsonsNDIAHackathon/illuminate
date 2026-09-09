import assert from 'node:assert/strict'
import test from 'node:test'
import { buildMapPlaces, matchesMapEntry } from '../src/graphMap.ts'

const countries = [{ code: 'US', name: 'United States', latitude: 38, longitude: -97 }]
const node = (id: string, label = 'Entity', props = {}) => ({ id, label, name: id, props })
const edge = (id: string, source: string, target: string, type = 'OPERATES_IN') => ({ id, source, target, type, props: {} })

test('regional relationships aggregate by country and preserve evidence edges', () => {
  const nodes = [node('supplier'), node('other'), node('state', 'Location', { code: 'US-CA' })]
  const edges = [edge('a', 'supplier', 'state'), edge('b', 'supplier', 'state', 'INCORPORATED_IN')]
  const result = buildMapPlaces(nodes, edges, countries)
  assert.equal(result.mappedCount, 1)
  assert.equal(result.unmappedCount, 1)
  assert.equal(result.places.length, 1)
  assert.equal(result.places[0].precise, false)
  assert.equal(result.places[0].entries.length, 2)
  assert.equal(result.places[0].entries[0].location?.props.code, 'US-CA')
})

test('zero coordinates are valid; missing, blank and invalid coordinates remain unplaced', () => {
  const nodes = [node('zero', 'Entity', { latitude: 0, longitude: 0 }),
    node('bad', 'Entity', { latitude: 91, longitude: 20 }),
    node('blank', 'Entity', { latitude: '', longitude: null }),
    node('missing', 'Entity', { latitude: 20 })]
  const result = buildMapPlaces(nodes, [], countries)
  assert.equal(result.mappedCount, 1)
  assert.equal(result.unmappedCount, 3)
  assert.equal(result.places[0].latitude, 0)
  assert.equal(result.places[0].precise, true)
})

test('publisher country, supplier links and unknown locations do not invent geographic placements', () => {
  const nodes = [node('news', 'Artifact', { sourcecountry: 'US' }), node('supplier'), node('country', 'Location', { code: 'US' }), node('unknown', 'Location', { code: 'ZZ' })]
  const result = buildMapPlaces(nodes, [edge('supply', 'supplier', 'country', 'SUPPLIES'), edge('unknown-location', 'supplier', 'unknown')], countries)
  assert.equal(result.places.length, 0)
  assert.equal(result.unmappedCount, 1)
})

test('search matches entity identifiers and regional codes', () => {
  const entry = { node: node('supplier', 'Entity', { uei: 'ABC123' }), location: node('California', 'Location', { code: 'US-CA' }) }
  assert.ok(matchesMapEntry(entry, 'abc123 US-CA'))
  assert.equal(matchesMapEntry(entry, 'France'), false)
})

test('exact location coordinates and simulated evidence remain identifiable', () => {
  const nodes = [node('supplier'), node('facility', 'Location', { latitude: '38', longitude: '-122' })]
  const relation = { ...edge('a', 'supplier', 'facility'), props: { simulated: true } }
  const result = buildMapPlaces(nodes, [relation], countries)
  assert.equal(result.places.length, 1)
  assert.equal(result.places[0].precise, true)
  assert.ok(result.places[0].entries.find(e => e.edge?.props.simulated))
})

test('state and province records use subdivision label points without moving country-only records', () => {
  const regions = [{ code: 'US-CA', name: 'California', latitude: 37, longitude: -119 }, { code: 'CA-ON', name: 'Ontario', latitude: 50, longitude: -86 }]
  const allCountries = [...countries, { code: 'CA', name: 'Canada', latitude: 60, longitude: -100 }]
  const nodes = [node('supplier'), node('state', 'Location', { code: 'US-CA' }), node('province', 'Location', { code: 'CA-ON' }), node('country', 'Location', { code: 'US' })]
  const result = buildMapPlaces(nodes, [edge('a', 'supplier', 'state'), edge('b', 'supplier', 'province'), edge('c', 'supplier', 'country')], allCountries, regions)
  assert.equal(result.mappedCount, 1)
  assert.equal(result.places.length, 3)
  const state = result.places.find(p => p.key === 'region:US-CA')!
  assert.equal(state.latitude, 37)
  assert.equal(state.region, true)
  assert.equal(state.precise, false)
  assert.equal(result.places.find(p => p.key === 'region:CA-ON')?.name, 'Ontario, Canada')
  assert.equal(result.places.find(p => p.key === 'country:US')?.latitude, 38)
})
