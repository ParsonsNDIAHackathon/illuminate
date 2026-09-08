import assert from 'node:assert/strict'
import test from 'node:test'

import cytoscape from 'cytoscape'

import { layerData, layerVisible } from '../src/stores/graphLayers.ts'

const claim = { id: 'claim-a', label: 'Claim', props: {} }
const source = { id: 'source-a', label: 'Artifact', props: { kind: 'record' } }
const document = { id: 'document-a', label: 'Artifact', props: { kind: 'filing' } }

function renderedWith(layers: Record<string, boolean>) {
  const cy = cytoscape({
    headless: true,
    elements: [claim, source, document].map(node => ({
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
  const cy = renderedWith({ claims: false, sources: false, artifacts: false })

  assert.equal(cy.getElementById('claim-a').data('layer'), 'claims')
  assert.equal(cy.getElementById('claim-a').hasClass('layer-hide'), true)
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