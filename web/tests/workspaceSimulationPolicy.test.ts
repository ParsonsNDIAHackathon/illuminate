import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../src/api/client.ts'
import { useGraph } from '../src/stores/graph.ts'
import { useWorkspace } from '../src/stores/workspace.ts'

const explorer = readFileSync(new URL('../src/views/Explorer.vue', import.meta.url), 'utf8')

test('disabling simulation evicts cached state and rejects a late simulation response', async () => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: { getItem: () => null, setItem: () => undefined },
  })
  const originalGet = api.get
  const originalPut = api.put
  let resolveGraph: ((value: any) => void) | undefined
  api.get = (() => new Promise(resolve => { resolveGraph = resolve })) as typeof api.get
  api.put = (async (_path: string, body: any) => body) as typeof api.put
  try {
    setActivePinia(createPinia())
    const graph = useGraph()
    const workspace = useWorkspace()
    workspace.ws.include_simulated = true
    graph.focusId = 'program-a'
    graph.nodes.set('scenario', {
      id: 'scenario', label: 'Entity', name: 'Scenario', props: { simulated: true },
    })
    graph.edges.set('scenario-edge', {
      id: 'scenario-edge', source: 'scenario', target: 'scenario',
      type: 'OWNS', props: { simulated: true },
    })
    graph.selectedId = 'scenario'
    graph.styleOps = [{ op: 'set', ids: ['scenario'], style: { fill: 'red' } }]
    graph.focusIds = ['scenario']

    const staleLoad = graph.loadAll({})
    const staleRequest = graph.requestVersion
    await workspace.save({ include_simulated: false })

    assert.equal(workspace.ws.include_simulated, false)
    assert.ok(graph.requestVersion > staleRequest)
    assert.equal(graph.replacementRequest, 0)
    assert.equal(graph.loading, false)
    assert.equal(graph.nodes.size, 0)
    assert.equal(graph.edges.size, 0)
    assert.equal(graph.selectedId, null)
    assert.deepEqual(graph.focusIds, [])
    assert.deepEqual(graph.legend, [])
    assert.deepEqual(graph.styleOps, [{ op: 'clear', scope: 'all' }])
    assert.equal(graph.focusId, 'program-a')

    resolveGraph?.({
      subgraph: {
        nodes: [{
          id: 'late-scenario', label: 'Entity', name: 'Late scenario',
          props: { simulated: true },
        }],
        edges: [],
      },
    })
    assert.equal(await staleLoad, false)
    assert.equal(graph.nodes.size, 0)
    assert.match(explorer, /watch\(\(\) => ws\.ws\.include_simulated, \(\) => reload\(\)\)/)
  } finally {
    api.get = originalGet
    api.put = originalPut
  }
})