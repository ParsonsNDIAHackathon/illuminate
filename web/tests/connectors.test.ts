import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { invalidateConnectorResults, isModelBackedConnector, recordConnectorResult } from '../src/connectors/diagnosticState.ts'

const connectors = readFileSync(new URL('../src/views/Connectors.vue', import.meta.url), 'utf8')

test('saving a credential immediately runs its provider diagnostic', () => {
  assert.match(connectors, />Save & test</)
  assert.match(connectors, /if \(connector\) await check\(connector\)/)
})

test('replacing a model credential disables chat until its diagnostic succeeds', () => {
  const disable = connectors.indexOf('if (isModelBackedConnector(name)) useChat().modelKey = false')
  const credentialPut = connectors.indexOf('await api.put(`/api/connectors/${name}/credential`')

  assert.notEqual(disable, -1)
  assert.notEqual(credentialPut, -1)
  assert.ok(disable < credentialPut, 'model availability must fail closed before storing the replacement')
})

test('OpenAI-backed tests synchronize model availability for success and failure', () => {
  assert.match(connectors, /function updateModelAvailability\(c: any, result: ConnectorTestResult\)/)
  assert.equal(
    connectors.match(/recordResult\(c, result\)/g)?.length,
    2,
    'both normal diagnostic responses and request failures must record model availability',
  )
})

test('removing a shared model credential disables model-backed chat', () => {
  assert.match(connectors, /if \(isModelBackedConnector\(c\.name\)\) useChat\(\)\.modelKey = false/)
})

test('changing a shared model credential invalidates both connector results', () => {
  const results = {
    openai: { ok: true },
    websearch: { ok: true },
    sam: { ok: true },
  }

  assert.equal(isModelBackedConnector('openai'), true)
  assert.equal(isModelBackedConnector('websearch'), true)
  assert.deepEqual(invalidateConnectorResults(results, 'openai'), { sam: { ok: true } })
  assert.deepEqual(invalidateConnectorResults(results, 'websearch'), { sam: { ok: true } })
  assert.deepEqual(invalidateConnectorResults(results, 'sam'), {
    openai: { ok: true },
    websearch: { ok: true },
  })
})

test('testing one connector preserves every other connector result', () => {
  const previous = {
    openai: { ok: true, detail: 'OpenAI is available' },
    websearch: { ok: true, detail: 'Web search is available' },
    sam: { ok: false, detail: 'The credential was rejected' },
  }
  const result = { ok: false, detail: 'OpenAI authentication failed' }

  assert.deepEqual(recordConnectorResult(previous, 'openai', result), {
    openai: result,
    websearch: previous.websearch,
    sam: previous.sam,
  })
})