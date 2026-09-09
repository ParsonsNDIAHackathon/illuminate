import assert from 'node:assert/strict'
import test from 'node:test'

import cytoscape from 'cytoscape'

import { hiddenNodeIds, indirectOrganizations, layerData, layerVisible, orphanedOrganizations, riskPinnedNodes } from '../src/stores/graphLayers.ts'

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

// A program, its supplier and the supplier's own subcontractor (with the holding company that owns
// it, and that holding company's other subsidiary, which supplies nobody), a director of the
// supplier who also sits on two other boards (one of those companies owning a subsidiary), a trade
// council the supplier is only a member of, a company known only by where it is incorporated, and a
// company nothing points at. Person nodes come with the "people" layer; entities always arrive.
const org = (id: string) => ({ id, label: 'Entity', layer: null, props: { kind: 'organization' } })
const network = {
  nodes: [
    { id: 'program', label: 'Entity', layer: null, props: { kind: 'program' } },
    org('supplier'),
    org('subcontractor'),
    org('holding'),
    { id: 'director', label: 'Person', layer: 'people', props: {} },
    org('board-seat'),
    org('club'),
    org('club-subsidiary'),
    org('trade-council'),
    org('sister'),
    org('seated-only'),
    { id: 'country', label: 'Location', layer: 'countries', props: {} },
    org('isolated'),
  ],
  edges: [
    { source: 'supplier', target: 'program', type: 'SUPPLIES' },
    { source: 'subcontractor', target: 'supplier', type: 'SUPPLIES' },
    { source: 'holding', target: 'subcontractor', type: 'OWNS' },
    { source: 'director', target: 'supplier', type: 'HELD_ROLE' },
    { source: 'director', target: 'board-seat', type: 'HELD_ROLE' },
    { source: 'director', target: 'club', type: 'HELD_ROLE' },
    { source: 'club', target: 'club-subsidiary', type: 'OWNS' },
    { source: 'supplier', target: 'trade-council', type: 'MEMBER_OF' },
    { source: 'holding', target: 'sister', type: 'OWNS' },
    { source: 'seated-only', target: 'country', type: 'INCORPORATED_IN' },
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

test('the indirect-orgs toggle hides organizations no contract or ownership chain joins to a program, whatever the layers show', () => {
  // An organization with no edges at all counts as indirect too: nothing joins it to anything.
  assert.deepEqual(hiddenWith({ people: true, countries: true, indirect_orgs: false }), ['board-seat', 'club', 'club-subsidiary', 'isolated', 'seated-only', 'sister', 'trade-council'])
  // The default is to show them.
  assert.deepEqual(hiddenWith({ people: true, countries: true }), [])
})

test('affiliation to a supplier is not the chain; a contract or an ownership stake is', () => {
  const hidden = hiddenWith({ people: true, countries: true, indirect_orgs: false })
  // The trade council hangs straight off the supplier, on MEMBER_OF — the shape of RTX's lobbying
  // and membership network, none of it on an award.
  assert.ok(hidden.includes('trade-council'))
  // A subcontractor and the holding company that owns it are the chain, and stay.
  assert.ok(!hidden.includes('subcontractor') && !hidden.includes('holding'))
})

test('the indirect walk starts from the root too, and from nothing when the canvas has no anchor', () => {
  const noProgram = { nodes: network.nodes.filter(n => n.id !== 'program'), edges: network.edges.filter(e => e.target !== 'program') }
  const hidden = new Set<string>()
  assert.deepEqual([...indirectOrganizations(noProgram.nodes, noProgram.edges, hidden)], [])
  assert.deepEqual(
    [...indirectOrganizations(noProgram.nodes, noProgram.edges, hidden, ['supplier'])].sort(),
    ['board-seat', 'club', 'club-subsidiary', 'isolated', 'seated-only', 'sister', 'trade-council'],
  )
})

test('ownership counts pointing at the chain, not away from it', () => {
  const hidden = hiddenWith({ people: true, countries: true, indirect_orgs: false })
  // Who owns a company on the contract is material; that owner's other subsidiary is not — the
  // Raytheon Visual Analytics shape, on the canvas only because its parent sells to the program.
  assert.ok(!hidden.includes('holding'), 'the owner of a supplier stays')
  assert.ok(hidden.includes('sister'), 'the owner\'s other subsidiary does not')
  // Unless it is risky in its own right, where the pin holds it: Pacific Alloy under Zhejiang.
  const nodes = network.nodes.map(n => (n.id === 'sister' ? { ...n, props: { ...n.props, risk_score: 100 } } : n))
  assert.ok(![...hiddenNodeIds(nodes, network.edges, { people: true, countries: true, indirect_orgs: false })].includes('sister'))
})

// The same shape with risk on it: a donor to the trade council, a quiet peer beside it, an offshore
// company that shares only a country with the supplier, a risky company nothing points at, and a
// designated insider inside the supplier who also sits on a shell company and one ordinary board.
const risky = (id: string, score: number) => ({ id, label: 'Entity', layer: null, props: { kind: 'organization', risk_score: score } })
const person = (id: string, score?: number) => ({ id, label: 'Person', layer: 'people', props: score == null ? {} : { risk_score: score } })
const scored = {
  nodes: [
    ...network.nodes,
    risky('sanctioned-donor', 61),
    risky('quiet-donor', 12),
    risky('offshore', 70),
    risky('unattached', 90),
    person('insider', 100),
    risky('shell', 80),
    org('insider-board'),
  ],
  edges: [
    ...network.edges,
    { source: 'sanctioned-donor', target: 'trade-council', type: 'DONATED_TO' },
    { source: 'quiet-donor', target: 'trade-council', type: 'DONATED_TO' },
    { source: 'supplier', target: 'country', type: 'INCORPORATED_IN' },
    { source: 'offshore', target: 'country', type: 'INCORPORATED_IN' },
    { source: 'insider', target: 'supplier', type: 'HELD_ROLE' },
    { source: 'insider', target: 'shell', type: 'BENEFICIAL_OWNER_OF' },
    { source: 'insider', target: 'insider-board', type: 'HELD_ROLE' },
  ],
}
const hiddenInScored = (layers: Record<string, boolean>) => [...hiddenNodeIds(scored.nodes, scored.edges, layers)].sort()

test('an organization over the risk floor that reaches a supplier survives the indirect filter', () => {
  const hidden = hiddenInScored({ people: true, countries: true, indirect_orgs: false })
  // Two hops off the prime over donation and membership edges — the finding, not the clutter.
  assert.ok(!hidden.includes('sanctioned-donor'))
  // Its neighbour on the same council scores 12, so the filter takes it, and the council with it.
  assert.ok(hidden.includes('quiet-donor') && hidden.includes('trade-council'))
})

test('a shared country is not a path to a supplier, and neither is no path at all', () => {
  const hidden = hiddenInScored({ people: true, countries: true, indirect_orgs: false })
  assert.ok(hidden.includes('offshore'), 'sharing a jurisdiction is not a connection')
  assert.ok(hidden.includes('unattached'), 'a high score alone does not keep a node')
})

test('the risk pin also holds against orphan pruning, and against a hidden layer breaking the path', () => {
  // club-subsidiary reaches the supplier through club and the director. The indirect filter takes
  // club, which would strand the subsidiary — the pin keeps it, floating.
  const nodes = scored.nodes.map(n => (n.id === 'club-subsidiary' ? risky(n.id, 55) : n))
  const hidden = [...hiddenNodeIds(nodes, scored.edges, { people: true, countries: true, indirect_orgs: false })].sort()
  assert.ok(hidden.includes('club') && !hidden.includes('club-subsidiary'))
  // With the people layer off, the director no longer conducts and there is no path left to pin on.
  const peopleOff = [...hiddenNodeIds(nodes, scored.edges, { people: false, countries: true, indirect_orgs: false })].sort()
  assert.ok(peopleOff.includes('club-subsidiary'))
})

test('the risk pin needs a supplier on the canvas at all', () => {
  const noSupply = { nodes: scored.nodes, edges: scored.edges.filter(e => e.type !== 'SUPPLIES') }
  assert.deepEqual([...riskPinnedNodes(noSupply.nodes, noSupply.edges, new Set())], [])
  assert.deepEqual([...riskPinnedNodes(scored.nodes, scored.edges, new Set())].sort(), ['insider', 'sanctioned-donor', 'shell'])
})

test('a risky person is drawn over an off people layer, and an ordinary one is not', () => {
  const hidden = hiddenInScored({ people: false, countries: true })
  assert.ok(!hidden.includes('insider'), 'the layer hides people, not the designated insider')
  assert.ok(hidden.includes('director'), 'an ordinary director goes with the layer')
  // The pin is for the person, not their address book: the board they sit on for no other reason
  // is still gone.
  assert.ok(hidden.includes('insider-board'))
})

test('a risky organization is pinned through a risky person, whatever the people layer says', () => {
  for (const people of [true, false]) {
    const hidden = [...hiddenNodeIds(scored.nodes, scored.edges, { people, countries: true, indirect_orgs: false })]
    // No contract or ownership joins the shell to the program — only the insider does, and both of
    // them clear the floor, so both stay.
    assert.ok(!hidden.includes('shell'), `shell should be pinned with people=${people}`)
    assert.ok(!hidden.includes('insider'), `insider should be pinned with people=${people}`)
  }
})

test('a person over the floor with no path to a supplier is not pinned', () => {
  const nodes = [...scored.nodes, person('stranger', 95), risky('stranger-co', 95)]
  const edges = [...scored.edges, { source: 'stranger', target: 'stranger-co', type: 'HELD_ROLE' }]
  const hidden = [...hiddenNodeIds(nodes, edges, { people: false, countries: true })]
  assert.ok(hidden.includes('stranger') && hidden.includes('stranger-co'))
})

test('orphan pruning ignores self-loops and edges to nodes that are not loaded', () => {
  const nodes = [{ id: 'p', label: 'Person', layer: 'people', props: {} }, org('a')]
  const edges = [{ source: 'p', target: 'a' }, { source: 'a', target: 'a' }, { source: 'a', target: 'missing' }]
  assert.deepEqual([...orphanedOrganizations(nodes, edges, new Set(['p']))], ['a'])
})
