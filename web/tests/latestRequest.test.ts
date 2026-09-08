import test from 'node:test'
import assert from 'node:assert/strict'
import { LatestRequest, ScopedRowRequests } from '../src/lib/latestRequest.ts'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

test('same vendor decision history from an older mission cannot overwrite the new scope', async () => {
  const gate = new LatestRequest()
  const missionA = deferred<{ root: string; decision: string }>()
  const missionB = deferred<{ root: string; decision: string }>()
  let visible: { root: string; decision: string } | null = null
  async function load(request: ReturnType<typeof deferred<{ root: string; decision: string }>>) {
    const generation = gate.begin()
    const result = await request.promise
    if (gate.isCurrent(generation)) visible = result
  }
  const oldLoad = load(missionA)
  const newLoad = load(missionB)
  missionB.resolve({ root: 'program-b', decision: 'monitor' })
  await newLoad
  missionA.resolve({ root: 'program-a', decision: 'investigate' })
  await oldLoad
  assert.deepEqual(visible, { root: 'program-b', decision: 'monitor' })
})

test('simultaneous row retries complete independently in one mission scope', async () => {
  const requests = new ScopedRowRequests<string>()
  const scope = requests.beginScope()
  const resultA = deferred<string>()
  const resultB = deferred<string>()
  const rows = {
    a: { pending: false, contract: '' },
    b: { pending: false, contract: '' },
  }
  async function assess(key: 'a' | 'b', result: ReturnType<typeof deferred<string>>) {
    const vendor = `vendor-${key}`
    const token = requests.beginRow(vendor, scope)
    rows[key].pending = true
    try {
      const contract = await result.promise
      if (requests.isCurrent(vendor, token)) rows[key].contract = contract
    } finally {
      if (requests.isCurrent(vendor, token)) rows[key].pending = false
    }
  }
  const a = assess('a', resultA)
  const b = assess('b', resultB)
  resultB.resolve('contract-b'); await b
  resultA.resolve('contract-a'); await a
  assert.deepEqual(rows, {
    a: { pending: false, contract: 'contract-a' },
    b: { pending: false, contract: 'contract-b' },
  })
})

test('a row retry does not strand remaining initial batch assessments', async () => {
  const requests = new ScopedRowRequests<string>()
  const scope = requests.beginScope()
  const oldA = deferred<string>(); const retryA = deferred<string>(); const laterZ = deferred<string>()
  const rows = {
    a: { pending: false, contract: '' },
    z: { pending: false, contract: '' },
  }
  async function assess(key: 'a' | 'z', result: ReturnType<typeof deferred<string>>) {
    const vendor = `vendor-${key}`
    const token = requests.beginRow(vendor, scope)
    rows[key].pending = true
    try {
      const contract = await result.promise
      if (requests.isCurrent(vendor, token)) rows[key].contract = contract
    } finally {
      if (requests.isCurrent(vendor, token)) rows[key].pending = false
    }
  }
  const first = assess('a', oldA)
  const later = assess('z', laterZ)
  const retry = assess('a', retryA)
  oldA.resolve('stale-a'); await first
  laterZ.resolve('contract-z'); await later
  retryA.resolve('contract-a'); await retry
  assert.deepEqual(rows, {
    a: { pending: false, contract: 'contract-a' },
    z: { pending: false, contract: 'contract-z' },
  })
  assert.equal(requests.currentScope(), scope, 'row retry must not cancel the portfolio batch loop')
})