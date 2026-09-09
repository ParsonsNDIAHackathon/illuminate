import assert from 'node:assert/strict'
import test, { beforeEach } from 'node:test'

import { createPinia, setActivePinia } from 'pinia'

import { useGraph } from '../src/stores/graph.ts'
import type { StyleOp } from '../src/styles/styleOps.ts'

beforeEach(() => setActivePinia(createPinia()))

const MUTE: StyleOp = { op: 'dim', scope: 'all' }
const PATHS: StyleOp = { op: 'highlight', ids: ['de-1', 'de-2'], style: { stroke: 'teal' }, label: 'To Germany' }
const PEOPLE: StyleOp = { op: 'set', ids: ['p-1', 'p-2'], style: { fill: 'pink' }, label: 'Company B staff' }

/** One chat turn: the socket announces it, each tool result arrives on its own, then the
 *  answer repeats the whole turn's ops. Both arrivals are what the store has to survive. */
function turn(graph: ReturnType<typeof useGraph>, ...ops: StyleOp[]) {
  graph.beginStyleTurn()
  for (const op of ops) graph.appendStyleOps([op])
  graph.setTurnStyleOps(ops)
}

test('a turn adds to the encodings already on the canvas', () => {
  const graph = useGraph()
  turn(graph, MUTE, PATHS)
  turn(graph, PEOPLE)
  assert.deepEqual(graph.styleOps, [MUTE, PATHS, PEOPLE])
})

test("the answer's repeat of a turn does not double up its ops", () => {
  const graph = useGraph()
  turn(graph, MUTE, PATHS)
  assert.equal(graph.styleOps.length, 2)
  // Nor does the legend count the same elements twice.
  assert.deepEqual(graph.legend, [{ swatch: 'teal', label: 'To Germany', count: 2 }])
})

test('the legend carries every live encoding, not just the last turn', () => {
  const graph = useGraph()
  turn(graph, PATHS)
  turn(graph, PEOPLE)
  assert.deepEqual(graph.legend.map(l => l.label), ['To Germany', 'Company B staff'])
})

test('a turn that styles nothing leaves the canvas as it was', () => {
  const graph = useGraph()
  turn(graph, MUTE, PATHS)
  graph.beginStyleTurn()   // a question, answered in words, with no set_styles call
  assert.deepEqual(graph.styleOps, [MUTE, PATHS])
})

test('clearing drops the accumulated ops and starts a fresh base', () => {
  const graph = useGraph()
  turn(graph, MUTE, PATHS)
  graph.clearStyleOps()
  assert.deepEqual(graph.styleOps, [{ op: 'clear', scope: 'all' }])
  assert.deepEqual(graph.legend, [])
  turn(graph, PEOPLE)
  assert.deepEqual(graph.styleOps, [{ op: 'clear', scope: 'all' }, PEOPLE])
})

test('a clear from the model prunes what it would only wipe on replay', () => {
  const graph = useGraph()
  turn(graph, MUTE, PATHS)
  turn(graph, { op: 'clear', scope: 'all' }, PEOPLE)
  assert.deepEqual(graph.styleOps, [{ op: 'clear', scope: 'all' }, PEOPLE])
})

test('the op list stays bounded across a long styling session', () => {
  const graph = useGraph()
  for (let i = 0; i < 300; i++) turn(graph, { op: 'set', ids: [`n-${i}`], style: { fill: 'blue' }, label: `op ${i}` })
  assert.equal(graph.styleOps.length, 200)
  // The oldest go, so the newest encoding is always the one still drawn.
  assert.equal(graph.styleOps.at(-1)?.label, 'op 299')
})
