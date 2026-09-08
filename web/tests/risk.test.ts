import assert from 'node:assert/strict'
import test from 'node:test'

import { bandChip, bandColor, bandLabel, bandOf, confidenceNote, haloFor, isThin, scoreLabel } from '../src/styles/risk.ts'

// The bands and their floors mirror risk.BANDS in api/illuminate/risk.py. If those move,
// these are the tests that should fail first.
test('band thresholds match the scorer', () => {
  assert.equal(bandOf(100), 'severe')
  assert.equal(bandOf(75), 'severe')
  assert.equal(bandOf(74), 'high')
  assert.equal(bandOf(50), 'high')
  assert.equal(bandOf(49), 'elevated')
  assert.equal(bandOf(25), 'elevated')
  assert.equal(bandOf(24), 'low')
  assert.equal(bandOf(0), 'low')
})

test('an unscored node is never dressed as a low-risk one', () => {
  // The whole model refuses to impute zeros; the visual encoding must not undo that by
  // painting "we know nothing" the same as "we looked and it was fine".
  assert.equal(bandOf(null), null)
  assert.equal(bandOf(undefined), null)
  assert.equal(bandLabel(null), 'Unscored')
  assert.equal(scoreLabel(null), 'unscored')
  assert.equal(bandColor(null, 'light'), null)
  assert.equal(haloFor(null, 'light'), null)
})

test('low risk is neutral, not green — a low score is not an all-clear', () => {
  assert.equal(bandChip('low'), undefined)
  assert.equal(haloFor('low', 'light'), null)
  assert.notEqual(bandColor('low', 'light'), bandColor('severe', 'light'))
})

test('halos grow and deepen with the band, and differ by theme', () => {
  const severe = haloFor('severe', 'light')!
  const elevated = haloFor('elevated', 'light')!
  assert.ok(severe.padding > elevated.padding)
  assert.ok(severe.opacity > elevated.opacity)
  assert.notEqual(haloFor('severe', 'light')!.color, haloFor('severe', 'dark')!.color)
})

test('thin coverage is called out in words, with the dimension count', () => {
  assert.ok(isThin(19))
  assert.ok(isThin(59))
  assert.ok(!isThin(60))
  assert.ok(!isThin(null))
  assert.match(confidenceNote(19, 1, 7), /Very thin/)
  assert.match(confidenceNote(19, 1, 7), /1 of 7 dimensions/)
  assert.match(confidenceNote(45), /^Thin/)
  assert.equal(confidenceNote(null), '')
})

test('a score reads with its band attached', () => {
  assert.equal(scoreLabel(96, 'severe'), '96 · severe')
  // Band is derived when the caller does not have one to hand.
  assert.equal(scoreLabel(30), '30 · elevated')
})
