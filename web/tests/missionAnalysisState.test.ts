import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  missionAnalysisKey,
  extendMissionResultIds,
  resolveMissionAnalysis,
  retainMissionCompletion,
  shouldRunMissionAnalysis,
} from '../src/missionAnalysisState.ts'

const explorer = readFileSync(new URL('../src/views/Explorer.vue', import.meta.url), 'utf8')

test('a completed analysis is cleared when the route moves to another mission scope', () => {
  const queryA = { mission: 'Supply chain', template: 'sole_source', root_id: 'program-a' }
  const keyA = missionAnalysisKey(queryA)
  const completedA = resolveMissionAnalysis(
    { ok: true, subgraph: { nodes: [{ id: 'vendor-a' }], edges: [] } },
    keyA,
    'sole_source',
    'program-a',
    'Supply chain',
  ).completion
  assert.ok(completedA)

  const keyB = missionAnalysisKey({ root_id: 'program-b' })
  assert.equal(retainMissionCompletion(completedA, keyB, false), null)
  assert.match(explorer, /presetCompletion\.value = retainMissionCompletion\(presetCompletion\.value, missionKey/)
})

test('guided list expansion includes loaded one-hop neighbors and excludes unrelated context', () => {
  assert.deepEqual(
    extendMissionResultIds(['vendor-a', 'finding-edge'], 'vendor-a', [
      { id: 'existing-edge', source: 'existing-neighbor', target: 'vendor-a' },
      { id: 'new-edge', source: 'vendor-a', target: 'new-neighbor' },
      { id: 'unrelated-edge', source: 'elsewhere-a', target: 'elsewhere-b' },
    ]),
    ['vendor-a', 'finding-edge', 'existing-edge', 'existing-neighbor', 'new-edge', 'new-neighbor'],
  )
  assert.match(explorer, /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
  assert.match(explorer, /:result-ids="guidedListIds"/)
})

test('guided status and recovery feedback flow after search instead of covering it', () => {
  const overlayStart = explorer.indexOf('class="canvas-overlays"')
  const search = explorer.indexOf('class="search"', overlayStart)
  const error = explorer.indexOf('class="graph-error"', search)
  const progress = explorer.indexOf('class="mission-progress"', error)
  const completion = explorer.indexOf('class="mission-complete"', progress)
  const truncation = explorer.indexOf('class="truncation"', completion)
  assert.ok(overlayStart >= 0 && overlayStart < search)
  assert.ok(search < error && error < progress && progress < completion)
  assert.ok(completion < truncation)
  assert.doesNotMatch(explorer, /\.graph-error\s*\{[^}]*position:absolute/)
  assert.doesNotMatch(explorer, /\.mission-(?:progress|complete)\s*\{[^}]*position:absolute/)
})

test('failed and empty analyses remain retryable until a usable result succeeds', () => {
  const key = missionAnalysisKey({ mission: 'Supply chain', template: 'sole_source', root_id: 'program-a' })
  const failed = resolveMissionAnalysis({ ok: false, data: { error: 'source unavailable' } }, key, 'sole_source', 'program-a', 'Supply chain')
  assert.equal(failed.completion, null)
  assert.equal(failed.error, 'source unavailable')
  assert.equal(shouldRunMissionAnalysis(failed.completion, key, true), true)

  const empty = resolveMissionAnalysis({ ok: true, subgraph: { nodes: [], edges: [] } }, key, 'sole_source', 'program-a', 'Supply chain')
  assert.equal(empty.completion, null)
  assert.match(empty.error, /no usable graph results/)
  assert.equal(shouldRunMissionAnalysis(empty.completion, key, true), true)

  const succeeded = resolveMissionAnalysis({ ok: true, subgraph: { nodes: [{ id: 'vendor-a' }], edges: [] } }, key, 'sole_source', 'program-a', 'Supply chain')
  assert.ok(succeeded.completion)
  assert.equal(succeeded.error, '')
  assert.equal(shouldRunMissionAnalysis(succeeded.completion, key, true), false)
  assert.doesNotMatch(explorer, /lastMissionPreset/)
})

test('guided completion retains only returned finding identity and truth state', () => {
  const key = missionAnalysisKey({ mission: 'Supply chain', template: 'sole_source', root_id: 'program-a' })
  const result = resolveMissionAnalysis({
    ok: true,
    data: { rows: [{ id: 'vendor-a', name: 'Vendor A' }] },
    subgraph: {
      nodes: [
        { id: 'program-a', label: 'Entity', name: 'Program A', props: { kind: 'program' } },
        { id: 'vendor-a', label: 'Entity', name: 'Vendor A', props: { simulated: true } },
        { id: 'intermediate-a', label: 'Entity', name: 'Intermediate Supplier', props: {} },
        { id: 'owner-a', label: 'Entity', name: 'Contextual Parent', props: {} },
      ],
      edges: [{ id: 'supply-a', props: { simulated: true } }],
    },
  }, key, 'sole_source', 'program-a', 'Supply chain')
  assert.deepEqual(result.completion?.elementIds, ['program-a', 'vendor-a', 'intermediate-a', 'owner-a', 'supply-a'])
  assert.deepEqual(result.completion?.affected, [{ id: 'vendor-a', name: 'Vendor A' }])
  assert.equal(result.completion?.hasSimulated, true)
  assert.match(explorer, /failedPreset\.value.*runPreset/)
})