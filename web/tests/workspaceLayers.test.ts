import assert from 'node:assert/strict'
import test from 'node:test'

import { LAYERS_KEY, LAYERS_OFF, readLayers, writeLayers } from '../src/stores/layerPrefs.ts'

/** A stand-in for the browser's localStorage, returned so a test can look at what was written
 *  and read it back — which is what "next time this browser opens" means here. */
function stubStorage(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed))
  ;(globalThis as any).localStorage = {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => { map.set(k, String(v)) },
    removeItem: (k: string) => { map.delete(k) },
  }
  return map
}

test('the canvas opens with every optional layer off', () => {
  stubStorage()
  const layers = readLayers()
  assert.deepEqual(layers, LAYERS_OFF)
  // Entities are always drawn; everything else is asked for, the indirect-orgs filter included.
  assert.equal(layers.entities, true)
  assert.deepEqual(Object.entries(layers).filter(([k, v]) => v && k !== 'entities'), [])
})

test('a layer turned on is written to storage and is still on next time', () => {
  const store = stubStorage()
  writeLayers({ ...LAYERS_OFF, people: true })
  assert.equal(JSON.parse(store.get(LAYERS_KEY)!).people, true)
  const later = readLayers()
  assert.equal(later.people, true)
  assert.equal(later.countries, false)
})

test('a layer added since this browser last saved arrives off, not undefined', () => {
  stubStorage({ [LAYERS_KEY]: JSON.stringify({ entities: true, people: true }) })
  const layers = readLayers()
  assert.equal(layers.people, true)
  assert.equal(layers.reports, false, 'a key the saved map never had')
  assert.deepEqual(Object.keys(layers).sort(), Object.keys(LAYERS_OFF).sort())
})

test('unreadable storage falls back to all off rather than throwing', () => {
  stubStorage({ [LAYERS_KEY]: '{not json' })
  assert.deepEqual(readLayers(), LAYERS_OFF)
})

test('storage that refuses to answer at all costs the next visit, not this one', () => {
  // A private window, or a browser set to block site data: every accessor throws.
  ;(globalThis as any).localStorage = {
    getItem() { throw new Error('denied') },
    setItem() { throw new Error('denied') },
  }
  assert.deepEqual(readLayers(), LAYERS_OFF)
  assert.doesNotThrow(() => writeLayers({ ...LAYERS_OFF, claims: true }))
})
