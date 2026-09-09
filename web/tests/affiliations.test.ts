import test from 'node:test'
import assert from 'node:assert/strict'
import { affiliationGroups, affiliationVisibility } from '../src/affiliations.ts'
import type { GNode, GEdge } from '../src/stores/graph'

const node = (id: string, label = 'Entity', props = {}): GNode => ({ id, name: id, label, props })
const edge = (id: string, source: string, target: string, type: string, props = {}): GEdge => ({ id, source, target, type, props })
function fixture() {
  const nodes = [node('program', 'Entity', { kind: 'program' }), node('supplier'), node('director', 'Person'), node('other'), node('recipient'), node('unconnected')]
  const edges = [edge('contract', 'supplier', 'program', 'SUPPLIES'), edge('board1', 'director', 'supplier', 'HELD_ROLE', { role_type: 'board' }), edge('board2', 'director', 'other', 'HELD_ROLE'), edge('gift', 'supplier', 'recipient', 'DONATED_TO')]
  return { nodes, edges }
}

test('collapse groups by recorded relationship and reveal the real person bridge on expansion', () => {
  const { nodes, edges } = fixture(), model = affiliationGroups(nodes, edges)
  const board = model.groups.find(g => g.title === 'Board affiliations')!
  assert.equal(board.anchorId, 'supplier')
  assert.deepEqual(board.members.map(n => n.id), ['other'])
  assert.deepEqual(board.paths.get('other'), { nodes: ['supplier', 'director', 'other'], edges: ['board1', 'board2'] })
  const collapsed = affiliationVisibility(model, new Set())
  assert.ok(collapsed.hidden.has('other') && collapsed.hidden.has('director'))
  assert.ok(!collapsed.hidden.has('supplier') && !collapsed.hidden.has('program'))
  const expanded = affiliationVisibility(model, new Set([board.id]))
  assert.ok(expanded.visible.has('director') && expanded.visible.has('other'))
  assert.deepEqual([...expanded.pathEdges].sort(), ['board1', 'board2'])
  assert.ok(expanded.hidden.has('recipient'))
  assert.deepEqual(model.unconnected.map(n => n.id), ['unconnected'])
})

test('significant risks and their connecting paths cannot be collapsed', () => {
  const { nodes, edges } = fixture()
  nodes.find(n => n.id === 'other')!.props.risk_score = 75
  const view = affiliationVisibility(affiliationGroups(nodes, edges), new Set())
  for (const id of ['supplier', 'director', 'other']) {
    assert.ok(view.visible.has(id)); assert.ok(!view.hidden.has(id))
  }
  assert.ok(view.hidden.has('recipient'))
})

test('a risk with no known program path is still visible', () => {
  const { nodes, edges } = fixture()
  nodes.find(n => n.id === 'unconnected')!.props.risk_score = 21
  assert.ok(affiliationVisibility(affiliationGroups(nodes, edges), new Set()).visible.has('unconnected'))
})

test('selection and search reveal the path without expanding unrelated groups', () => {
  const { nodes, edges } = fixture()
  const view = affiliationVisibility(affiliationGroups(nodes, edges), new Set(), new Set(['other', 'unconnected']))
  assert.ok(view.visible.has('director') && view.visible.has('other') && view.visible.has('unconnected'))
  assert.ok(view.hidden.has('recipient'))
})

test('shared countries and documents do not manufacture affiliations', () => {
  const { nodes, edges } = fixture()
  nodes.push(node('country', 'Location'), node('doc', 'Artifact'))
  edges.push(edge('a', 'supplier', 'country', 'INCORPORATED_IN'), edge('b', 'unconnected', 'country', 'INCORPORATED_IN'), edge('c', 'doc', 'supplier', 'ABOUT'), edge('d', 'doc', 'unconnected', 'ABOUT'))
  assert.deepEqual(affiliationGroups(nodes, edges).unconnected.map(n => n.id), ['unconnected'])
})

test('shared organizations have one stable nearest group and are never duplicated', () => {
  const { nodes, edges } = fixture()
  nodes.push(node('supplier2'))
  edges.push(edge('contract2', 'supplier2', 'program', 'SUPPLIES'), edge('gift2', 'supplier2', 'recipient', 'DONATED_TO'))
  const a = affiliationGroups(nodes, edges), b = affiliationGroups([...nodes].reverse(), [...edges].reverse())
  const summarize = (model: typeof a) => model.groups.map(g => [g.id, g.members.map(n => n.id)])
  assert.deepEqual(summarize(a), summarize(b))
  const members = a.groups.flatMap(g => g.members.map(n => n.id))
  assert.equal(new Set(members).size, members.length)
})

test('supplier owners stay central while their other subsidiaries are grouped', () => {
  const { nodes, edges } = fixture()
  nodes.push(node('parent'), node('sibling'))
  edges.push(edge('owner', 'parent', 'supplier', 'OWNS'), edge('sister', 'parent', 'sibling', 'OWNS'))
  const model = affiliationGroups(nodes, edges)
  assert.ok(!model.indirect.has('parent'))
  assert.deepEqual(model.groups.find(g => g.title === 'Related companies')!.members.map(n => n.id), ['sibling'])
})

test('a graph without a program or focused anchor is not arbitrarily grouped', () => {
  const { nodes, edges } = fixture()
  const model = affiliationGroups(nodes.filter(n => n.id !== 'program'), edges)
  assert.equal(model.groups.length, 0)
  assert.equal(model.unconnected.length, 0)
})
