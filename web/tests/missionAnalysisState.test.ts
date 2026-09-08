import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  missionAnalysisKey,
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