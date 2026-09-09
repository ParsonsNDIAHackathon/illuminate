import assert from 'node:assert/strict'
import test from 'node:test'
import { inMapViewport, visibleNewsArticles } from '../src/mapViewport.ts'

test('zoom and pan restrict map rows to marker centres in the current view', () => {
  const us = { latitude: 40, longitude: -100 }
  const europe = { latitude: 50, longitude: 10 }
  assert.ok(inMapViewport(us, [540, 270], 1))
  assert.ok(inMapViewport(europe, [540, 270], 1))
  assert.ok(inMapViewport(us, [240, 150], 4))
  assert.equal(inMapViewport(europe, [240, 150], 4), false)
  assert.ok(inMapViewport(europe, [570, 120], 4))
  assert.equal(inMapViewport(us, [570, 120], 4), false)
})

test('viewport includes boundaries and zero coordinates but excludes unplaced records', () => {
  assert.ok(inMapViewport({ latitude: 45, longitude: 90 }, [540, 270], 2))
  assert.equal(inMapViewport({ latitude: 45, longitude: 90.01 }, [540, 270], 2), false)
  assert.ok(inMapViewport({ latitude: 0, longitude: 0 }, [540, 270], 20))
  assert.equal(inMapViewport({ latitude: null, longitude: null }, [540, 270], 1), false)
  assert.equal(inMapViewport({ latitude: NaN, longitude: 0 }, [540, 270], 1), false)
})

test('news rows exclude offscreen and unplaced articles without duplicating multi-country news', () => {
  const articles = [{ url: 'shared' }, { url: 'offscreen' }, { url: 'unplaced' }]
  const visible = [{ code: 'US', articles: [articles[0]!] }, { code: 'CA', articles: [articles[0]!] }]
  assert.deepEqual(visibleNewsArticles(articles, visible), [articles[0]])
  assert.deepEqual(visibleNewsArticles(articles, visible, 'CA'), [articles[0]])
  assert.deepEqual(visibleNewsArticles(articles, visible, 'FR'), [])
  assert.deepEqual(visibleNewsArticles(articles, []), [])
})
