import assert from 'node:assert/strict'
import test from 'node:test'
import { deriveFindingPath } from '../src/graphFocusPath.ts'

const nodes = ['program', 'prime', 'vendor', 'owner', 'country'].map(id => ({ id }))
const edges = [
  { id: 's1', source: 'prime', target: 'program', type: 'SUPPLIES' },
  { id: 's2', source: 'vendor', target: 'prime', type: 'SUPPLIES' },
  { id: 'owns', source: 'owner', target: 'vendor', type: 'ULTIMATE_PARENT_OF' },
  { id: 'seat', source: 'owner', target: 'country', type: 'PARENT_SEATED_IN' },
  // This is a shorter undirected route, but is outside the report's ownership family.
  { id: 'unrelated', source: 'vendor', target: 'country', type: 'OPERATES_IN' },
]

test('finding paths use the same directed supply and family-constrained risk route', () => {
  const result = deriveFindingPath(nodes, edges, ['country'], 'vendor', 'program', 'ownership')
  assert.deepEqual([...result.pathIds].sort(), ['country', 'owns', 'owner', 'prime', 'program', 's1', 's2', 'seat', 'vendor'].sort())
  assert.equal(result.pathIds.has('unrelated'), false)
  assert.deepEqual([...result.riskIds], ['country'])
})

test('missing report elements are exposed without inventing a path', () => {
  const result = deriveFindingPath(nodes, edges, ['missing'], 'vendor', 'program', 'ownership')
  assert.deepEqual(result.unavailableIds, ['missing'])
  assert.equal(result.pathIds.has('missing'), false)
})