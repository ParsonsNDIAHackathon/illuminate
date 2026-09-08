import assert from 'node:assert/strict'
import test from 'node:test'

import { restrictDeltaToFocus } from '../src/stores/graphDelta.ts'

const program = (id: string) => ({ id, label: 'Entity', props: { kind: 'program' } })
const supplier = (id: string) => ({ id, label: 'Entity', props: { kind: 'organization' } })
const edge = (id: string, source: string, target: string, type = 'SUPPLIES') => ({ id, source, target, type })
const canvas = {
  nodes: [program('program-a'), supplier('prime-a')],
  edges: [edge('prime-link', 'prime-a', 'program-a')],
}

test('an unrelated program update cannot add its supplier to a focused canvas', () => {
  const result = restrictDeltaToFocus(
    {
      nodes: [program('program-b'), supplier('supplier-b')],
      edges: [edge('supplies-b', 'supplier-b', 'program-b')],
    },
    canvas,
    'program-a',
  )

  assert.deepEqual(result, { nodes: [], edges: [] })
})

test('a connected multi-hop supplier arrival is retained', () => {
  const result = restrictDeltaToFocus(
    {
      nodes: [supplier('prime-a'), supplier('tier-2-new'), supplier('tier-3-new')],
      edges: [
        edge('tier-2-link', 'tier-2-new', 'prime-a'),
        edge('tier-3-link', 'tier-3-new', 'tier-2-new'),
      ],
    },
    canvas,
    'program-a',
  )

  assert.deepEqual(result.nodes.map(node => node.id), ['prime-a', 'tier-2-new', 'tier-3-new'])
  assert.deepEqual(result.edges.map(item => item.id), ['tier-2-link', 'tier-3-link'])
})

test('a focused program accepts an evidence chain connected to an existing supplier', () => {
  const result = restrictDeltaToFocus(
    {
      nodes: [
        supplier('prime-a'),
        { id: 'claim-a', label: 'Claim', props: {} },
        { id: 'artifact-a', label: 'Artifact', props: {} },
      ],
      edges: [
        edge('evidence-a', 'artifact-a', 'claim-a', 'EVIDENCES'),
        edge('assert-a', 'claim-a', 'prime-a', 'ASSERTS'),
      ],
    },
    canvas,
    'program-a',
  )

  assert.deepEqual(new Set(result.nodes.map(item => item.id)), new Set(['prime-a', 'claim-a', 'artifact-a']))
  assert.equal(result.edges.length, 2)
})

test('a shared country cannot admit another program supplier', () => {
  const country = { id: 'country-us', label: 'Location', props: {} }
  const result = restrictDeltaToFocus(
    {
      nodes: [program('program-b'), supplier('supplier-b'), supplier('prime-a'), country],
      edges: [
        edge('supplier-b-link', 'supplier-b', 'program-b'),
        edge('supplier-b-country', 'supplier-b', 'country-us', 'INCORPORATED_IN'),
        edge('prime-country', 'prime-a', 'country-us', 'INCORPORATED_IN'),
      ],
    },
    {
      nodes: [...canvas.nodes, country],
      edges: [...canvas.edges, edge('prime-country', 'prime-a', 'country-us', 'INCORPORATED_IN')],
    },
    'program-a',
  )

  assert.deepEqual(result.nodes.map(node => node.id), ['prime-a', 'country-us'])
  assert.deepEqual(result.edges.map(item => item.id), ['prime-country'])
})

test('a shared subcontractor cannot admit another program prime', () => {
  const shared = supplier('shared-subcontractor')
  const result = restrictDeltaToFocus(
    {
      nodes: [shared, supplier('prime-a'), supplier('prime-b'), program('program-b')],
      edges: [
        edge('shared-to-a', 'shared-subcontractor', 'prime-a'),
        edge('shared-to-b', 'shared-subcontractor', 'prime-b'),
        edge('prime-b-program', 'prime-b', 'program-b'),
      ],
    },
    {
      nodes: [...canvas.nodes, shared],
      edges: [...canvas.edges, edge('shared-to-a', 'shared-subcontractor', 'prime-a')],
    },
    'program-a',
  )

  assert.deepEqual(result.nodes.map(node => node.id), ['shared-subcontractor', 'prime-a'])
  assert.deepEqual(result.edges.map(item => item.id), ['shared-to-a'])
})