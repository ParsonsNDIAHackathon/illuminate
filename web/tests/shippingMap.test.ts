import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { linkedShippingRoutes, shippingPath, routePath, usesPort, type ShippingCatalog } from '../src/shippingMap.ts'
import type { GNode, GEdge } from '../src/stores/graph.ts'
const catalog: ShippingCatalog = JSON.parse(readFileSync(new URL('../../api/illuminate/shipping_demo.json', import.meta.url), 'utf8'))
const route = catalog.routes[0]
const nodes: GNode[] = [{ id: route.supplier_id, label: 'Entity', name: 'SUBARU', props: {} }, { id: route.customer_id, label: 'Entity', name: 'V-22', props: {} }]
const edge: GEdge = { id: route.relationship_id, source: route.supplier_id, target: route.customer_id, type: 'SUPPLIES', props: {} }

test('routes require the exact loaded directional supplier relationship', () => {
  assert.equal(linkedShippingRoutes(catalog, nodes, [edge]).length, 2)
  assert.equal(linkedShippingRoutes(catalog, nodes.slice(0, 1), [edge]).length, 0)
  assert.equal(linkedShippingRoutes(catalog, nodes, [{ ...edge, source: edge.target, target: edge.source }]).length, 0)
  assert.equal(linkedShippingRoutes(catalog, nodes, [{ ...edge, id: 'another' }]).length, 0)
  assert.equal(linkedShippingRoutes(catalog, nodes, [{ ...edge, type: 'OWNS' }]).length, 0)
})
test('search includes goods, ports, passages, and supplier names', () => {
  assert.equal(linkedShippingRoutes(catalog, nodes, [edge], 'subaru pacific').length, 2)
  assert.equal(linkedShippingRoutes(catalog, nodes, [edge], 'oakland').length, 1)
  assert.equal(linkedShippingRoutes(catalog, nodes, [edge], 'unknown').length, 0)
  assert.equal(usesPort(route, 'nagoya'), true)
  assert.equal(usesPort(route, 'oakland'), false)
})
test('Pacific crossings split at both map edges, without a transatlantic stroke', () => {
  assert.equal(shippingPath([{ latitude: 10, longitude: 170 }, { latitude: 20, longitude: -170 }]), 'M1050,240 L1080,225 M0,225 L30,210')
  assert.equal(shippingPath([{ latitude: 20, longitude: -170 }, { latitude: 10, longitude: 170 }]), 'M30,210 L0,225 M1080,225 L1050,240')
  assert.equal(shippingPath([]), '')
  assert.ok(!routePath(route, catalog.ports).includes('NaN'))
  assert.equal(routePath(route, []), '')
})
