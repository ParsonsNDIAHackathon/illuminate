import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { useTransport } from '../src/stores/transport.ts'
import { shippingPath } from '../src/shippingMap.ts'
const data = JSON.parse(readFileSync(new URL('../../api/illuminate/transport_network.json', import.meta.url), 'utf8'))

test('reference filters separate highways and rail without requiring graph entities', () => {
  const store = useTransport(createPinia())
  store.corridors = data.corridors
  assert.equal(store.visible.length, 14)
  store.highways = false
  assert.equal(store.visible.length, 3)
  store.query = 'Chicago'
  assert.equal(store.visible.length, 3)
  store.query = 'Norfolk'
  assert.equal(store.visible.length, 1)
  store.rail = false
  assert.equal(store.visible.length, 0)
  store.highways = true; store.query = 'I-40'
  assert.equal(store.visible[0].id, 'i-40')
})
test('failed refresh keeps previous reference and supports retry', async t => {
  const store = useTransport(createPinia()); store.corridors = data.corridors
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Unavailable' }, { status: 503 }))
  await store.load()
  assert.equal(store.corridors.length, 14)
  assert.ok(store.error)
  t.mock.method(globalThis, 'fetch', async () => Response.json(data))
  await store.load()
  assert.equal(store.error, '')
})
test('reference geometry renders without invalid points or date-line splits', () => {
  for (const c of data.corridors) {
    const path = shippingPath(c.points)
    assert.ok(!path.includes('NaN'))
    assert.equal(path.split('M').length, 2)
  }
})
