import assert from 'node:assert/strict'
import test from 'node:test'

import { filterFocusedDelta } from '../src/stores/graphDelta.ts'

const node = (id: string, kind = 'organization') => ({
  id,
  label: 'Entity',
  props: { kind },
})
const edge = (id: string, source: string, target: string) => ({
  id,
  source,
  target,
})

test('a focused program ignores a disconnected delta for another program', () => {
  const filtered = filterFocusedDelta(
    {
      nodes: [node('program-b', 'program'), node('supplier-b')],
      edges: [edge('supplies-b', 'supplier-b', 'program-b')],
    },
    new Set(['program-a', 'supplier-a']),
    'program-a',
  )

  assert.deepEqual(filtered, { nodes: [], edges: [] })
})

test('a focused program accepts a new chain connected to an existing node', () => {
  const filtered = filterFocusedDelta(
    {
      nodes: [
        node('supplier-a'),
        { id: 'claim-a', label: 'Claim', props: {} },
        { id: 'artifact-a', label: 'Artifact', props: {} },
      ],
      edges: [
        edge('evidence-a', 'artifact-a', 'claim-a'),
        edge('assert-a', 'claim-a', 'supplier-a'),
      ],
    },
    new Set(['program-a', 'supplier-a']),
    'program-a',
  )

  assert.deepEqual(
    new Set(filtered.nodes.map(item => item.id)),
    new Set(['supplier-a', 'claim-a', 'artifact-a']),
  )
  assert.equal(filtered.edges.length, 2)
})