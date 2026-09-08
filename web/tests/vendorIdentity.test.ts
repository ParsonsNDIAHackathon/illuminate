import assert from 'node:assert/strict'
import test from 'node:test'
import { identityLine, vendorCandidates } from '../src/lib/vendorIdentity.ts'

test('blank comparator candidates remain selectable by vendor name', () => {
  const candidates = vendorCandidates([{ id: 'a', name: 'Subaru Corporation', tier: 1, simulated: false }])
  assert.equal(candidates[0].name, 'Subaru Corporation')
  assert.match(candidates[0].identityLine, /Tier 1$/)
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

test('a scenario record reads exactly like an observed one', () => {
  // Scenario material is disclosed once, by the app-bar badge. An identity line that
  // says SIMULATED hands the analyst the answer the tool is supposed to find.
  assert.equal(identityLine({ simulated: true, tier: 3 }), identityLine({ simulated: false, tier: 3 }))
  assert.doesNotMatch(identityLine({ simulated: true, tier: 3 }), /SIMULATED|OBSERVED/)
})

test('internal IDs remain stable values for direct-link restoration', () => {
  const [candidate] = vendorCandidates([{ id: 'entity-internal-42', name: 'Acme', tier: null, simulated: false }])
  assert.equal(candidate.id, 'entity-internal-42')
  assert.match(candidate.identityLine, /Record entity-internal-42/)
})