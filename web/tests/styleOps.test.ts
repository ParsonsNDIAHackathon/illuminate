import assert from 'node:assert/strict'
import test from 'node:test'

import cytoscape from 'cytoscape'

import { applyStyleOps, clearStyleOps } from '../src/styles/styleOps.ts'
import type { StyleOp } from '../src/styles/styleOps.ts'

// A program, two German suppliers on a path out of it, an unrelated supplier, and two
// people at one of them — enough to say "mute everything, highlight the paths to Germany,
// then colour these people" and check all three survive together.
const ELEMENTS = [
  { group: 'nodes', data: { id: 'program' } },
  { group: 'nodes', data: { id: 'de-1' } },
  { group: 'nodes', data: { id: 'de-2' } },
  { group: 'nodes', data: { id: 'other' } },
  { group: 'nodes', data: { id: 'person-1' } },
  { group: 'nodes', data: { id: 'person-2' } },
  { group: 'edges', data: { id: 'e-de1', source: 'de-1', target: 'program' } },
  { group: 'edges', data: { id: 'e-de2', source: 'de-2', target: 'de-1' } },
  { group: 'edges', data: { id: 'e-other', source: 'other', target: 'program' } },
]

const graph = () => cytoscape({ headless: true, elements: ELEMENTS as any })

/** The canvas replays the whole op list from a clean slate on every sync; so does this. */
function render(ops: StyleOp[]) {
  const cy = graph()
  clearStyleOps(cy)
  applyStyleOps(cy, ops, 'light')
  return cy
}

const dimmed = (cy: any) => cy.elements('.op-dim').map((e: any) => e.id()).sort()

const MUTE: StyleOp = { op: 'dim', scope: 'all' }
const PATHS: StyleOp = { op: 'highlight', ids: ['de-1', 'de-2', 'e-de1', 'e-de2'], style: { stroke: 'teal' }, label: 'To Germany' }
const PEOPLE: StyleOp = { op: 'set', ids: ['person-1', 'person-2'], style: { fill: 'pink' }, label: 'Company B staff' }

test('dim with a scope and no ids mutes the whole canvas', () => {
  assert.equal(render([MUTE]).elements('.op-dim').length, ELEMENTS.length)
  assert.equal(render([{ op: 'dim', scope: 'nodes' }]).edges('.op-dim').length, 0)
  assert.equal(render([{ op: 'dim', scope: 'edges' }]).nodes('.op-dim').length, 0)
})

test('hide honours a scope with no ids; set and highlight still need ids', () => {
  assert.equal(render([{ op: 'hide', scope: 'edges' }]).edges('.op-hide').length, 3)
  // An idless paint addresses nothing rather than repainting the graph.
  assert.equal(render([{ op: 'set', scope: 'all', style: { fill: 'red' } }]).elements('.op-fill').length, 0)
})

test('a later encoding stacks on the earlier ones instead of replacing them', () => {
  const cy = render([MUTE, PATHS, PEOPLE])
  // The mute still holds everywhere it was not painted over.
  assert.deepEqual(dimmed(cy), ['e-other', 'other', 'program'])
  // The path highlight from two turns ago is still drawn.
  assert.equal(cy.getElementById('de-1').hasClass('op-highlight'), true)
  assert.equal(cy.getElementById('e-de2').hasClass('op-highlight'), true)
  assert.equal(cy.getElementById('de-2').data('opStroke'), '#0f766e')
  // And the new one landed on top.
  assert.equal(cy.getElementById('person-1').data('opFill'), '#be185d')
  assert.equal(cy.getElementById('person-2').hasClass('op-fill'), true)
})

test('painting an element lifts an earlier mute off it', () => {
  const cy = render([MUTE, PEOPLE])
  assert.equal(cy.getElementById('person-1').hasClass('op-dim'), false)
  assert.equal(cy.getElementById('other').hasClass('op-dim'), true)
})

test('a later mute takes the graph back down, highlights included', () => {
  const cy = render([PATHS, MUTE])
  assert.equal(cy.getElementById('de-1').hasClass('op-dim'), true)
  assert.equal(cy.getElementById('de-1').hasClass('op-highlight'), true)
})

test('a clear op wipes what came before it and nothing after', () => {
  const cy = render([MUTE, PATHS, { op: 'clear', scope: 'all' }, PEOPLE])
  assert.equal(cy.elements('.op-dim').length, 0)
  assert.equal(cy.elements('.op-highlight').length, 0)
  assert.equal(cy.getElementById('person-1').data('opFill'), '#be185d')
})
