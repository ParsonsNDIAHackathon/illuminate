import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../src/api/client.ts'
import { claimScope, createActiveRouteRequestGate, createRequestGate, missionProgramFromQuery, missionRootFromQuery, reportRouteQuery } from '../src/navigationState.ts'
import { useGraph } from '../src/stores/graph.ts'

const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const comparison = readFileSync(new URL('../src/views/VendorComparison.vue', import.meta.url), 'utf8')
const explorer = readFileSync(new URL('../src/views/Explorer.vue', import.meta.url), 'utf8')
const missionEntry = readFileSync(new URL('../src/views/MissionEntry.vue', import.meta.url), 'utf8')
const portfolio = readFileSync(new URL('../src/views/Portfolio.vue', import.meta.url), 'utf8')
const report = readFileSync(new URL('../src/views/EntityReport.vue', import.meta.url), 'utf8')
const router = readFileSync(new URL('../src/router.ts', import.meta.url), 'utf8')
const interoperability = readFileSync(new URL('../src/views/FindingsInteroperability.vue', import.meta.url), 'utf8')

test('global navigation is grouped by user intent', () => {
  assert.match(app, /title="Start mission"/)
  assert.match(app, /title="Mission graph"/)
  assert.match(app, /title="Supporting records"/)
  assert.match(app, /title="Administration"/)
  assert.match(app, /title: 'Share findings'/)
  assert.match(app, /<v-menu location="end"/)
  assert.doesNotMatch(app, /title: 'Compare'/)
  assert.doesNotMatch(app, /title: 'Connectors'/)
})

test('findings interoperability is visible and preserves lifecycle semantics', () => {
  assert.match(router, /path: '\/interoperability'/)
  assert.match(missionEntry, /contextualLink\('\/interoperability'\)/)
  assert.match(comparison, /path: '\/interoperability'/)
  assert.match(interoperability, /Schema \{\{ page\?\.meta\.schema_version/)
  assert.match(interoperability, /JSON · NDJSON · CSV/)
  assert.match(interoperability, /deleted: true/)
  assert.match(interoperability, /provenance, classification, truth status, simulation state/)
  assert.match(interoperability, /catalogPublished = computed\(\(\) => Boolean\(catalogDatasetId\.value\)/)
  assert.match(interoperability, /Validate dry run/)
  assert.match(interoperability, /catalog credentials are never sent to this browser/)
})

test('comparison requires a deliberate second vendor or explicit preset', () => {
  assert.match(comparison, /label="Choose a second vendor"/)
  assert.match(comparison, /leftId === rightId/)
  assert.match(comparison, /route\.query\.preset === 'judged'/)
  assert.match(comparison, /watch\(\(\) => route\.fullPath, applyRoute\)/)
  assert.match(comparison, /const \{ preset, \.\.\.query \} = route\.query/)
  assert.match(comparison, /router\.resolve\(destination\)\.fullPath === route\.fullPath/)
  assert.doesNotMatch(comparison, /\? loadLive\(\) : loadPreset\(\)/)
})

test('route changes restore a prior control or focus a page heading', () => {
  assert.match(router, /focusByLocation/)
  assert.match(router, /router\.beforeEach/)
  assert.match(router, /router\.afterEach/)
  assert.match(router, /main h1, main h2/)
  assert.match(router, /MutationObserver/)
  assert.match(router, /allowHeadingFallback/)
  assert.match(router, /document\.activeElement === target/)
})

test('query-only navigation clears stale claim scope', () => {
  assert.deepEqual(claimScope({ status: 'committed', entity_id: 'vendor-a', program_id: 'program-a' }), {
    status: 'committed',
    entityId: 'vendor-a',
    programId: 'program-a',
    claimId: '',
  })
  assert.deepEqual(claimScope({}), { status: 'staged', entityId: '', programId: '', claimId: '' })
})

test('mission program follows URL history instead of stale selection', () => {
  const programs = [{ id: 'program-a' }, { id: 'program-b' }]
  assert.equal(missionProgramFromQuery({ root_id: 'program-b' }, programs), 'program-b')
  assert.equal(missionProgramFromQuery({ root_id: 'program-a' }, programs), 'program-a')
  assert.equal(missionProgramFromQuery({}, programs), 'program-a')
})

test('leaving mission prevents delayed entry requests from changing graph scope', async () => {
  const requests = createActiveRouteRequestGate('mission')
  requests.mount()
  const request = requests.begin()
  let resolvePrograms: ((programs: Array<{ id: string }>) => void) | undefined
  const pendingPrograms = new Promise<Array<{ id: string }>>(resolve => { resolvePrograms = resolve })
  const route: { name: string; path: string; query: Record<string, string> } = { name: 'mission', path: '/', query: {} }
  const replacements: Array<Record<string, string>> = []
  const load = pendingPrograms.then(programs => {
    if (!requests.isCurrent(request, route.name)) return
    replacements.push({ root_id: missionProgramFromQuery(route.query, programs) })
  })

  route.name = 'graph'
  route.path = '/explorer'
  requests.unmount()
  resolvePrograms?.([{ id: 'program-a' }])
  await load

  assert.equal(route.path, '/explorer')
  assert.deepEqual(route.query, {})
  assert.deepEqual(replacements, [])
  assert.match(missionEntry, /onUnmounted\(\(\) => entryRequests\.unmount\(\)\)/)
  assert.match(missionEntry, /entryRequests\.isCurrent\(request, route\.name\)/)
})

test('ownership routes preserve report and mission context', () => {
  const context = { root_id: 'program-a', focus: 'edge-a', finding: 'foreign parent', family: 'ownership', evidence: 'record-a' }
  assert.deepEqual(reportRouteQuery(context, '', 'vendor-a', { entity_id: 'vendor-a', program_id: 'program-a', claim_id: 'claim-a' }), {
    ...context,
    vendor: 'vendor-a',
    entity_id: 'vendor-a',
    program_id: 'program-a',
    claim_id: 'claim-a',
  })
  assert.deepEqual(reportRouteQuery(context, '', 'vendor-a', { vendor: 'owner-a' }), {
    ...context,
    vendor: 'owner-a',
  })
})

test('affiliation report routes preserve finding and evidence context', () => {
  const context = { root_id: 'program-a', focus: 'edge-a', finding: 'foreign tie', family: 'affiliation', evidence: 'record-a' }
  assert.deepEqual(reportRouteQuery(context, 'program-a', 'vendor-a', { vendor: 'counterparty-a' }), {
    ...context,
    vendor: 'counterparty-a',
  })
  assert.match(report, /query: reportQuery\(\{ vendor: t\.entity_id \}\)/)
  assert.doesNotMatch(report, /query: \{ root_id: reportRoot \|\| undefined \}/)
})

test('query-only program changes replace the active mission scope', () => {
  assert.equal(missionRootFromQuery({ root_id: 'program-a' }, 'retained-program'), 'program-a')
  assert.equal(missionRootFromQuery({ root_id: 'program-b' }, 'retained-program'), 'program-b')
  assert.equal(missionRootFromQuery({}, 'retained-program'), 'retained-program')
})

test('late scope responses cannot replace the latest request', async () => {
  const requests = createRequestGate()
  const committed: string[] = []
  const complete = async (request: number, value: string, delay: number) => {
    await new Promise(resolve => setTimeout(resolve, delay))
    if (requests.isCurrent(request)) committed.push(value)
  }
  const programA = requests.begin()
  const slowA = complete(programA, 'program-a', 10)
  const programB = requests.begin()
  const fastB = complete(programB, 'program-b', 0)
  await Promise.all([slowA, fastB])
  assert.deepEqual(committed, ['program-b'])
})

test('a new mission clears an inherited bulk-retry state', async () => {
  const requests = createRequestGate()
  let retrying = false
  const programA = requests.begin()
  retrying = true
  const staleCleanup = new Promise<void>(resolve => setTimeout(() => {
    if (requests.isCurrent(programA)) retrying = false
    resolve()
  }, 10))
  const programB = requests.begin()
  retrying = false
  await staleCleanup
  assert.equal(requests.isCurrent(programB), true)
  assert.equal(retrying, false)
  assert.match(portfolio, /reportsLoading\.value = false; retrying\.value = false;/)
})

test('out-of-order mission graph responses keep the latest URL and canvas', async () => {
  const originalGet = api.get
  const pending = new Map<string, (value: any) => void>()
  api.get = ((path: string) => new Promise(resolve => {
    const entityId = new URL(path, 'http://test').searchParams.get('entity_id') || ''
    pending.set(entityId, resolve)
  })) as typeof api.get
  try {
    setActivePinia(createPinia())
    const graph = useGraph()
    const navigation = createRequestGate()
    let urlRoot = ''
    const navigate = async (rootId: string) => {
      const request = navigation.begin()
      const applied = await graph.focus(rootId, rootId, 2, {})
      if (!applied || !navigation.isCurrent(request)) return
      urlRoot = rootId
    }
    const programA = navigate('program-a')
    const programB = navigate('program-b')
    pending.get('program-b')?.({
      subgraph: { nodes: [{ id: 'program-b', label: 'Entity', name: 'Program B', props: { kind: 'program' } }], edges: [] },
      cypher: 'B',
      params: {},
    })
    await programB
    pending.get('program-a')?.({
      subgraph: { nodes: [{ id: 'program-a', label: 'Entity', name: 'Program A', props: { kind: 'program' } }], edges: [] },
      cypher: 'A',
      params: {},
    })
    await programA
    assert.equal(urlRoot, 'program-b')
    assert.equal(graph.focusId, 'program-b')
    assert.deepEqual(graph.nodeList.map(node => node.id), ['program-b'])
    assert.match(explorer, /if \(!applied \|\| !navigationRequests\.isCurrent\(request\)\) return/)
  } finally {
    api.get = originalGet
  }
})

test('back to a cached mission invalidates a delayed replacement', async () => {
  const originalGet = api.get
  let resolveProgramB: ((value: any) => void) | undefined
  api.get = (() => new Promise(resolve => { resolveProgramB = resolve })) as typeof api.get
  try {
    setActivePinia(createPinia())
    const graph = useGraph()
    graph.focusId = 'program-a'
    graph.focusLabel = 'Program A'
    graph.replace({ nodes: [{ id: 'program-a', label: 'Entity', name: 'Program A', props: { kind: 'program' } }], edges: [] })
    const navigation = createRequestGate()
    let urlRoot = 'program-a'
    const applyRoute = async (rootId: string) => {
      const request = navigation.begin()
      graph.invalidatePendingRequests()
      urlRoot = rootId
      if (graph.focusId === rootId && graph.nodes.size) return
      const applied = await graph.focus(rootId, rootId, 2, {})
      if (!applied || !navigation.isCurrent(request)) return
    }
    const programB = applyRoute('program-b')
    await applyRoute('program-a')
    resolveProgramB?.({
      subgraph: { nodes: [{ id: 'program-b', label: 'Entity', name: 'Program B', props: { kind: 'program' } }], edges: [] },
      cypher: 'B',
      params: {},
    })
    await programB
    assert.equal(urlRoot, 'program-a')
    assert.equal(graph.focusId, 'program-a')
    assert.deepEqual(graph.nodeList.map(node => node.id), ['program-a'])
    assert.equal(graph.loading, false)
    assert.match(explorer, /navigationRequests\.begin\(\)\s+graph\.invalidatePendingRequests\(\)/)
  } finally {
    api.get = originalGet
  }
})

test('layer reload follows the URL mission while its first load is pending', async () => {
  const originalGet = api.get
  const pending: Array<(value: any) => void> = []
  api.get = (() => new Promise(resolve => { pending.push(resolve) })) as typeof api.get
  try {
    setActivePinia(createPinia())
    const graph = useGraph()
    graph.focusId = 'program-a'
    graph.focusLabel = 'Program A'
    graph.replace({ nodes: [{ id: 'program-a', label: 'Entity', name: 'Program A', props: { kind: 'program' } }], edges: [] })
    const navigation = createRequestGate()
    let urlRoot = 'program-b'
    const applyRoute = async (force = false) => {
      const request = navigation.begin()
      graph.invalidatePendingRequests()
      const rootId = urlRoot
      if (!force && graph.focusId === rootId && graph.nodes.size) return
      const applied = await graph.focus(rootId, rootId, 2, {})
      if (!applied || !navigation.isCurrent(request)) return
    }
    const initialProgramB = applyRoute()
    const layerReload = applyRoute(true)
    pending[1]?.({
      subgraph: { nodes: [{ id: 'program-b', label: 'Entity', name: 'Program B', props: { kind: 'program' } }], edges: [] },
      cypher: 'B reload',
      params: {},
    })
    await layerReload
    pending[0]?.({
      subgraph: { nodes: [{ id: 'program-b-stale', label: 'Entity', name: 'Stale B', props: {} }], edges: [] },
      cypher: 'B stale',
      params: {},
    })
    await initialProgramB
    assert.equal(urlRoot, 'program-b')
    assert.equal(graph.focusId, 'program-b')
    assert.deepEqual(graph.nodeList.map(node => node.id), ['program-b'])
    assert.equal(graph.loading, false)
    assert.match(explorer, /async function reload\(\) \{\s+await applyRouteFocus\(true\)/)
  } finally {
    api.get = originalGet
  }
})

test('fresh graph enrichment runs but cannot supersede a pending replacement', async () => {
  const originalGet = api.get
  const originalPost = api.post
  let getCalls = 0
  let postCalls = 0
  api.get = (async () => {
    getCalls++
    return { subgraph: { nodes: [], edges: [] }, cypher: 'neighborhood', params: {} }
  }) as typeof api.get
  api.post = (async () => {
    postCalls++
    return { ok: true, subgraph: { nodes: [], edges: [] } }
  }) as typeof api.post
  try {
    setActivePinia(createPinia())
    let graph = useGraph()
    assert.equal(await graph.loadNeighbourhood('vendor-a', 1, {}), true)
    assert.equal((await graph.runTemplate('sole_source', {})).ok, true)
    assert.equal(getCalls, 1)
    assert.equal(postCalls, 1)

    let resolveFocus: ((value: any) => void) | undefined
    api.get = (() => {
      getCalls++
      return new Promise(resolve => { resolveFocus = resolve })
    }) as typeof api.get
    setActivePinia(createPinia())
    graph = useGraph()
    const focus = graph.focus('program-b', 'Program B', 2, {})
    assert.equal(await graph.loadNeighbourhood('vendor-a', 1, {}), false)
    assert.equal((await graph.runTemplate('sole_source', {})).stale, true)
    assert.equal(getCalls, 2)
    assert.equal(postCalls, 1)
    resolveFocus?.({
      subgraph: { nodes: [{ id: 'program-b', label: 'Entity', name: 'Program B', props: { kind: 'program' } }], edges: [] },
      cypher: 'B',
      params: {},
    })
    assert.equal(await focus, true)
    assert.equal(graph.focusId, 'program-b')
  } finally {
    api.get = originalGet
    api.post = originalPost
  }
})