import assert from 'node:assert/strict'
import test from 'node:test'

import { supportedDecisionEvidenceRefs } from '../src/api/client.ts'

test('graph-backed findings retain stable evidence and omit internal relationship ids', () => {
  const refs = supportedDecisionEvidenceRefs([
    'rel_supply_123',
    '4:relationship-element-id',
    'clm_supply_123',
    'art_award_123',
    'clm_supply_123',
  ])

  assert.deepEqual(refs, ['art_award_123', 'clm_supply_123'])
})