import assert from 'node:assert/strict'
import test from 'node:test'
import { identityLine, vendorCandidates } from '../src/lib/vendorIdentity.ts'

test('blank comparator candidates remain selectable by vendor name', () => {
  const candidates = vendorCandidates([{ id: 'a', name: 'Subaru Corporation', tier: 1, simulated: false }])
  assert.equal(candidates[0].name, 'Subaru Corporation')
  assert.match(candidates[0].identityLine, /Tier 1 · OBSERVED/)
})

test('same-name candidates carry an explicit ambiguity cue and stable differentiators', () => {
  const candidates = vendorCandidates([
    { id: 'ray-1', name: 'RAYTHEON COMPANY', uei: 'UEI-ONE', cage: 'CAGE1', lei: 'LEI', tier: 1, simulated: false },
    { id: 'ray-2', name: 'RAYTHEON COMPANY', uei: 'UEI-TWO', cage: 'CAGE2', lei: 'LEI', tier: 2, simulated: false },
  ])
  assert.ok(candidates.every(candidate => candidate.ambiguous))
  assert.match(candidates[0].matchContext, /Same-name record/)
  assert.match(candidates[0].identityLine, /UEI UEI-ONE · CAGE CAGE1 · LEI LEI · Tier 1/)
  assert.notEqual(candidates[0].identityLine, candidates[1].identityLine)
})

test('simulated records are explicit before selection', () => {
  assert.match(identityLine({ simulated: true, tier: 3 }), /SIMULATED/)
})

test('internal IDs remain stable values for direct-link restoration', () => {
  const [candidate] = vendorCandidates([{ id: 'entity-internal-42', name: 'Acme', tier: null, simulated: false }])
  assert.equal(candidate.id, 'entity-internal-42')
  assert.match(candidate.identityLine, /Record entity-internal-42/)
})