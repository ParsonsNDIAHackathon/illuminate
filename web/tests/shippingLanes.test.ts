import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { useShippingLanes } from '../src/stores/shippingLanes.ts'
import { routePath } from '../src/shippingMap.ts'
const catalog = JSON.parse(readFileSync(new URL('../../api/illuminate/shipping_lanes.json', import.meta.url), 'utf8'))
test('established lanes appear without graph entities or relationships', () => {
  setActivePinia(createPinia())
  const store = useShippingLanes()
  store.catalog = catalog
  assert.equal(store.enabled, true)
  assert.equal(store.lanes.length, 7)
  store.port = 'oakland'
  assert.equal(store.lanes.length, 1)
  store.port = ''
  store.query = 'TP8'
  assert.equal(store.lanes.length, 2)
  store.query = 'no-match'
  assert.equal(store.lanes.length, 0)
})
test('reference paths render with dated sources and no supplier assertions', () => {
  for (const lane of catalog.lanes) {
    assert.ok(lane.source.reference.startsWith('https://'))
    assert.equal(lane.published_at, '2026-08-05')
    assert.equal(lane.relationship_id, undefined)
    assert.ok(routePath(lane, catalog.ports).startsWith('M'))
    assert.ok(!routePath(lane, catalog.ports).includes('NaN'))
  }
})
