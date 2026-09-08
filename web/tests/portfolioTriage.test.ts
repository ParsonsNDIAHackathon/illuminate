import assert from 'node:assert/strict'
import test from 'node:test'
import { compareTrustworthy } from '../src/lib/portfolioTriage.ts'

test('trustworthy ranking never promotes high risk solely for stronger evidence', () => {
  const lowerRisk = { score: 18, confidence: 0.6, completeness: 0.55 }
  const highRisk = { score: 91, confidence: 1, completeness: 1 }

  assert.deepEqual([highRisk, lowerRisk].sort(compareTrustworthy), [lowerRisk, highRisk])
})

test('trustworthy ranking uses evidence quality when assessed risk is equal', () => {
  const weakerEvidence = { score: 30, confidence: 0.5, completeness: 0.9 }
  const strongerEvidence = { score: 30, confidence: 0.8, completeness: 0.7 }

  assert.deepEqual([weakerEvidence, strongerEvidence].sort(compareTrustworthy), [strongerEvidence, weakerEvidence])
})

test('unassessed vendors rank after assessed vendors', () => {
  const assessed = { score: 45, confidence: 0.4, completeness: 0.4 }
  const unavailable = { score: null, confidence: 1, completeness: 1 }

  assert.deepEqual([unavailable, assessed].sort(compareTrustworthy), [assessed, unavailable])
})