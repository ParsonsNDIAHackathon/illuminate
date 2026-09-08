import assert from 'node:assert/strict'
import test from 'node:test'

import cytoscape from 'cytoscape'

import { hiddenNodeIds, indirectOrganizations, layerData, layerVisible, orphanedOrganizations } from '../src/stores/graphLayers.ts'

const claim = { id: 'claim-a', label: 'Claim', props: {} }
const source = { id: 'source-a', label: 'Artifact', props: { kind: 'record' } }
const document = { id: 'document-a', label: 'Artifact', props: { kind: 'filing' } }
const nodes = [
  { id: 'entity-a', label: 'Entity', props: { kind: 'organization' } },
  { id: 'person-a', label: 'Person', props: {} },
  { id: 'country-a', label: 'Location', props: {} },
  { id: 'category-a', label: 'Category', props: {} },
  claim,
  source,
  document,
]

function renderedWith(layers: Record<string, boolean>) {
  const cy = cytoscape({
    headless: true,
    elements: nodes.map(node => ({
      group: 'nodes',
      data: { id: node.id, ...layerData(node) },
    })),
  })
  cy.nodes().forEach(node => {
    node.toggleClass('layer-hide', !layerVisible(node.data('layer'), layers))
  })
  return cy
}

test('disabled layers remain hidden when projected into Cytoscape data', () => {
  const cy = renderedWith({
    people: false,
    countries: false,
    categories: false,
    claims: false,
    sources: false,
    artifacts: false,
  })

  assert.equal(cy.getElementById('entity-a').data('layer'), null)
  assert.equal(cy.getElementById('entity-a').hasClass('layer-hide'), false)
  for (const id of ['person-a', 'country-a', 'category-a', 'claim-a', 'source-a', 'document-a']) {
    assert.equal(cy.getElementById(id).hasClass('layer-hide'), true, `${id} should be hidden`)
  }
  assert.equal(cy.getElementById('claim-a').data('layer'), 'claims')
  assert.equal(cy.getElementById('person-a').data('layer'), 'people')
  assert.equal(cy.getElementById('country-a').data('layer'), 'countries')
  assert.equal(cy.getElementById('category-a').data('layer'), 'categories')
})

test('source records and documents obey independent layer toggles', () => {
  const sourcesOnly = renderedWith({ claims: false, sources: true, artifacts: false })
  assert.equal(sourcesOnly.getElementById('source-a').data('layer'), 'sources')
  assert.equal(sourcesOnly.getElementById('source-a').hasClass('layer-hide'), false)
  assert.equal(sourcesOnly.getElementById('document-a').data('layer'), 'artifacts')
  assert.equal(sourcesOnly.getElementById('document-a').hasClass('layer-hide'), true)

  const documentsOnly = renderedWith({ claims: false, sources: false, artifacts: true })
  assert.equal(documentsOnly.getElementById('source-a').hasClass('layer-hide'), true)
  assert.equal(documentsOnly.getElementById('document-a').hasClass('layer-hide'), false)
})

// A program, its supplier, a director of that supplier who also sits on two other boards (one of
// those companies owning a subsidiary), a company known only by where it is incorporated, and a
// company nothing points at. Person nodes come with the "people" layer; entities always arrive.
const org = (id: string) => ({ id, label: 'Entity', layer: null, props: { kind: 'organization' } })
const network = {
  nodes: [
    { id: 'program', label: 'Entity', layer: null, props: { kind: 'program' } },
    org('supplier'),
    { id: 'director', label: 'Person', layer: 'people', props: {} },
    org('board-seat'),
    org('club'),
    org('club-subsidiary'),
    org('seated-only'),
    { id: 'country', label: 'Location', layer: 'countries', props: {} },
    org('isolated'),
  ],
  edges: [
    { source: 'supplier', target: 'program' },
    { source: 'director', target: 'supplier' },
    { source: 'director', target: 'board-seat' },
    { source: 'director', target: 'club' },
    { source: 'club', target: 'club-subsidiary' },
    { source: 'seated-only', target: 'country' },
  ],
}
const hiddenWith = (layers: Record<string, boolean>, keep: string[] = []) =>
  [...hiddenNodeIds(network.nodes, network.edges, layers, keep)].sort()

test('hiding the people layer also hides the organizations only people reached', () => {
  const hidden = hiddenWith({ people: false, countries: false })
  assert.deepEqual(hidden, ['board-seat', 'country', 'director', 'seated-only'])
  // Two companies still joined to each other are an island, not orphans: the indirect filter's job.
  assert.ok(!hidden.includes('club') && !hidden.includes('club-subsidiary'))
})

test('an organization stays while anything visible still points at it', () => {
  assert.deepEqual(hiddenWith({ people: true, countries: false }), ['country', 'seated-only'])
  assert.deepEqual(hiddenWith({ people: false, countries: true }), ['board-seat', 'director'])
})

test('programs, the root and organizations with no edges are never pruned', () => {
  const hidden = hiddenWith({ people: false, countries: false }, ['board-seat'])
  assert.ok(!hidden.includes('program'))
  assert.ok(!hidden.includes('isolated'))
  assert.ok(!hidden.includes('board-seat'), 'the root is kept')
})

test('the indirect-orgs toggle hides organizations no entity chain joins to a program, whatever the layers show', () => {
  // An organization with no edges at all counts as indirect too: nothing joins it to anything.
  assert.deepEqual(hiddenWith({ people: true, countries: true, indirect_orgs: false }), ['board-seat', 'club', 'club-subsidiary', 'isolated', 'seated-only'])
  // The default is to show them.
  assert.deepEqual(hiddenWith({ people: true, countries: true }), [])
})

test('the indirect walk starts from the root too, and from nothing when the canvas has no anchor', () => {
  const noProgram = { nodes: network.nodes.filter(n => n.id !== 'program'), edges: network.edges.filter(e => e.target !== 'program') }
  const hidden = new Set<string>()
  assert.deepEqual([...indirectOrganizations(noProgram.nodes, noProgram.edges, hidden)], [])
  assert.deepEqual([...indirectOrganizations(noProgram.nodes, noProgram.edges, hidden, ['supplier'])].sort(), ['board-seat', 'club', 'club-subsidiary', 'isolated', 'seated-only'])
})

test('orphan pruning ignores self-loops and edges to nodes that are not loaded', () => {
  const nodes = [{ id: 'p', label: 'Person', layer: 'people', props: {} }, org('a')]
  const edges = [{ source: 'p', target: 'a' }, { source: 'a', target: 'a' }, { source: 'a', target: 'missing' }]
  assert.deepEqual([...orphanedOrganizations(nodes, edges, new Set(['p']))], ['a'])
})
