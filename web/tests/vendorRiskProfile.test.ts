import assert from 'node:assert/strict'
import test from 'node:test'
import { getVendorRiskProfile } from '../src/api/client.ts'

test('vendor report requests explicitly exclude simulated data by default', async () => {
  const originalFetch = globalThis.fetch
  let requested = ''
  globalThis.fetch = async input => {
    requested = String(input)
    return new Response(JSON.stringify({
      source_mode: 'live',
      refresh: { status: 'queued' },
      identity: { id: 'vendor-1', name: 'Observed Vendor', simulated: false },
      risk: { categories: [], diligence_flags: [] },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }

  try {
    const profile = await getVendorRiskProfile('vendor-1')
    assert.equal(new URL(requested, 'http://localhost').searchParams.get('include_simulated'), 'false')
    assert.equal(profile.sourceMode, 'live')
    assert.equal(profile.refresh?.status, 'queued')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('vendor report requests can explicitly include simulated data', async () => {
  const originalFetch = globalThis.fetch
  let requested = ''
  globalThis.fetch = async input => {
    requested = String(input)
    return new Response(JSON.stringify({
      identity: { id: 'scenario-1', name: 'Scenario Vendor', simulated: true },
      risk: { categories: [], diligence_flags: [] },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }

  try {
    const profile = await getVendorRiskProfile('scenario-1', undefined, 'mission-1', true)
    const url = new URL(requested, 'http://localhost')
    assert.equal(url.searchParams.get('root_id'), 'mission-1')
    assert.equal(url.searchParams.get('include_simulated'), 'true')
    assert.equal(profile.simulated, true)
  } finally {
    globalThis.fetch = originalFetch
  }
})