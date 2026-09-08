import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import test, { after, before } from 'node:test'

const port = 4179
const cdpPort = 9239
let vite
let chromium
let socket
let sequence = 0
const pending = new Map()

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function waitFor(check, message, timeout = 10000) {
  const started = Date.now()
  while (Date.now() - started < timeout) {
    const result = await check()
    if (result) return result
    await sleep(75)
  }
  throw new Error(`Timed out waiting for ${message}`)
}

function command(method, params = {}) {
  const id = ++sequence
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

async function evaluate(expression) {
  const response = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (response.result.exceptionDetails) throw new Error(response.result.exceptionDetails.text)
  return response.result.result.value
}

async function open(path) {
  await command('Page.navigate', { url: `http://127.0.0.1:${port}${path}` })
  await waitFor(() => evaluate('document.readyState === "complete"'), 'page load')
}

async function bodyIncludes(text) {
  return evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`)
}

before(async () => {
  vite = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(port)], { stdio: 'ignore' })
  await waitFor(async () => {
    try { return (await fetch(`http://127.0.0.1:${port}`)).ok } catch { return false }
  }, 'Vite server')

  chromium = spawn('chromium', [
    '--headless=new', '--no-sandbox', '--disable-gpu',
    `--remote-debugging-port=${cdpPort}`, '--user-data-dir=/tmp/illuminate-vendor-comparison-browser-test',
    'about:blank',
  ], { stdio: 'ignore' })
  const target = await waitFor(async () => {
    try {
      const pages = await (await fetch(`http://127.0.0.1:${cdpPort}/json`)).json()
      return pages.find(page => page.type === 'page')
    } catch { return false }
  }, 'Chromium debugger')

  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true })
    socket.addEventListener('error', reject, { once: true })
  })
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (!message.id || !pending.has(message.id)) return
    const waiter = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) waiter.reject(new Error(message.error.message))
    else waiter.resolve(message)
  })
  await command('Page.enable')
  await command('Runtime.enable')
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    (() => {
      const entities = [
        { id: 'ray-1', name: 'RAYTHEON COMPANY', uei: 'UEI-ONE', cage: 'CAGE1', lei: 'LEI-SHARED', tier: 1, simulated: false, source: 'SAM.gov' },
        { id: 'ray-2', name: 'RAYTHEON COMPANY', uei: 'UEI-TWO', cage: 'CAGE2', lei: 'LEI-SHARED', tier: 2, simulated: false, source: 'USAspending' },
        { id: 'sim-1', name: 'Scenario Components', uei: 'SIM-UEI', cage: 'SIM01', tier: 3, simulated: true, source: 'training scenario' },
      ];
      const json = body => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }));
      window.fetch = input => {
        const url = String(input);
        if (url.includes('/api/workspace')) return json({ root_id: null, root_label: null, permission_mode: 'ask_always', model_strong: null, model_fast: null, openai_base_url: null, layers: {} });
        if (url.includes('/api/permissions')) return json({ pending: [], history: [] });
        if (url.includes('/api/jobs')) return json([]);
        if (url.includes('/api/claims')) return json([]);
        if (url.includes('/api/entities?')) return json({ items: entities, total: entities.length });
        const match = url.match(/\\/api\\/entities\\/([^/]+)\\/report/);
        if (match) {
          const entity = entities.find(item => item.id === decodeURIComponent(match[1]));
          return json({
            identity: entity,
            risk: { contract_version: 'uc11.vendor-risk.v1', score: 12, band: 'low', disposition: 'standard_monitoring', confidence: .9, completeness: 1, freshness: 'current', categories: [], diligence_flags: [] },
            screen_evidence: [],
          });
        }
        if (url.includes('/api/graph')) return json({ nodes: [], edges: [] });
        return json({});
      };
    })();
  ` })
})

after(() => {
  socket?.close()
  chromium?.kill()
  vite?.kill()
})

test('portfolio deep link preserves the first vendor with a blank comparator', async () => {
  await open('/compare/vendors?left=ray-1')
  await waitFor(() => bodyIncludes('First vendor preserved.'), 'blank-comparator guidance')
  assert.equal(await bodyIncludes('Atlas Precision Systems'), false)
  assert.equal(await evaluate('new URL(location.href).searchParams.get("left")'), 'ray-1')
})

test('the judged-preset deep link still restores the frozen comparison', async () => {
  await open('/compare/vendors?preset=judged')
  await waitFor(() => bodyIncludes('Atlas Precision Systems'), 'judged preset')
  assert.equal(await bodyIncludes('Offline judged case'), true)
})

test('same-name and simulated candidates show differentiators before selection', async () => {
  await evaluate(`(() => {
    const input = document.querySelectorAll('.v-autocomplete input')[1];
    input.focus();
    input.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    input.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  })()`)
  await waitFor(() => bodyIncludes('AMBIGUOUS NAME'), 'same-name ambiguity cue')
  const text = await evaluate('document.body.innerText')
  assert.match(text, /UEI UEI-ONE · CAGE CAGE1 · LEI LEI-SHARED · Tier 1/)
  assert.match(text, /UEI UEI-TWO · CAGE CAGE2 · LEI LEI-SHARED · Tier 2/)
  assert.match(text, /Scenario Components[\s\S]*SIMULATED/)
})

test('direct comparison links restore both legal records and header identifiers', async () => {
  await open('/compare/vendors?left=ray-1&right=ray-2')
  await waitFor(() => bodyIncludes('Framework uc11.vendor-risk.v1'), 'live comparison profiles')
  const text = await evaluate('document.body.innerText')
  assert.match(text, /UEI UEI-ONE · CAGE CAGE1 · LEI LEI-SHARED · Tier 1/)
  assert.match(text, /UEI UEI-TWO · CAGE CAGE2 · LEI LEI-SHARED · Tier 2/)
  assert.equal(await evaluate('new URL(location.href).searchParams.get("right")'), 'ray-2')
})